"""The real pipeline end to end: manifest, provenance, determinism, idempotence, resume, failure injection, configuration safety, offline, atomic writes.

One full run is made once per session; tests that damage something work on a copy, so the shared run is never touched.
"""
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

from src.config import DEFAULT_CONFIG_DIR
from src.fsutil import TMP_MARK, atomic_write_text
from src.pipeline.report import ALL_FILES, DETERMINISTIC_FILES, config_fingerprint
from src.pipeline.run import main
from src.pipeline.stages import STAGE_ORDER, default_stages

REPO = Path(__file__).resolve().parents[1]
NON_DETERMINISTIC = {"ingestion/ingestion_run.json", "pipeline/run_manifest.json", "pipeline/runtime_summary.json", "pipeline/run_log.jsonl"}
STAGE_DIRS = {"ingest": "ingestion", "stage": "staging", "validate": "validation", "model": "model", "metrics": "metrics", "sensitivity": "evidence"}


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def tree(out: Path, skip=NON_DETERMINISTIC) -> dict[str, str]:
    return {p.relative_to(out).as_posix(): sha(p) for p in sorted(out.rglob("*")) if p.is_file() and p.relative_to(out).as_posix() not in skip}


def files_of(out: Path, stage: str) -> list[Path]:
    d = out / STAGE_DIRS[stage]
    return [p for p in d.rglob("*") if p.is_file()] if d.is_dir() else []


def manifest(out: Path) -> dict:
    return json.loads((out / "pipeline" / "run_manifest.json").read_text(encoding="utf-8"))


def stage_status(out: Path) -> dict[str, str]:
    with (out / "pipeline" / "stage_summary.csv").open(newline="", encoding="utf-8") as fh:
        return {r["stage"]: r["status"] for r in csv.DictReader(fh)}


def fake_repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    shutil.copytree(REPO / "data" / "raw", root / "data" / "raw")
    return root


@pytest.fixture(scope="session")
def full_run(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("pipeline_full") / "out"
    assert main(["--out", str(out)]) == 0
    return out


@pytest.fixture()
def work(full_run, tmp_path) -> Path:
    out = tmp_path / "work_out"
    shutil.copytree(full_run, out)
    return out


# ---- manifest ----------------------------------------------------------------------------------------------------------------------------------
def test_the_run_manifest_records_everything_the_brief_requires(full_run):
    m = manifest(full_run)
    assert m["run_id"].startswith("run-") and m["pipeline_version"] and m["started_at"] <= m["finished_at"] and m["elapsed_s"] >= 0
    assert m["exit_code"] == 0 and m["target"] == "sensitivity" and m["resume_from"] is None and m["offline"] is True
    assert list(m["provenance"]["source_snapshot_ids"]) == ["flavoria", "fmi_weather"] and m["provenance"]["input_fingerprint"]
    assert m["provenance"]["source_snapshot_ids"]["flavoria"].startswith("flavoria-")
    assert [s["stage"] for s in m["stages"]] == list(STAGE_ORDER)
    for s in m["stages"]:
        assert s["status"] == "PASSED" and s["elapsed_s"] >= 0 and s["outputs"] and s["counts"] and s["verifies"] and s["removed_outputs"] == []
        assert s["warnings"] >= 0 and s["errors"] >= 0
    assert m["controls"]["fail"] == 0 and m["config_fingerprint"]["sha256"]


def test_manifest_output_hashes_and_sizes_match_the_files_on_disk(full_run):
    recorded = {o["path"]: o for s in manifest(full_run)["stages"] for o in s["outputs"]}
    assert recorded, "the manifest must list outputs"
    for rel, o in recorded.items():
        p = full_run / rel
        assert sha(p) == o["sha256"] and p.stat().st_size == o["bytes"], rel
    on_disk = {p.relative_to(full_run).as_posix() for p in full_run.rglob("*") if p.is_file()}
    expected = set(recorded) | NON_DETERMINISTIC | {f"pipeline/{n}" for n in DETERMINISTIC_FILES}
    assert on_disk == expected, "every output file is in the manifest and nothing unlisted remains"


def test_manifest_row_counts_are_the_approved_ones(full_run):
    counts = {s["stage"]: s["counts"] for s in manifest(full_run)["stages"]}
    assert counts["stage"]["events"] == 12284 and counts["stage"]["weather_observations"] == 4516
    assert counts["model"]["rows_fact_dining_session"] > 0 and counts["metrics"]["metrics"] > 0 and counts["sensitivity"]["scenarios"] > 0


def test_config_fingerprint_matches_a_recomputation_and_moves_with_any_config_edit(full_run, config_copy):
    assert manifest(full_run)["config_fingerprint"] == config_fingerprint(DEFAULT_CONFIG_DIR)
    before = config_fingerprint(config_copy.dir)["sha256"]
    p = config_copy.dir / "populations.yml"
    p.write_text(p.read_text(encoding="utf-8") + "\n# a comment changes the fingerprint\n", encoding="utf-8")
    assert config_fingerprint(config_copy.dir)["sha256"] != before


def test_the_pipeline_output_set_is_exactly_the_five_documented_files(full_run):
    assert {p.name for p in (full_run / "pipeline").iterdir()} == set(ALL_FILES)
    assert not [p for p in full_run.rglob("*") if TMP_MARK in p.name], "no temporary file may remain"


def test_the_run_log_is_structured_jsonl_with_no_paths(full_run):
    lines = (full_run / "pipeline" / "run_log.jsonl").read_text(encoding="utf-8").splitlines()
    events = [json.loads(x) for x in lines]
    assert events[0]["event"] == "run_start" and events[-1]["event"] == "run_end" and events[-1]["exit_code"] == 0
    assert [e["stage"] for e in events if e["event"] == "stage_end"] == list(STAGE_ORDER)
    assert len({e["run_id"] for e in events}) == 1 and str(full_run) not in "\n".join(lines)


def test_runtime_summary_has_total_and_per_stage_time_and_sizes(full_run):
    r = json.loads((full_run / "pipeline" / "runtime_summary.json").read_text(encoding="utf-8"))
    assert [s["stage"] for s in r["stages"]] == list(STAGE_ORDER) and r["total_elapsed_s"] > 0
    assert all(s["output_bytes"] > 0 and s["elapsed_s"] >= 0 for s in r["stages"]) and r["total_output_bytes"] == sum(s["output_bytes"] for s in r["stages"])


# ---- provenance --------------------------------------------------------------------------------------------------------------------------------
def test_every_provenance_link_is_checked_and_passes(full_run):
    links = manifest(full_run)["provenance"]["links"]
    assert len(links) == 18 and {l["status"] for l in links} == {"PASS"}
    assert manifest(full_run)["provenance"]["chain"][0] == "raw snapshot" and manifest(full_run)["provenance"]["chain"][-1].startswith("sensitivity")


def test_pipeline_controls_all_pass(full_run):
    with (full_run / "pipeline" / "pipeline_controls.csv").open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert [r["control_id"] for r in rows] == [f"P{i:02d}" for i in range(1, 12)]
    assert {r["status"] for r in rows} <= {"PASS", "INFO"} and sum(r["status"] == "PASS" for r in rows) == 9


def test_the_sensitivity_stage_refuses_an_altered_canonical_table_on_its_own(work):
    """With no manifest to compare against, the stage's own check against the model manifest still refuses the altered table."""
    (work / "pipeline" / "run_manifest.json").unlink()
    p = work / "model" / "fact_dining_session.csv"
    p.write_bytes(p.read_bytes() + b"x")
    assert main(["--out", str(work), "--stages", "sensitivity", "--resume-from", "sensitivity"]) == 10


# ---- determinism, idempotence, resume ------------------------------------------------------------------------------------------------------------
def test_two_runs_in_the_same_directory_are_byte_identical_apart_from_run_metadata(full_run, tmp_path):
    out = tmp_path / "out"
    assert main(["--out", str(out)]) == 0
    first = tree(out)
    m1 = manifest(out)
    assert main(["--out", str(out)]) == 0
    assert tree(out) == first == tree(full_run), "a second real run must not change one byte of any deterministic output"
    m2 = manifest(out)
    assert m1["run_id"] != m2["run_id"] and [s["outputs"] for s in m1["stages"]] == [s["outputs"] for s in m2["stages"]]


def test_a_different_hash_seed_working_directory_and_output_directory_give_identical_outputs(full_run, tmp_path):
    other = tmp_path / "elsewhere"
    other.mkdir()
    out = tmp_path / "o2" / "deep"
    env = {**os.environ, "PYTHONHASHSEED": "12345", "PYTHONPATH": str(REPO)}
    r = subprocess.run([sys.executable, "-m", "src.pipeline.run", "--out", str(out), "--repo-root", str(REPO)], cwd=other, env=env, capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stderr
    assert tree(out) == tree(full_run)


def test_resuming_leaves_every_upstream_file_untouched_and_reproduces_the_downstream_ones(work):
    up = {p: (sha(p), p.stat().st_mtime_ns) for st in ("ingest", "stage", "validate") for p in files_of(work, st)}
    down = tree(work, NON_DETERMINISTIC | {f"pipeline/{n}" for n in DETERMINISTIC_FILES})
    assert main(["--out", str(work), "--resume-from", "model"]) == 0
    assert {p: (sha(p), p.stat().st_mtime_ns) for p in up} == up, "upstream artifacts must not be rewritten by a later-stage rerun"
    assert tree(work, NON_DETERMINISTIC | {f"pipeline/{n}" for n in DETERMINISTIC_FILES}) == down
    assert stage_status(work) == {**{s: "REUSED" for s in STAGE_ORDER[:3]}, **{s: "PASSED" for s in STAGE_ORDER[3:]}}


def test_a_single_stage_rerun_touches_only_that_stage(work):
    before = {p: p.stat().st_mtime_ns for st in STAGE_ORDER[:5] for p in files_of(work, st)}
    assert main(["--out", str(work), "--stages", "sensitivity", "--resume-from", "sensitivity"]) == 0
    assert {p: p.stat().st_mtime_ns for p in before} == before


def forget_manifest(out: Path) -> None:
    """Simulate a resume with no previous run manifest, so only the stage's own upstream verification can catch damage."""
    (out / "pipeline" / "run_manifest.json").unlink()


def test_resume_checks_reused_artifacts_against_the_last_run_manifest(work):
    p = work / "staging" / "stg_weighing_event.csv"
    p.write_bytes(p.read_bytes() + b"tampered\n")
    assert main(["--out", str(work), "--resume-from", "validate"]) == 4, "the reused staging stage no longer matches what the last run recorded"
    assert stage_status(work) == {"ingest": "REUSED", "stage": "FAILED", "validate": "BLOCKED", "model": "BLOCKED", "metrics": "BLOCKED", "sensitivity": "BLOCKED"}
    only(work, "ingest")


def test_resume_verifies_the_upstream_itself_even_with_no_manifest_to_compare_against(work):
    forget_manifest(work)
    p = work / "staging" / "stg_weighing_event.csv"
    p.write_bytes(p.read_bytes() + b"tampered\n")
    assert main(["--out", str(work), "--resume-from", "validate"]) == 7
    assert stage_status(work) == {"ingest": "REUSED", "stage": "REUSED", "validate": "FAILED", "model": "BLOCKED", "metrics": "BLOCKED", "sensitivity": "BLOCKED"}
    only(work, "ingest", "stage")


# ---- failure injection -----------------------------------------------------------------------------------------------------------------------------
def only(out: Path, *stages: str) -> None:
    for st in STAGE_ORDER:
        assert bool(files_of(out, st)) == (st in stages), f"{st}: expected {'outputs' if st in stages else 'no outputs'}"


def test_tampered_raw_archive_fails_at_ingest_and_nothing_downstream_survives(work, tmp_path):
    root = fake_repo(tmp_path)
    tar = root / "data" / "raw" / "flavoria" / "dataset_csv.tar"
    data = bytearray(tar.read_bytes())
    data[1000] ^= 0xFF
    tar.write_bytes(bytes(data))
    assert main(["--out", str(work), "--repo-root", str(root)]) == 4
    assert stage_status(work) == {"ingest": "FAILED", "stage": "BLOCKED", "validate": "BLOCKED", "model": "BLOCKED", "metrics": "BLOCKED", "sensitivity": "BLOCKED"}
    only(work, "ingest")
    assert manifest(work)["exit_code"] == 4 and manifest(work)["stages"][0]["reason"]


def test_missing_raw_archive_fails_clearly_downloads_nothing_and_removes_stale_outputs(work, tmp_path, capsys, no_network):
    root = fake_repo(tmp_path)
    (root / "data" / "raw" / "flavoria" / "dataset_csv.tar").unlink()
    assert main(["--out", str(work), "--repo-root", str(root)]) == 4
    err = capsys.readouterr().err
    assert "python -m src.pipeline.fetch --source" in err
    assert not (root / "data" / "raw" / "flavoria" / "dataset_csv.tar").exists()
    only(work, "ingest")


def test_a_missing_weather_lane_blocks_weather_outputs_only_and_exits_6(work, tmp_path):
    root = fake_repo(tmp_path)
    (root / "data" / "raw" / "weather" / "fmi_100949_20201012_20201018.xml").unlink()
    assert main(["--out", str(work), "--repo-root", str(root)]) == 6
    assert set(stage_status(work).values()) == {"PASSED"}, "the core gate stays open when only the weather lane is blocked"
    only(work, *STAGE_ORDER)
    assert not (work / "staging" / "stg_weather_observation.csv").exists() and not (work / "model" / "fact_weather.csv").exists()
    assert (work / "model" / "fact_dining_session.csv").is_file() and manifest(work)["weather_blocked"] is True and manifest(work)["exit_code"] == 6


def test_tampered_staging_table_fails_at_validate_when_only_the_stage_checks_it(work):
    forget_manifest(work)
    p = work / "staging" / "stg_weighing_event.csv"
    p.write_bytes(p.read_bytes() + b"tampered-row,1,2")
    assert main(["--out", str(work), "--resume-from", "validate"]) == 7
    only(work, "ingest", "stage")


def test_tampered_validation_summary_is_caught_at_validation_by_the_manifest_even_for_a_field_nobody_consumes(work):
    p = work / "validation" / "validation_summary.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    d["quarantine"]["events"] += 1
    p.write_text(json.dumps(d, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    assert main(["--out", str(work), "--resume-from", "model"]) == 7
    only(work, "ingest", "stage")


def test_a_forged_validation_summary_checksum_is_caught_at_model_when_only_the_stage_checks_it(work):
    forget_manifest(work)
    p = work / "validation" / "validation_summary.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    d["output_sha256"]["validation_issues.csv"] = "0" * 64
    p.write_text(json.dumps(d, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    assert main(["--out", str(work), "--resume-from", "model"]) == 8
    only(work, "ingest", "stage", "validate")


def test_tampered_canonical_table_fails_at_metrics_when_only_the_stage_checks_it_and_evidence_is_removed(work):
    forget_manifest(work)
    p = work / "model" / "fact_dining_session.csv"
    p.write_bytes(p.read_bytes() + b"tampered\n")
    assert main(["--out", str(work), "--resume-from", "metrics"]) == 9
    only(work, "ingest", "stage", "validate", "model")
    assert stage_status(work)["sensitivity"] == "BLOCKED"


def test_tampered_canonical_table_is_caught_at_the_model_by_the_manifest(work):
    p = work / "model" / "fact_dining_session.csv"
    p.write_bytes(p.read_bytes() + b"tampered\n")
    assert main(["--out", str(work), "--resume-from", "metrics"]) == 8
    only(work, "ingest", "stage", "validate")


def test_a_missing_canonical_table_fails_at_metrics(work):
    forget_manifest(work)
    (work / "model" / "fact_weighing_event.csv").unlink()
    assert main(["--out", str(work), "--resume-from", "metrics"]) == 9
    only(work, "ingest", "stage", "validate", "model")


def test_a_changed_metric_reference_fails_the_metric_stage_and_blocks_the_evidence(work, monkeypatch):
    import src.metrics.evaluate as ev
    monkeypatch.setattr(ev, "APPROVED_COUNTS", {**ev.APPROVED_COUNTS, "M5": (1697, 1700)})
    assert main(["--out", str(work), "--resume-from", "metrics"]) == 9
    assert stage_status(work)["metrics"] == "FAILED" and stage_status(work)["sensitivity"] == "BLOCKED"
    assert not files_of(work, "sensitivity")
    assert json.loads((work / "metrics" / "metric_summary.json").read_text(encoding="utf-8"))["failed_metrics"] == ["M5"], "the failure is recorded for inspection, never recalibrated away"


def test_an_invalid_sensitivity_registry_fails_at_sensitivity_with_exit_10(work, monkeypatch):
    """A scenario that recalculates the waste metric W1 violates the registry rules; the real validator must catch it."""
    from src.sensitivity.registry import SCENARIO_BY_ID
    spec = SCENARIO_BY_ID["G01"]
    original = spec.metrics_recalculated
    object.__setattr__(spec, "metrics_recalculated", (*original, "W1"))
    try:
        assert main(["--out", str(work), "--resume-from", "sensitivity"]) == 10
    finally:
        object.__setattr__(spec, "metrics_recalculated", original)
    assert stage_status(work)["sensitivity"] == "FAILED"
    assert files_of(work, "model") and files_of(work, "metrics"), "a sensitivity failure never removes the upstream stages"


def test_an_orchestration_failure_is_exit_11(work, monkeypatch):
    import src.pipeline.stages as st

    def boom(ctx):
        raise RuntimeError("unexpected")

    specs = default_stages()
    broken = tuple(s if s.name != "validate" else type(s)(s.name, boom, s.clean, s.outputs, s.verifies) for s in specs)
    monkeypatch.setattr("src.pipeline.run.default_stages", lambda: broken)
    assert main(["--out", str(work)]) == 11
    assert stage_status(work)["validate"] == "FAILED" and stage_status(work)["model"] == "BLOCKED"


# ---- configuration safety ----------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("edit", [
    ("timezone_overrides.yml", "offset_hours: 3", "offset_hours: 2"),
    ("timezone_overrides.yml", "offset_hours: 3", "offset_hours: 4"),
    ("thresholds.yml", "registered_export_session_ids_in_source", "all_session_ids"),
    ("thresholds.yml", "handling: QUARANTINE", "handling: FLAG"),
    ("thresholds.yml", "handling: FLAG", "handling: QUARANTINE"),
], ids=["tz+2", "tz+4", "m5-denominator", "quarantine-treatment-changed", "flag-rule-becomes-exclusion"])
def test_an_unapproved_decision_in_configuration_is_refused_before_anything_runs(config_copy, tmp_path, capsys, edit):
    config_copy.edit(*edit)
    out = tmp_path / "out"
    assert main(["--config-dir", str(config_copy.dir), "--out", str(out)]) == 2
    assert "configuration" in capsys.readouterr().err and not out.exists(), "a refused configuration must leave no outputs"


def test_automatic_network_retrieval_cannot_be_configured(config_copy, tmp_path, capsys):
    p = config_copy.dir / "sources.yml"
    p.write_text(p.read_text(encoding="utf-8") + "\nauto_fetch: true\n", encoding="utf-8")
    out = tmp_path / "out"
    assert main(["--config-dir", str(config_copy.dir), "--out", str(out)]) == 2
    assert "retriev" in capsys.readouterr().err.lower() and not out.exists()


# ---- offline -----------------------------------------------------------------------------------------------------------------------------------
def test_the_full_pipeline_makes_no_network_call_at_all(tmp_path, no_network, monkeypatch):
    import urllib.request

    def refuse(*a, **k):
        raise AssertionError("urllib used during the offline pipeline")

    monkeypatch.setattr(urllib.request, "urlopen", refuse)
    assert main(["--stages", "all", "--out", str(tmp_path / "out")]) == 0


NETWORK_MODULES = {"urllib", "urllib.request", "http", "http.client", "requests", "socket", "ftplib", "httpx", "aiohttp", "smtplib"}


@pytest.mark.parametrize("module", ["run", "orchestrate", "stages", "report", "describe", "exit_codes"])
def test_no_orchestration_module_imports_a_network_library(module):
    import ast
    tree_ = ast.parse((REPO / "src" / "pipeline" / f"{module}.py").read_text(encoding="utf-8"))
    names = {n.name for node in ast.walk(tree_) if isinstance(node, ast.Import) for n in node.names} | {node.module for node in ast.walk(tree_) if isinstance(node, ast.ImportFrom) and node.module}
    assert not any(n == m or n.startswith(m + ".") for n in names for m in NETWORK_MODULES), names


# ---- atomic outputs ----------------------------------------------------------------------------------------------------------------------------
def test_a_failed_atomic_write_keeps_the_previous_file_and_leaves_no_temporary(tmp_path):
    target = tmp_path / "a.json"
    atomic_write_text(target, "old\n")
    import src.fsutil as fsutil
    real = fsutil.os.replace
    fsutil.os.replace = lambda *a, **k: (_ for _ in ()).throw(OSError("disk full"))    # noqa: E731
    try:
        with pytest.raises(OSError):
            atomic_write_text(target, "new\n")
    finally:
        fsutil.os.replace = real
    assert target.read_text() == "old\n" and [p.name for p in tmp_path.iterdir()] == ["a.json"]


def test_a_writer_that_fails_halfway_never_leaves_a_truncated_csv(tmp_path):
    from src.ingest.manifest import write_csv
    target = tmp_path / "t.csv"
    write_csv(target, [{"a": 1}, {"a": 2}], ["a"])
    good = target.read_bytes()

    def rows():
        yield {"a": 9}
        raise RuntimeError("crash mid-write")

    with pytest.raises(RuntimeError):
        write_csv(target, rows(), ["a"])
    assert target.read_bytes() == good and [p.name for p in tmp_path.iterdir()] == ["t.csv"]


def test_an_unwritable_run_manifest_is_exit_11_and_never_a_partial_manifest(tmp_path, monkeypatch):
    import src.fsutil as fsutil
    real = fsutil.os.replace

    def flaky(src, dst, *a, **k):
        if Path(dst).name == "run_manifest.json":
            raise OSError("cannot write manifest")
        return real(src, dst, *a, **k)

    monkeypatch.setattr(fsutil.os, "replace", flaky)
    out = tmp_path / "out"
    assert main(["--out", str(out), "--stages", "ingest"]) == 11
    assert not (out / "pipeline" / "run_manifest.json").exists() and not [p for p in out.rglob("*") if TMP_MARK in p.name]


def test_a_previous_runs_manifest_never_survives_into_a_run_that_fails_to_write_its_own(work, monkeypatch):
    assert (work / "pipeline" / "run_manifest.json").is_file()
    import src.pipeline.run as runmod
    monkeypatch.setattr(runmod, "write_pipeline_outputs", lambda *a, **k: (_ for _ in ()).throw(OSError("no")))
    assert main(["--out", str(work), "--stages", "ingest"]) == 11
    assert not (work / "pipeline" / "run_manifest.json").exists()
