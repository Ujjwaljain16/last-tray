"""The sensitivity stage: determinism (figures included), refusal to run on missing or tampered canonical inputs, a consistent forgery caught by
the baseline gate, no mutation of any canonical file, and static/runtime guarantees that WP7 never reads raw or staging data."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from src.model.build import MANIFEST_JSON, TABLE_FILES
from src.sensitivity.registry import SCENARIOS
from src.sensitivity.stage import DETERMINISTIC_FILES, OUT_SUBDIR, REGISTRY_JSON, SUMMARY_JSON, run_sensitivity
from tests.static_checks import raw_access_violations

REPO = Path(__file__).resolve().parents[1]
SENS_DIR = REPO / "src" / "sensitivity"
pytestmark = pytest.mark.usefixtures("no_network")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_hashes(root: Path) -> dict[str, str]:
    return {str(p.relative_to(root)): sha(p) for p in sorted(root.rglob("*")) if p.is_file()}


@pytest.fixture()
def sens_copy(tmp_path, real_model, real_metrics) -> Path:
    """A private copy of the model, validation and metrics directories (the analysis reads model + the validation summary)."""
    out = tmp_path / "out"
    for sub in ("model", "validation", "metrics"):
        shutil.copytree(real_model.out / sub, out / sub)
    return out


def resign(out: Path, table: str) -> None:
    p = out / "model" / MANIFEST_JSON
    m = json.loads(p.read_text(encoding="utf-8"))
    path = out / "model" / TABLE_FILES[table]
    m["tables"][table]["sha256"] = sha(path)
    m["tables"][table]["rows"] = sum(1 for _ in path.open(encoding="utf-8")) - 1
    p.write_text(json.dumps(m), encoding="utf-8")


class TestDeterminism:
    def test_two_runs_write_byte_identical_files_including_figures(self, sens_copy, cfg):
        run_sensitivity(cfg, sens_copy)
        first = {n: sha(sens_copy / OUT_SUBDIR / n) for n in DETERMINISTIC_FILES}
        run_sensitivity(cfg, sens_copy)
        assert {n: sha(sens_copy / OUT_SUBDIR / n) for n in DETERMINISTIC_FILES} == first and len(first) == 13

    def test_no_wall_clock_lf_endings_and_sorted_scenarios(self, real_sensitivity):
        for n in DETERMINISTIC_FILES:
            if n.endswith(".png"):
                continue
            assert b"\r\n" not in (real_sensitivity.out / OUT_SUBDIR / n).read_bytes(), n
        text = (real_sensitivity.out / OUT_SUBDIR / SUMMARY_JSON).read_text(encoding="utf-8")
        assert not any(k in text for k in ("started", "finished", "created_at", "utc_now"))
        registry = json.loads((real_sensitivity.out / OUT_SUBDIR / REGISTRY_JSON).read_text(encoding="utf-8"))
        assert registry == [s.as_dict() for s in SCENARIOS] or [r["scenario_id"] for r in registry] == [s.scenario_id for s in SCENARIOS]

    def test_processes_with_different_hash_seeds_and_directories_agree(self, tmp_path, real_model, real_metrics):
        outs = []
        for seed, cwd in (("2", REPO), ("271828", tmp_path)):
            out = tmp_path / f"seed{seed}"
            for sub in ("model", "validation", "metrics"):
                shutil.copytree(real_model.out / sub, out / sub)
            env = {**os.environ, "PYTHONHASHSEED": seed, "PYTHONPATH": str(REPO)}
            code = ("import sys; from pathlib import Path; from src.config import load_config; from src.sensitivity.stage import run_sensitivity; "
                    f"r = run_sensitivity(load_config(Path(r'{REPO}') / 'config'), Path(r'{out}')); sys.exit(0 if r.core_status == 'PASSED' else 4)")
            done = subprocess.run([sys.executable, "-c", code], cwd=cwd, env=env, capture_output=True, text=True, timeout=240)
            assert done.returncode == 0, done.stderr
            outs.append({n: sha(out / OUT_SUBDIR / n) for n in DETERMINISTIC_FILES})
        assert outs[0] == outs[1], [n for n in outs[0] if outs[0][n] != outs[1][n]]

    def test_outputs_can_be_regenerated_from_the_baseline_inputs_alone(self, sens_copy, cfg):
        run_sensitivity(cfg, sens_copy)
        first = {n: sha(sens_copy / OUT_SUBDIR / n) for n in DETERMINISTIC_FILES}
        shutil.rmtree(sens_copy / OUT_SUBDIR)
        run_sensitivity(cfg, sens_copy)
        assert {n: sha(sens_copy / OUT_SUBDIR / n) for n in DETERMINISTIC_FILES} == first


class TestNothingCanonicalIsMutated:
    def test_the_analysis_leaves_every_canonical_baseline_file_byte_identical(self, sens_copy, cfg):
        before = {sub: tree_hashes(sens_copy / sub) for sub in ("model", "validation", "metrics")}
        assert run_sensitivity(cfg, sens_copy).core_status == "PASSED"
        after = {sub: tree_hashes(sens_copy / sub) for sub in ("model", "validation", "metrics")}
        assert before == after, "sensitivity writes only under outputs/evidence"

    def test_the_approved_configuration_is_untouched(self, sens_copy, cfg):
        files = sorted((REPO / "config").glob("*.yml"))
        before = {p.name: sha(p) for p in files}
        run_sensitivity(cfg, sens_copy)
        assert {p.name: sha(p) for p in files} == before

    def test_the_baseline_in_the_metric_outputs_is_still_the_approved_package(self, real_sensitivity, real_metrics):
        assert real_metrics.rows["M1"]["value"] == 499.0 and real_metrics.rows["M5"]["numerator"] == 1697 and real_metrics.rows["S2"]["numerator"] == 1663
        assert real_sensitivity.result.summary["baseline"]["M1"] == 499.0 and real_sensitivity.result.summary["baseline"]["M5_denominator"] == 1699


class TestInputsAreVerified:
    def test_a_missing_manifest_blocks_and_removes_stale_evidence(self, sens_copy, cfg):
        assert run_sensitivity(cfg, sens_copy).core_status == "PASSED"
        (sens_copy / "model" / MANIFEST_JSON).unlink()
        res = run_sensitivity(cfg, sens_copy)
        assert res.core_status == "BLOCKED" and "canonical model has not been built" in res.error
        assert not any((sens_copy / OUT_SUBDIR / n).exists() for n in DETERMINISTIC_FILES), "a stale finding must never look current"

    @pytest.mark.parametrize("table", ["fact_dining_session", "fact_weighing_event", "fact_daily_volume", "fact_session_component"])
    def test_an_altered_canonical_table_blocks_the_analysis(self, sens_copy, cfg, table):
        p = sens_copy / "model" / TABLE_FILES[table]
        p.write_bytes(p.read_bytes() + b"\n")
        res = run_sensitivity(cfg, sens_copy)
        assert res.core_status == "BLOCKED" and "does not match the SHA-256 recorded by the model" in res.error

    def test_a_forged_readiness_flag_with_a_valid_checksum_fails_the_baseline_gate_but_is_reported(self, sens_copy, cfg):
        p = sens_copy / "model" / TABLE_FILES["fact_dining_session"]
        lines = p.read_text(encoding="utf-8").splitlines(keepends=True)
        idx = lines[0].strip().split(",").index("core_ready")
        target = next(i for i, l in enumerate(lines[1:], 1) if ",registered_export," in l and l.split(",")[idx] == "true")
        cells = lines[target].rstrip("\n").split(",")
        cells[idx] = "false"
        lines[target] = ",".join(cells) + "\n"
        p.write_text("".join(lines), encoding="utf-8")
        resign(sens_copy, "fact_dining_session")
        res = run_sensitivity(cfg, sens_copy)
        assert res.core_status == "FAILED" and any("M3: baseline 1696" in x for x in res.analysis.baseline_problems)
        assert (sens_copy / OUT_SUBDIR / SUMMARY_JSON).exists(), "the difference is written so it can be inspected; nothing is tuned"
        assert json.loads((sens_copy / OUT_SUBDIR / SUMMARY_JSON).read_text(encoding="utf-8"))["core_status"] == "FAILED"

    def test_a_weather_problem_does_not_block_the_core_analysis(self, sens_copy, cfg):
        p = sens_copy / "model" / TABLE_FILES["fact_weather"]
        p.write_bytes(p.read_bytes() + b"x")
        res = run_sensitivity(cfg, sens_copy)
        assert res.core_status == "PASSED" and res.analysis.results["S00"].m1 == 499.0
        assert res.analysis.timezone[0]["mean_abs_t2m_diff_c"] is None, "without weather the temperature comparison is simply unavailable, never invented"


def module_sources():
    for p in sorted(SENS_DIR.glob("*.py")):
        yield p, p.read_text(encoding="utf-8")


class TestSensitivityNeverReadsRawOrStagingData:
    def test_no_module_can_read_raw_data(self):
        for p, src in module_sources():
            assert raw_access_violations(src, may_touch_files=p.name in ("stage.py", "figures.py")) == [], p.name     # both only WRITE under outputs/evidence

    def test_computation_modules_do_no_file_io_at_all(self):
        for name in ("registry.py", "data.py", "engine.py", "timezone.py", "classify.py", "questions.py", "evidence.py", "report.py"):
            assert raw_access_violations((SENS_DIR / name).read_text(encoding="utf-8"), may_touch_files=False) == [], name

    def test_the_registry_holds_declarations_and_no_calculation_imports(self):
        src = (SENS_DIR / "registry.py").read_text(encoding="utf-8")
        assert "import statistics" not in src and "from src.metrics" not in src and "import numpy" not in src

    def test_the_analysis_succeeds_with_no_raw_or_staging_directory_and_reads_only_model_and_validation(self, sens_copy, cfg, monkeypatch):
        assert not (sens_copy / "staging").exists() and not (sens_copy / "data").exists() and not (sens_copy.parent / "data").exists()
        opened: list[str] = []
        real_open = Path.open

        def spy(self, *a, **k):
            opened.append(str(self))
            return real_open(self, *a, **k)

        monkeypatch.setattr(Path, "open", spy)
        assert run_sensitivity(cfg, sens_copy).core_status == "PASSED"
        reads = [p for p in opened if not p.startswith(str(sens_copy / OUT_SUBDIR))]
        allowed = (str(sens_copy / "model"), str(sens_copy / "validation"))
        assert reads and all(p.startswith(allowed) for p in reads), [p for p in reads if not p.startswith(allowed)]
