"""Explicit retrieval (python -m src.pipeline.fetch), tested with a fake HTTP client: no network, no sleeping."""
from __future__ import annotations

import hashlib
import json
import re
import tarfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.config import RetryPolicy
from src.ingest.http import FetchFailed, HttpConnectionError, HttpResponse, HttpTimeout, get_with_retry
from src.ingest.retrieval import FetchOutcome, fetch_flavoria, fetch_weather, pin_snippet
from src.ingest.weather import plan_weather_chunks
from src.pipeline import fetch as fetch_cli

REPO = Path(__file__).resolve().parents[1]
FIXED = datetime(2026, 9, 19, 12, 0, 0, tzinfo=timezone.utc)
clock = lambda: FIXED
pytestmark = pytest.mark.usefixtures("no_network")


class Scripted:
    """Answers each call from a queue (exceptions are raised). Records calls; never touches a network."""

    def __init__(self, script):
        self.script, self.calls = list(script), []

    def get(self, url, *, params=None, timeout=30.0):
        self.calls.append((url, dict(params or {}), timeout))
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class Sleeper:
    def __init__(self):
        self.naps: list[float] = []

    def __call__(self, s):
        self.naps.append(s)


def ok(content: bytes, **headers) -> HttpResponse:
    return HttpResponse(200, content, headers)


def status(code: int, body: bytes = b"", **headers) -> HttpResponse:
    return HttpResponse(code, body, headers)


TAR = (REPO / "data/raw/flavoria/dataset_csv.tar").read_bytes()
def _different() -> bytes:
    """Same length, still a readable tar, but one payload byte differs (a tar's last 1 KiB is padding, so edit the middle)."""
    b = bytearray(TAR)
    b[100_000] ^= 0xFF
    return bytes(b)


OTHER = _different()
assert OTHER != TAR and len(OTHER) == len(TAR)
POLICY = RetryPolicy(max_attempts=4, backoff_base_seconds=2, backoff_factor=2, timeout_seconds=30)


def weather_payload(cfg) -> list[HttpResponse]:
    """The committed XML files, in request order: what a healthy FMI would return."""
    w = cfg.sources.weather
    return [ok((REPO / w.local_dir / p.filename).read_bytes()) for p in plan_weather_chunks(w)]


# ---- retry policy ---------------------------------------------------------------------------------------------------------------------------
class TestBoundedRetry:
    def test_success_first_time(self):
        resp, attempts = get_with_retry(Scripted([ok(b"x")]), "u", None, POLICY, Sleeper())
        assert resp.content == b"x" and [a.result for a in attempts] == ["ok"]

    def test_timeout_then_success_recovers_with_exponential_backoff(self):
        sleeper = Sleeper()
        resp, attempts = get_with_retry(Scripted([HttpTimeout("t"), HttpConnectionError("c"), ok(b"y")]), "u", None, POLICY, sleeper)
        assert [a.result for a in attempts] == ["timeout", "connection_error", "ok"]
        assert sleeper.naps == [2, 4]

    @pytest.mark.parametrize("code", [429, 500, 502, 503, 504])
    def test_transient_statuses_are_retried(self, code):
        _, attempts = get_with_retry(Scripted([status(code), ok(b"z")]), "u", None, POLICY, Sleeper())
        assert [a.result for a in attempts] == [f"HTTP {code}", "ok"]

    def test_retry_after_is_honoured_but_capped(self):
        s = Sleeper()
        get_with_retry(Scripted([status(429, b"", **{"Retry-After": "7"}), status(429, b"", **{"Retry-After": "9999"}), ok(b"z")]), "u", None, POLICY, s)
        assert s.naps == [7, 60]

    def test_retries_are_bounded_and_the_failure_is_reported(self):
        s = Sleeper()
        client = Scripted([status(500)] * 4)
        with pytest.raises(FetchFailed, match="gave up after 4 attempts") as e:
            get_with_retry(client, "u", None, POLICY, s)
        assert len(client.calls) == 4 and len(e.value.attempts) == 4 and len(s.naps) == 3

    def test_a_non_retryable_status_fails_immediately_with_the_servers_reason(self):
        client = Scripted([status(400, b"Too long time interval requested!"), ok(b"never reached")])
        with pytest.raises(FetchFailed, match="not retryable: Too long time interval") as e:
            get_with_retry(client, "u", None, POLICY, Sleeper())
        assert len(client.calls) == 1 and len(e.value.attempts) == 1


# ---- Flavoria -----------------------------------------------------------------------------------------------------------------------------------
class TestFetchFlavoria:
    def test_present_pinned_file_is_never_touched_and_nothing_is_requested(self, cfg, tmp_path):
        (tmp_path / "flavoria").mkdir()
        p = tmp_path / "flavoria" / "dataset_csv.tar"
        p.write_bytes(b"precious")
        client = Scripted([])
        rep = fetch_flavoria(cfg, tmp_path, client, sleep=Sleeper(), clock=clock)
        assert rep.outcome is FetchOutcome.NO_OP and client.calls == [] and p.read_bytes() == b"precious"

    def test_a_missing_pinned_archive_is_restored_and_verified(self, cfg, tmp_path):
        client = Scripted([ok(TAR, **{"Content-Length": str(len(TAR)), "ETag": '"abc"'})])
        rep = fetch_flavoria(cfg, tmp_path, client, sleep=Sleeper(), clock=clock)
        p = tmp_path / "flavoria" / "dataset_csv.tar"
        assert rep.outcome is FetchOutcome.OK and p.read_bytes() == TAR
        side = json.loads(p.with_name("dataset_csv.tar.retrieval.json").read_text())
        assert side["url"] == cfg.sources.flavoria.archive_url and side["equivalent_to_pins"] is True and side["pins_updated"] is False
        assert side["response_headers"]["etag"] == '"abc"' and side["retrieved_at"].startswith("2026-09-19T12:00:00")
        assert client.calls[0][0] == cfg.sources.flavoria.archive_url

    def test_a_transient_failure_is_recovered_and_reported_as_recovered(self, cfg, tmp_path):
        rep = fetch_flavoria(cfg, tmp_path, Scripted([HttpTimeout("slow"), ok(TAR)]), sleep=Sleeper(), clock=clock)
        assert rep.outcome is FetchOutcome.RECOVERED and rep.files[0].attempts == 2

    def test_bytes_that_do_not_match_the_pins_are_not_written_at_the_pinned_path(self, cfg, tmp_path):
        other = OTHER
        rep = fetch_flavoria(cfg, tmp_path, Scripted([ok(other)]), sleep=Sleeper(), clock=clock)
        assert rep.outcome is FetchOutcome.FAILED and "does not match the pins" in rep.messages[0]
        assert not (tmp_path / "flavoria" / "dataset_csv.tar").exists()
        assert not list(tmp_path.rglob("*.part"))

    def test_truncated_download_is_rejected(self, cfg, tmp_path):
        rep = fetch_flavoria(cfg, tmp_path, Scripted([ok(TAR[:5000], **{"Content-Length": str(len(TAR))})]), sleep=Sleeper(), clock=clock)
        assert rep.outcome is FetchOutcome.FAILED and "truncated" in rep.messages[0] and not any(tmp_path.rglob("*.tar"))

    def test_a_non_archive_response_is_rejected(self, cfg, tmp_path):
        rep = fetch_flavoria(cfg, tmp_path, Scripted([ok(b"<html>captive portal</html>")]), sleep=Sleeper(), clock=clock)
        assert rep.outcome is FetchOutcome.FAILED and "not a readable tar archive" in rep.messages[0] and not any(tmp_path.rglob("*.tar"))

    def test_exhausted_retries_fail_and_write_nothing(self, cfg, tmp_path):
        rep = fetch_flavoria(cfg, tmp_path, Scripted([status(503)] * 4), sleep=Sleeper(), clock=clock)
        assert rep.outcome is FetchOutcome.FAILED and "gave up after 4 attempts" in rep.messages[0] and not any(tmp_path.rglob("*"))

    def test_refresh_creates_a_new_snapshot_directory_and_leaves_the_pinned_file_alone(self, cfg, tmp_path):
        (tmp_path / "flavoria").mkdir()
        pinned = tmp_path / "flavoria" / "dataset_csv.tar"
        pinned.write_bytes(b"pinned bytes")
        rep = fetch_flavoria(cfg, tmp_path, Scripted([ok(TAR)]), refresh=True, sleep=Sleeper(), clock=clock)
        assert rep.outcome is FetchOutcome.OK and pinned.read_bytes() == b"pinned bytes"
        snap = rep.snapshot_dir
        assert snap.parent == tmp_path / "flavoria" and snap.name == "refresh-20260919T120000Z"
        assert (snap / "dataset_csv.tar").read_bytes() == TAR
        assert json.loads((snap / "snapshot.json").read_text())["pins_updated"] is False

    def test_refresh_never_reuses_an_existing_snapshot_directory(self, cfg, tmp_path):
        a = fetch_flavoria(cfg, tmp_path, Scripted([ok(TAR)]), refresh=True, sleep=Sleeper(), clock=clock).snapshot_dir
        b = fetch_flavoria(cfg, tmp_path, Scripted([ok(TAR)]), refresh=True, sleep=Sleeper(), clock=clock).snapshot_dir
        assert a != b and a.exists() and b.exists()

    def test_a_refresh_that_differs_from_the_pins_is_kept_as_a_new_snapshot_and_flagged(self, cfg, tmp_path):
        other = OTHER
        rep = fetch_flavoria(cfg, tmp_path, Scripted([ok(other)]), refresh=True, sleep=Sleeper(), clock=clock)
        assert rep.outcome is FetchOutcome.OK and rep.equivalent_to_pins is False
        assert "DIFFER" in rep.messages[0] and "Pins were NOT updated" in rep.messages[0]


# ---- FMI weather ----------------------------------------------------------------------------------------------------------------------------------
class TestFetchWeather:
    def test_new_snapshot_with_identical_content_to_the_pins(self, cfg, tmp_path):
        client = Scripted(weather_payload(cfg))
        rep = fetch_weather(cfg, tmp_path, client, sleep=Sleeper(), clock=clock)
        assert rep.outcome is FetchOutcome.OK and rep.equivalent_to_pins is True and len(rep.files) == 7
        assert len(client.calls) == 7 and all(c[0] == cfg.sources.weather.endpoint for c in client.calls)
        snap = json.loads((rep.snapshot_dir / "snapshot.json").read_text())
        assert snap["content_equivalent_to_pins"] is True and snap["pins_updated"] is False and len(snap["requests"]) == 7

    def test_requests_match_the_pinned_chunks_and_respect_the_server_limit(self, cfg):
        plans = plan_weather_chunks(cfg.sources.weather)
        assert [p.filename for p in plans] == [s.file for s in cfg.sources.weather.raw_files]
        assert all(p.hours <= cfg.sources.weather.max_hours_per_request for p in plans)
        assert plans[0].params["storedquery_id"] == "fmi::observations::weather::simple" and plans[0].params["fmisid"] == "100949"
        assert plans[0].params["starttime"] == "2020-10-05T00:00:00Z" and plans[-1].params["endtime"] == "2020-11-21T00:00:00Z"

    def test_pinned_files_are_never_overwritten(self, cfg, tmp_path):
        (tmp_path / "weather").mkdir()
        keep = tmp_path / "weather" / "fmi_100949_20201005_20201011.xml"
        keep.write_bytes(b"pinned")
        rep = fetch_weather(cfg, tmp_path, Scripted(weather_payload(cfg)), sleep=Sleeper(), clock=clock)
        assert keep.read_bytes() == b"pinned" and rep.snapshot_dir.name.startswith("refresh-")

    def test_a_retry_in_the_middle_is_recovered(self, cfg, tmp_path):
        payload = weather_payload(cfg)
        script = payload[:3] + [status(503), HttpTimeout("x")] + payload[3:]
        rep = fetch_weather(cfg, tmp_path, Scripted(script), sleep=Sleeper(), clock=clock)
        assert rep.outcome is FetchOutcome.RECOVERED and len(rep.files) == 7

    def test_an_exhausted_chunk_fails_the_whole_retrieval_and_writes_nothing(self, cfg, tmp_path):
        payload = weather_payload(cfg)
        rep = fetch_weather(cfg, tmp_path, Scripted(payload[:2] + [status(500)] * 4), sleep=Sleeper(), clock=clock)
        assert rep.outcome is FetchOutcome.FAILED and "fmi_100949_20201019_20201025.xml" in rep.messages[0]
        assert not any(tmp_path.rglob("*")), "all-or-nothing: no partial snapshot"

    def test_fmis_too_long_interval_error_is_not_retried_and_is_reported(self, cfg, tmp_path):
        client = Scripted([status(400, b"<ExceptionText>Too long time interval requested!</ExceptionText>")])
        rep = fetch_weather(cfg, tmp_path, client, sleep=Sleeper(), clock=clock)
        assert rep.outcome is FetchOutcome.FAILED and "Too long time interval" in rep.messages[0] and len(client.calls) == 1

    @pytest.mark.parametrize("payload, reason", [
        (b"<broken", "not well-formed XML"),
        (b'<r:ExceptionReport xmlns:r="http://www.opengis.net/ows/1.1"><r:Exception><r:ExceptionText>Invalid fmisid</r:ExceptionText></r:Exception></r:ExceptionReport>', "Invalid fmisid"),
    ])
    def test_malformed_or_exception_responses_are_rejected(self, cfg, tmp_path, payload, reason):
        rep = fetch_weather(cfg, tmp_path, Scripted([ok(payload)]), sleep=Sleeper(), clock=clock)
        assert rep.outcome is FetchOutcome.FAILED and reason in rep.messages[0] and not any(tmp_path.rglob("*"))

    def test_an_incomplete_response_is_rejected(self, cfg, tmp_path):
        payload = weather_payload(cfg)
        first = payload[0].content
        short = re.sub(rb"<wfs:member>.*?</wfs:member>", b"", first, count=5, flags=re.S)     # drop five elements
        rep = fetch_weather(cfg, tmp_path, Scripted([ok(short)]), sleep=Sleeper(), clock=clock)
        assert rep.outcome is FetchOutcome.FAILED and "incomplete response" in rep.messages[0] and not any(tmp_path.rglob("*"))

    def test_changed_content_is_reported_as_a_genuinely_new_snapshot(self, cfg, tmp_path):
        payload = weather_payload(cfg)
        changed = payload[0].content.replace(b"<BsWfs:ParameterValue>13.3<", b"<BsWfs:ParameterValue>13.4<", 1)
        assert changed != payload[0].content
        rep = fetch_weather(cfg, tmp_path, Scripted([ok(changed)] + payload[1:]), sleep=Sleeper(), clock=clock)
        assert rep.outcome is FetchOutcome.OK and rep.equivalent_to_pins is False and "DIFFERS" in rep.messages[0]

    def test_pin_snippet_is_printed_for_review_and_never_applied(self, cfg, tmp_path):
        before = hashlib.sha256((REPO / "config" / "sources.yml").read_bytes()).hexdigest()
        rep = fetch_weather(cfg, tmp_path, Scripted(weather_payload(cfg)), sleep=Sleeper(), clock=clock)
        snippet = pin_snippet(rep)
        assert snippet.count("content_sha256") == 7 and "fmi_100949_20201005_20201011.xml" in snippet
        assert hashlib.sha256((REPO / "config" / "sources.yml").read_bytes()).hexdigest() == before


# ---- the command line ---------------------------------------------------------------------------------------------------------------------------------
class TestFetchCli:
    def test_source_is_required(self, capsys):
        with pytest.raises(SystemExit) as e:
            fetch_cli.main([])
        assert e.value.code == 2 and "--source" in capsys.readouterr().err

    def test_success_exit_code_and_report(self, capsys, tmp_path):
        code = fetch_cli.main(["--source", "flavoria", "--dest", str(tmp_path)], client=Scripted([ok(TAR)]))
        out = capsys.readouterr().out
        assert code == 0 and "flavoria: OK" in out and "sha256=7f7e46f0" in out

    def test_failure_exit_code_is_5(self, capsys, tmp_path):
        code = fetch_cli.main(["--source", "flavoria", "--dest", str(tmp_path)], client=Scripted([status(500)] * 4))
        assert code == 5 and "FAILED" in capsys.readouterr().out

    def test_no_op_exits_zero_and_says_so(self, capsys, tmp_path):
        (tmp_path / "flavoria").mkdir()
        (tmp_path / "flavoria" / "dataset_csv.tar").write_bytes(b"x")
        assert fetch_cli.main(["--source", "flavoria", "--dest", str(tmp_path)], client=Scripted([])) == 0
        assert "NO_OP" in capsys.readouterr().out

    def test_bad_config_exits_2(self, capsys, tmp_path):
        assert fetch_cli.main(["--source", "weather", "--config-dir", str(tmp_path)], client=Scripted([])) == 2
