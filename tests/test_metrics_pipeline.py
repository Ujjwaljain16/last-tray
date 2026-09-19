"""The metric layer as a stage: determinism, refusal to compute from missing or tampered canonical inputs, a consistent forgery caught by the
contracts, weather-only blocking, and static/runtime guarantees that metrics never reads raw (or staging) data."""
from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from src.metrics import contracts as ct
from src.metrics.evaluate import DETERMINISTIC_FILES, EVIDENCE_CSV, METRICS_CSV, OUT_SUBDIR, REPORT_MD, SUMMARY_JSON, run_metrics
from src.metrics.inputs import MetricInputError, load_metric_inputs
from src.model.build import MANIFEST_JSON, TABLE_FILES
from tests.static_checks import raw_access_violations

REPO = Path(__file__).resolve().parents[1]
METRICS_DIR = REPO / "src" / "metrics"
pytestmark = pytest.mark.usefixtures("no_network")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture()
def metrics_copy(tmp_path, real_model) -> Path:
    """A private copy of the canonical model + validation summary directories that a test may damage."""
    out = tmp_path / "out"
    for sub in ("model", "validation"):
        shutil.copytree(real_model.out / sub, out / sub)
    return out


def resign(out: Path, table: str) -> None:
    """Simulate a CONSISTENT forgery: record the new checksum and row count of a canonical table in the model manifest."""
    p = out / "model" / MANIFEST_JSON
    manifest = json.loads(p.read_text(encoding="utf-8"))
    path = out / "model" / TABLE_FILES[table]
    manifest["tables"][table]["sha256"] = sha(path)
    manifest["tables"][table]["rows"] = sum(1 for _ in path.open(encoding="utf-8")) - 1
    p.write_text(json.dumps(manifest), encoding="utf-8")


class TestDeterminism:
    def test_two_runs_write_byte_identical_files(self, metrics_copy, cfg):
        run_metrics(cfg, metrics_copy)
        first = {n: sha(metrics_copy / OUT_SUBDIR / n) for n in DETERMINISTIC_FILES}
        run_metrics(cfg, metrics_copy)
        assert {n: sha(metrics_copy / OUT_SUBDIR / n) for n in DETERMINISTIC_FILES} == first

    def test_no_wall_clock_lf_endings_and_stable_metric_order(self, real_metrics):
        for n in DETERMINISTIC_FILES:
            assert b"\r\n" not in (real_metrics.out / OUT_SUBDIR / n).read_bytes(), n
        text = (real_metrics.out / OUT_SUBDIR / SUMMARY_JSON).read_text(encoding="utf-8") + (real_metrics.out / OUT_SUBDIR / REPORT_MD).read_text(encoding="utf-8")
        assert not any(k in text for k in ("started", "finished", "created_at", "utc_now", "Generated on"))
        with (real_metrics.out / OUT_SUBDIR / METRICS_CSV).open(encoding="utf-8") as fh:
            assert [r["metric_id"] for r in csv.DictReader(fh)] == list(ct.ORDER)

    def test_processes_with_different_hash_seeds_and_directories_agree(self, tmp_path, real_model):
        outs = []
        for seed, cwd in (("5", REPO), ("31337", tmp_path)):
            out = tmp_path / f"seed{seed}"
            for sub in ("model", "validation"):
                shutil.copytree(real_model.out / sub, out / sub)
            env = {**os.environ, "PYTHONHASHSEED": seed, "PYTHONPATH": str(REPO)}
            code = ("import sys; from pathlib import Path; from src.config import load_config; from src.metrics.evaluate import run_metrics; "
                    f"r = run_metrics(load_config(Path(r'{REPO}') / 'config'), Path(r'{out}')); sys.exit(0 if r.core_status == 'PASSED' else 4)")
            done = subprocess.run([sys.executable, "-c", code], cwd=cwd, env=env, capture_output=True, text=True, timeout=180)
            assert done.returncode == 0, done.stderr
            outs.append({n: sha(out / OUT_SUBDIR / n) for n in DETERMINISTIC_FILES})
        assert outs[0] == outs[1], [n for n in outs[0] if outs[0][n] != outs[1][n]]


class TestInputsAreVerified:
    def test_a_missing_manifest_blocks_and_removes_stale_metrics(self, metrics_copy, cfg):
        assert run_metrics(cfg, metrics_copy).core_status == "PASSED" and all((metrics_copy / OUT_SUBDIR / n).exists() for n in DETERMINISTIC_FILES)
        (metrics_copy / "model" / MANIFEST_JSON).unlink()
        res = run_metrics(cfg, metrics_copy)
        assert res.core_status == "BLOCKED" and "canonical model has not been built" in res.error
        assert not any((metrics_copy / OUT_SUBDIR / n).exists() for n in DETERMINISTIC_FILES), "a stale metric must never look current"

    @pytest.mark.parametrize("table", ["fact_dining_session", "fact_session_component", "fact_daily_volume", "fact_weighing_event"])
    def test_an_altered_canonical_table_is_detected_by_checksum(self, metrics_copy, cfg, table):
        p = metrics_copy / "model" / TABLE_FILES[table]
        p.write_bytes(p.read_bytes() + b"\n")
        res = run_metrics(cfg, metrics_copy)
        assert res.core_status == "BLOCKED" and "does not match the SHA-256 recorded by the model" in res.error

    def test_a_missing_canonical_table_stops_the_metrics(self, metrics_copy, cfg):
        (metrics_copy / "model" / TABLE_FILES["fact_dining_session"]).unlink()
        assert "fact_dining_session.csv is missing" in run_metrics(cfg, metrics_copy).error

    def test_a_blocked_or_failed_model_is_not_measured(self, metrics_copy, cfg):
        p = metrics_copy / "model" / MANIFEST_JSON
        m = json.loads(p.read_text(encoding="utf-8"))
        m["core_status"] = "BLOCKED"
        p.write_text(json.dumps(m), encoding="utf-8")
        assert "reports its core lane as BLOCKED" in run_metrics(cfg, metrics_copy).error
        m["core_status"], m["controls"]["fail"] = "BUILT", 1
        p.write_text(json.dumps(m), encoding="utf-8")
        assert "failed control checks" in run_metrics(cfg, metrics_copy).error

    def test_a_model_built_on_another_validation_run_is_refused(self, metrics_copy, cfg):
        p = metrics_copy / "validation" / "validation_summary.json"
        s = json.loads(p.read_text(encoding="utf-8"))
        s["run_id"] = "val-000000000000"
        p.write_text(json.dumps(s), encoding="utf-8")
        assert "different validation run" in run_metrics(cfg, metrics_copy).error

    def test_a_header_change_is_refused(self, metrics_copy, cfg):
        p = metrics_copy / "model" / TABLE_FILES["fact_daily_volume"]
        p.write_text(p.read_text(encoding="utf-8").replace("volume_irregularity", "volume_oddity", 1), encoding="utf-8")
        resign(metrics_copy, "fact_daily_volume")
        assert "does not have the declared canonical columns" in run_metrics(cfg, metrics_copy).error

    def test_the_loader_raises_a_metric_input_error(self, tmp_path):
        with pytest.raises(MetricInputError):
            load_metric_inputs(tmp_path)


class TestConsistentForgeriesAreCaughtByTheContracts:
    def test_a_forged_session_weight_with_a_valid_checksum_fails_the_metrics_and_the_event_control(self, metrics_copy, cfg):
        p = metrics_copy / "model" / TABLE_FILES["fact_dining_session"]
        lines = p.read_text(encoding="utf-8").splitlines(keepends=True)
        header = lines[0].strip().split(",")
        idx = header.index("derived_selected_meal_weight_g")
        target = next(i for i, l in enumerate(lines[1:], 1) if l.startswith("session1006|non_registered_export,") is False and ",registered_export," in l and l.split(",")[idx])
        cells = lines[target].rstrip("\n").split(",")
        forged_key = cells[0]
        cells[idx] = str(int(cells[idx]) + 5000)
        lines[target] = ",".join(cells) + "\n"
        p.write_text("".join(lines), encoding="utf-8")
        resign(metrics_copy, "fact_dining_session")
        res = run_metrics(cfg, metrics_copy)
        assert res.core_status == "FAILED"
        assert "MC07" in res.summary["controls"]["failed_checks"] and forged_key in res.checks[[c.check_id for c in res.checks].index("MC07")].observed
        # one forged weight may leave the median and P90 inside tolerance; the independent event-level control is what catches it

    def test_a_forged_readiness_flag_shrinks_a_count_and_fails_m3_and_m5(self, metrics_copy, cfg):
        p = metrics_copy / "model" / TABLE_FILES["fact_dining_session"]
        lines = p.read_text(encoding="utf-8").splitlines(keepends=True)
        header = lines[0].strip().split(",")
        idx = header.index("core_ready")
        target = next(i for i, l in enumerate(lines[1:], 1) if ",registered_export," in l and l.split(",")[idx] == "true")
        cells = lines[target].rstrip("\n").split(",")
        cells[idx] = "false"
        lines[target] = ",".join(cells) + "\n"
        p.write_text("".join(lines), encoding="utf-8")
        resign(metrics_copy, "fact_dining_session")
        res = run_metrics(cfg, metrics_copy)
        assert res.core_status == "FAILED" and {"M3", "M5"} <= set(res.summary["failed_metrics"])
        assert "counts 1696/1699 differ from the approved 1697/1699" in res.summary["problems"]["M5"][-1]


class TestWeatherLaneIsIndependent:
    def test_a_damaged_weather_table_blocks_s1_only(self, metrics_copy, cfg):
        p = metrics_copy / "model" / TABLE_FILES["fact_weather"]
        p.write_bytes(p.read_bytes() + b"x")
        res = run_metrics(cfg, metrics_copy)
        assert res.weather_status == "BLOCKED" and res.core_status == "PASSED"
        rows = {r["metric_id"]: r for r in res.rows}
        assert rows["S1"]["status"] == "BLOCKED" and rows["S1"]["value"] is None
        assert all(rows[m]["status"] == "PASS" for m in ("M1", "M2", "M3", "M4", "M5", "S2"))

    def test_only_the_weather_control_may_fail_for_the_core_metrics_to_proceed(self, metrics_copy, cfg):
        p = metrics_copy / "model" / MANIFEST_JSON
        m = json.loads(p.read_text(encoding="utf-8"))
        m["weather_status"], m["controls"]["fail"], m["controls"]["failed_checks"] = "BLOCKED", 1, ["M22"]
        p.write_text(json.dumps(m), encoding="utf-8")
        assert run_metrics(cfg, metrics_copy).core_status == "PASSED", "a weather-lane control failure never blocks the core metrics"
        m["controls"]["failed_checks"] = ["M10"]
        p.write_text(json.dumps(m), encoding="utf-8")
        assert "failed control checks" in run_metrics(cfg, metrics_copy).error, "a core control failure always does"
        m["weather_status"], m["controls"]["failed_checks"] = "BUILT", ["M22"]
        p.write_text(json.dumps(m), encoding="utf-8")
        assert "failed control checks" in run_metrics(cfg, metrics_copy).error, "M22 is tolerated only while the weather lane is not BUILT"

    def test_a_model_reporting_blocked_weather_is_respected(self, metrics_copy, cfg):
        p = metrics_copy / "model" / MANIFEST_JSON
        m = json.loads(p.read_text(encoding="utf-8"))
        m["weather_status"] = "BLOCKED"
        p.write_text(json.dumps(m), encoding="utf-8")
        res = run_metrics(cfg, metrics_copy)
        assert res.weather_status == "BLOCKED" and res.core_status == "PASSED"


class TestMetricsNeverReadRawOrStagingData:
    IO_MODULES = ("inputs.py", "evaluate.py")

    def test_no_metric_module_can_read_raw_data(self):
        for p in sorted(METRICS_DIR.glob("*.py")):
            assert raw_access_violations(p.read_text(encoding="utf-8"), may_touch_files=p.name in self.IO_MODULES) == [], p.name

    def test_the_computation_and_contract_modules_do_no_file_io_at_all(self):
        for name in ("compute.py", "contracts.py", "stats.py", "populations.py", "controls.py"):
            assert raw_access_violations((METRICS_DIR / name).read_text(encoding="utf-8"), may_touch_files=False) == [], name

    def test_metrics_succeed_with_no_raw_directory_and_no_staging_and_read_only_model_and_validation(self, metrics_copy, cfg, monkeypatch):
        assert not (metrics_copy / "staging").exists() and not (metrics_copy / "data").exists() and not (metrics_copy.parent / "data").exists()
        opened: list[str] = []
        real_open = Path.open

        def spy(self, *a, **k):
            opened.append(str(self))
            return real_open(self, *a, **k)

        monkeypatch.setattr(Path, "open", spy)
        assert run_metrics(cfg, metrics_copy).core_status == "PASSED"
        reads = [p for p in opened if not p.startswith(str(metrics_copy / OUT_SUBDIR))]
        allowed = (str(metrics_copy / "model"), str(metrics_copy / "validation"))
        assert reads and all(p.startswith(allowed) for p in reads), [p for p in reads if not p.startswith(allowed)]


class TestDocumentation:
    def test_the_contract_document_lists_every_metric_and_the_s1_note(self):
        doc = (REPO / "docs" / "metric_contract.md").read_text(encoding="utf-8")
        for mid in ct.ORDER:
            assert f"**{mid}**" in doc or f"| {mid} |" in doc or f"{mid}" in doc
        assert "metrics implementation" in doc.lower() and "NOT_ATTEMPTED_QUARANTINED" in doc

    def test_no_output_makes_an_affirmative_forbidden_claim(self, real_metrics):
        from src.metrics.evaluate import _has_banned_affirmative
        banned = ("customers", "diners", "visits", "transactions", "savings", "food waste estimate", "data is correct", "measurements are accurate")
        texts = [str(v) for r in real_metrics.result.rows for v in (r["metric_name"], r["value_display"], r["interpretation"])]
        texts += [e["What it tells us"] for e in real_metrics.result.evidence] + [e["Metric"] + " " + e["Value"] for e in real_metrics.result.evidence]
        for t in texts:
            assert _has_banned_affirmative(t, banned) == [], t
