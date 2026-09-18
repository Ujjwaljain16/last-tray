"""Explicit source retrieval (the ONLY code path that downloads). Invoked by:  python -m src.pipeline.fetch --source <name>

Rules that keep retrieval honest:
  * Retrieval is always an explicit act. The normal pipeline never calls anything here.
  * It never overwrites an existing raw file and never edits a pin.
  * A refreshed source is a NEW snapshot in its own directory, with its own snapshot.json (URL, time, status, headers,
    checksums). Adopting it means a human updates config/sources.yml and the decision log; the pipeline will not.
  * Flavoria bytes are static, so a MISSING pinned archive can be restored and is verified against the pins.
    FMI XML embeds a retrieval timestamp, so its bytes can never equal the pinned bytes: weather retrieval therefore always
    produces a new snapshot and reports whether the parsed CONTENT equals the pinned content.
  * All-or-nothing: a failed or incomplete retrieval leaves nothing behind at a pinned path.
"""
from __future__ import annotations

import io
import json
import os
import tarfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Callable

from src.config import Config
from src.ingest.hashing import digest_bytes
from src.ingest.http import FetchFailed, HttpClient, HttpError, get_with_retry
from src.ingest.weather import ParsedWeather, WeatherParseError, check_chunk_completeness, parse_weather_xml, plan_weather_chunks

KEEP_HEADERS = ("content-type", "content-length", "etag", "last-modified", "date")


class FetchOutcome(str, Enum):
    OK = "OK"
    RECOVERED = "RECOVERED"     # succeeded, but at least one request needed a retry
    NO_OP = "NO_OP"             # nothing to do (pinned file already present); nothing was changed
    FAILED = "FAILED"


@dataclass
class FetchedFile:
    filename: str
    path: str
    size_bytes: int
    md5: str
    sha256: str
    url: str
    http_status: int
    attempts: int
    content_sha256: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    elements: int | None = None


@dataclass
class FetchReport:
    source: str
    outcome: FetchOutcome
    snapshot_dir: Path | None = None
    files: list[FetchedFile] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)
    equivalent_to_pins: bool | None = None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _stamp(t: datetime) -> str:
    return "refresh-" + t.strftime("%Y%m%dT%H%M%SZ")


def _keep(headers) -> dict[str, str]:
    return {k.lower(): v for k, v in headers.items() if k.lower() in KEEP_HEADERS}


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".part")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def _new_dir(base: Path, stamp: str) -> Path:
    d = base / stamp
    n = 1
    while d.exists():                   # never reuse or overwrite an existing snapshot directory
        n += 1
        d = base / f"{stamp}-{n}"
    return d


# ---- Flavoria ------------------------------------------------------------------------------------------------------------------
def fetch_flavoria(cfg: Config, dest_root: Path, client: HttpClient, *, refresh: bool = False,
                   sleep: Callable[[float], None] = time.sleep, clock: Callable[[], datetime] = _now) -> FetchReport:
    f = cfg.sources.flavoria
    pinned = dest_root / "flavoria" / f.archive_filename
    report = FetchReport("flavoria", FetchOutcome.OK)
    if pinned.exists() and not refresh:
        report.outcome = FetchOutcome.NO_OP
        report.messages.append(f"{pinned} is already present. Pins govern it and it was not touched. "
                               "Use --refresh to retrieve a NEW snapshot into its own directory.")
        return report
    t = clock()
    try:
        resp, attempts = get_with_retry(client, f.archive_url, None, cfg.sources.weather.retry, sleep)
    except FetchFailed as exc:
        report.outcome = FetchOutcome.FAILED
        report.messages.append(f"download failed: {exc}. Nothing was written.")
        return report
    except HttpError as exc:
        report.outcome = FetchOutcome.FAILED
        report.messages.append(f"transport error: {exc}. Nothing was written.")
        return report
    data = resp.content
    d = digest_bytes(data)
    declared = resp.headers.get("Content-Length") or resp.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) != len(data):
        report.outcome = FetchOutcome.FAILED
        report.messages.append(f"truncated download: Content-Length {declared} but received {len(data)} bytes. Nothing was written.")
        return report
    try:
        with tarfile.open(fileobj=io.BytesIO(data)) as tf:
            n_members = len(tf.getmembers())
    except (tarfile.TarError, EOFError) as exc:
        report.outcome = FetchOutcome.FAILED
        report.messages.append(f"downloaded bytes are not a readable tar archive ({exc}). Nothing was written.")
        return report
    matches = (d.size, d.md5, d.sha256) == (f.archive_size_bytes, f.archive_md5, f.archive_sha256)
    report.equivalent_to_pins = matches
    if not refresh and not matches:
        report.outcome = FetchOutcome.FAILED
        report.messages.append(f"restored file does not match the pins (size {d.size}, md5 {d.md5}, sha256 {d.sha256}). "
                               "Nothing was written at the pinned path. If the source legitimately changed, use --refresh for a new snapshot.")
        return report

    target_dir = pinned.parent if not refresh else _new_dir(dest_root / "flavoria", _stamp(t))
    target = target_dir / f.archive_filename
    _atomic_write(target, data)
    ff = FetchedFile(f.archive_filename, target.as_posix(), d.size, d.md5, d.sha256, f.archive_url, resp.status_code, len(attempts), None, _keep(resp.headers))
    report.files.append(ff)
    record = {"source": "flavoria", "mode": "refresh" if refresh else "restore_missing_pinned", "retrieved_at": t.isoformat(),
              "url": f.archive_url, "http_status": resp.status_code, "attempts": len(attempts), "response_headers": ff.headers,
              "size_bytes": d.size, "md5": d.md5, "sha256": d.sha256, "archive_members": n_members,
              "equivalent_to_pins": matches, "pins_updated": False}
    sidecar = target.with_name(target.name + ".retrieval.json") if not refresh else target_dir / "snapshot.json"
    sidecar.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    report.snapshot_dir = target_dir
    report.outcome = FetchOutcome.RECOVERED if len(attempts) > 1 else FetchOutcome.OK
    if refresh:
        report.messages.append("bytes identical to the pinned archive." if matches else
                               "bytes DIFFER from the pinned archive: this is a genuinely new snapshot. Pins were NOT updated. Adopt it only through an explicit change to config/sources.yml and a decision-log entry.")
    else:
        report.messages.append("pinned archive restored and verified against size, MD5 and SHA-256.")
    return report


# ---- FMI weather ----------------------------------------------------------------------------------------------------------------
def fetch_weather(cfg: Config, dest_root: Path, client: HttpClient, *, sleep: Callable[[float], None] = time.sleep,
                  clock: Callable[[], datetime] = _now) -> FetchReport:
    w = cfg.sources.weather
    report = FetchReport("weather", FetchOutcome.OK)
    t = clock()
    plans = plan_weather_chunks(w)
    expected_params = tuple(w.request["parameters"])
    pins = {s.file: s for s in w.raw_files}
    got: list[tuple[str, bytes, ParsedWeather, object, int, dict]] = []
    retried = False
    for plan in plans:
        try:
            resp, attempts = get_with_retry(client, w.endpoint, plan.params, w.retry, sleep)
            parsed = parse_weather_xml(resp.content)
        except FetchFailed as exc:
            report.outcome = FetchOutcome.FAILED
            report.messages.append(f"{plan.filename}: {exc}. Nothing was written.")
            return report
        except HttpError as exc:
            report.outcome = FetchOutcome.FAILED
            report.messages.append(f"{plan.filename}: transport error: {exc}. Nothing was written.")
            return report
        except WeatherParseError as exc:
            report.outcome = FetchOutcome.FAILED
            report.messages.append(f"{plan.filename}: unusable response: {exc}. Nothing was written.")
            return report
        reason = check_chunk_completeness(parsed, plan, expected_params)
        if reason:
            report.outcome = FetchOutcome.FAILED
            report.messages.append(f"{plan.filename}: incomplete response: {reason}. Nothing was written.")
            return report
        retried = retried or len(attempts) > 1
        got.append((plan.filename, resp.content, parsed, plan, len(attempts), _keep(resp.headers)))

    hours = {tm for _, _, p, _, _, _ in got for tm, par, _ in p.triples if par == expected_params[0]}
    if len(hours) != w.expected_hours:
        report.outcome = FetchOutcome.FAILED
        report.messages.append(f"retrieved {len(hours)} distinct hours, expected {w.expected_hours}. Nothing was written.")
        return report

    snap_dir = _new_dir(dest_root / "weather", _stamp(t))
    same = True
    requests_log = []
    for name, content, parsed, plan, n_attempts, headers in got:
        d = digest_bytes(content)
        _atomic_write(snap_dir / name, content)
        pin = pins.get(name)
        eq = bool(pin and pin.content_sha256 == parsed.content_sha256)
        same = same and eq
        report.files.append(FetchedFile(name, (snap_dir / name).as_posix(), d.size, d.md5, d.sha256, plan.url(w.endpoint), 200, n_attempts, parsed.content_sha256, headers, len(parsed.triples)))
        requests_log.append({"file": name, "url": plan.url(w.endpoint), "http_status": 200, "attempts": n_attempts, "size_bytes": d.size,
                             "sha256": d.sha256, "content_sha256": parsed.content_sha256, "elements": len(parsed.triples),
                             "content_equals_pin": eq, "response_headers": headers})
    record = {"source": "fmi_weather", "mode": "new_snapshot", "retrieved_at": t.isoformat(), "endpoint": w.endpoint, "fmisid": w.fmisid,
              "requests": requests_log, "content_equivalent_to_pins": same, "pins_updated": False}
    (snap_dir / "snapshot.json").write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    report.snapshot_dir = snap_dir
    report.equivalent_to_pins = same
    report.outcome = FetchOutcome.RECOVERED if retried else FetchOutcome.OK
    report.messages.append(
        "parsed CONTENT is identical to the pinned snapshot (bytes differ because FMI stamps each response with its retrieval time)."
        if same else "parsed content DIFFERS from the pinned snapshot: a genuinely new snapshot.")
    report.messages.append("Pins were NOT updated. To adopt this snapshot, copy the files to data/raw/weather/, update config/sources.yml "
                           "(use --print-pins) and record the decision. The pipeline never does this by itself.")
    return report


def pin_snippet(report: FetchReport) -> str:
    """YAML for config/sources.yml, for a human to review and commit. Never applied automatically."""
    lines = []
    for f in report.files:
        if f.content_sha256:
            lines.append(f"    - {{file: {f.filename}, bytes: {f.size_bytes}, sha256: {f.sha256}, content_sha256: {f.content_sha256}, elements: {f.elements}}}")
        else:
            lines.append(f"    size_bytes: {f.size_bytes}\n    md5: {f.md5}\n    sha256: {f.sha256}")
    return "\n".join(lines)
