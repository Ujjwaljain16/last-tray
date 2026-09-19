"""Pipeline outputs: run manifest, stage summary, pipeline controls, runtime summary, run log. No business logic.

Deterministic (byte-identical for identical inputs): stage_summary.csv and pipeline_controls.csv. They contain no timestamp, run id, timing or
path. Time-dependent by design: run_manifest.json (run id, start, end, elapsed), runtime_summary.json and run_log.jsonl. All are written
atomically, and any earlier pipeline output is removed before a run starts so a previous run's manifest can never look current.
"""
from __future__ import annotations

import csv
import hashlib
import json
import platform
import sys
import uuid
from pathlib import Path
from typing import Any

from src.config import Config
from src.fsutil import TMP_MARK, atomic_path, atomic_write_text
from src.ingest.hashing import digest_file
from src.pipeline.exit_codes import EXIT_TABLE
from src.pipeline.orchestrate import FAILED, PASSED, PipelineResult, StageRecord
from src.pipeline.stages import STAGE_ORDER

PIPELINE_VERSION = "1.0.0"
OUT_SUBDIR = "pipeline"
MANIFEST_JSON, STAGE_CSV, CONTROLS_CSV, RUNTIME_JSON, LOG_JSONL = "run_manifest.json", "stage_summary.csv", "pipeline_controls.csv", "runtime_summary.json", "run_log.jsonl"
DETERMINISTIC_FILES = (STAGE_CSV, CONTROLS_CSV)
ALL_FILES = (MANIFEST_JSON, STAGE_CSV, CONTROLS_CSV, RUNTIME_JSON, LOG_JSONL)


def new_run_id() -> str:
    return "run-" + uuid.uuid4().hex[:12]


def previous_output_hashes(out: Path) -> dict[str, dict[str, str]]:
    """{stage: {relative path: sha256}} from the last run manifest, or {} if there is none or it cannot be read. Read BEFORE the manifest is cleared."""
    m = _json(out / OUT_SUBDIR / MANIFEST_JSON)
    if not isinstance(m, dict):
        return {}
    try:
        return {s["stage"]: {o["path"]: o["sha256"] for o in s.get("outputs", [])} for s in m.get("stages", [])}
    except (KeyError, TypeError):
        return {}


def clear_pipeline_outputs(out: Path) -> None:
    d = out / OUT_SUBDIR
    if d.is_dir():
        for p in d.iterdir():
            if p.is_file() and (p.name in ALL_FILES or TMP_MARK in p.name):
                p.unlink()


def config_fingerprint(cfg_dir: Path) -> dict[str, Any]:
    """SHA-256 of each configuration file (line endings normalised) and of the set. Changing any approved decision changes it."""
    files = {}
    for p in sorted(Path(cfg_dir).glob("*.yml")):
        files[p.name] = hashlib.sha256(p.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    combined = hashlib.sha256("\n".join(f"{k}:{v}" for k, v in files.items()).encode("utf-8")).hexdigest()
    return {"sha256": combined, "files": files}


def _json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _sha(out: Path, rel: str) -> str | None:
    p = out / rel
    return digest_file(p).sha256 if p.is_file() else None


# ---- provenance chain ---------------------------------------------------------------------------------------------------------------------------
def provenance(out: Path, statuses: dict[str, str]) -> dict[str, Any]:
    """Walk the chain raw snapshot -> ingestion -> staging -> validation -> model -> metrics -> sensitivity through the identifiers and
    checksums each stage recorded, and re-derive every checksum from the file on disk. A link is PASS, FAIL, or NOT_CHECKED (stage not passed)."""
    ing = _json(out / "ingestion" / "ingestion_summary.json") or {}
    stg = _json(out / "staging" / "staging_summary.json") or {}
    val = _json(out / "validation" / "validation_summary.json") or {}
    mod = _json(out / "model" / "model_manifest.json") or {}
    met = _json(out / "metrics" / "metric_summary.json") or {}
    sen = _json(out / "evidence" / "sensitivity_summary.json") or {}
    ok = lambda s: statuses.get(s) in (PASSED, "REUSED", "NOT_RUN")
    links: list[dict[str, Any]] = []

    def link(name: str, needs: tuple[str, ...], expected: Any, actual: Any) -> None:
        if not all(ok(s) for s in needs):
            links.append({"link": name, "status": "NOT_CHECKED", "expected": None, "actual": None})
        else:
            links.append({"link": name, "status": "PASS" if expected is not None and expected == actual else "FAIL", "expected": expected, "actual": actual})

    fp = ing.get("input_fingerprint")
    snaps = {s["source"]: s["source_snapshot_id"] for s in ing.get("snapshots", [])}
    link("ingestion.input_fingerprint == staging.input_fingerprint", ("ingest", "stage"), fp, stg.get("input_fingerprint"))
    link("staging.input_fingerprint == validation.input_fingerprint", ("ingest", "stage", "validate"), fp, val.get("input_fingerprint"))
    link("validation.input_fingerprint == model.input_fingerprint", ("ingest", "stage", "validate", "model"), fp, mod.get("inputs", {}).get("input_fingerprint"))
    link("model.input_fingerprint == metrics.input_fingerprint", ("ingest", "stage", "validate", "model", "metrics"), fp, met.get("model_manifest_inputs", {}).get("input_fingerprint"))
    link("ingestion snapshot ids == staging snapshot ids", ("ingest", "stage"), snaps, stg.get("source_snapshot_ids"))
    link("staging snapshot ids == validation snapshot ids", ("ingest", "stage", "validate"), snaps, val.get("source_snapshot_ids"))
    link("validation snapshot ids == model snapshot ids", ("ingest", "stage", "validate", "model"), snaps, mod.get("inputs", {}).get("source_snapshot_ids"))
    link("model snapshot id == metrics snapshot id", ("ingest", "stage", "validate", "model", "metrics"), snaps.get("flavoria"), met.get("source_snapshot_id"))
    stg_actual = {n: _sha(out, f"staging/{n}") for n in stg.get("output_sha256", {})}
    link("staging recorded checksums == staging files on disk", ("stage",), stg.get("output_sha256"), stg_actual)
    link("validation's staging table checksums == staging files on disk", ("stage", "validate"), val.get("staging_table_sha256"), {n: _sha(out, f"staging/{n}") for n in val.get("staging_table_sha256", {})})
    link("validation recorded checksums == validation files on disk", ("validate",), val.get("output_sha256"), {n: _sha(out, f"validation/{n}") for n in val.get("output_sha256", {})})
    mi = mod.get("inputs", {})
    link("model's staging checksums == staging files on disk", ("stage", "model"), mi.get("staging_table_sha256"), {n: _sha(out, f"staging/{n}") for n in mi.get("staging_table_sha256", {})})
    link("model's validation checksums == validation files on disk", ("validate", "model"), mi.get("validation_output_sha256"), {n: _sha(out, f"validation/{n}") for n in mi.get("validation_output_sha256", {})})
    link("model's validation run id == validation run id", ("validate", "model"), val.get("run_id"), mi.get("validation_run_id"))
    tables = mod.get("tables", {})
    link("model manifest table checksums == canonical files on disk", ("model",), {n: t.get("sha256") for n, t in tables.items()}, {n: _sha(out, f"model/{n}.csv") for n in tables})
    link("metrics' validation run id == validation run id", ("validate", "model", "metrics"), val.get("run_id"), met.get("model_manifest_inputs", {}).get("validation_run_id"))
    link("metrics' model inputs == model manifest inputs", ("model", "metrics"), mi, met.get("model_manifest_inputs"))
    link("sensitivity core status == PASSED-equivalent (baseline reproduces the metrics)", ("metrics", "sensitivity"), "OK", "OK" if sen.get("core_status") in ("OK", "PASSED", "WARNING") and not sen.get("baseline_problems") else sen.get("core_status"))
    return {"chain": ["raw snapshot", "ingestion", "staging", "validation", "canonical model", "metrics", "sensitivity / evidence"], "input_fingerprint": fp, "source_snapshot_ids": snaps,
            "validation_run_id": val.get("run_id"), "links": links}


# ---- outputs ----------------------------------------------------------------------------------------------------------------------------------------
def _fingerprint(rec: StageRecord) -> str:
    return hashlib.sha256("\n".join(f"{o['path']}:{o['sha256']}" for o in rec.outputs).encode("utf-8")).hexdigest() if rec.outputs else ""


def _write_csv(path: Path, header: list[str], rows: list[list[Any]]) -> None:
    with atomic_path(path) as tmp, tmp.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)


def controls(result: PipelineResult, out: Path, prov: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []

    def add(cid: str, name: str, ok: bool | None, detail: str) -> None:
        rows.append({"control_id": cid, "control": name, "status": "INFO" if ok is None else "PASS" if ok else "FAIL", "detail": detail})

    names = [s.name for s in result.stages]
    add("P01", "stages are exactly ingest, stage, validate, model, metrics, sensitivity in that order", names == list(STAGE_ORDER), " > ".join(names))
    first_fail = next((i for i, s in enumerate(result.stages) if s.status == FAILED), None)
    if first_fail is None:
        after = []
    else:
        after = [s for s in result.stages[first_fail + 1:] if s.status == PASSED]
    add("P02", "no stage ran after a failed stage (gate held)", not after, "none ran after a failure" if not after else ", ".join(s.name for s in after))
    stale = [s.name for s in result.stages if s.status in ("BLOCKED", "INVALIDATED") and s.outputs]
    add("P03", "a blocked or invalidated stage has no outputs left (stale outputs removed)", not stale, "no stale outputs" if not stale else ", ".join(stale))
    mismatched = []
    for s in result.stages:
        for o in s.outputs:
            p = out / o["path"]
            if not p.is_file() or digest_file(p).sha256 != o["sha256"]:
                mismatched.append(o["path"])
    add("P04", "every recorded output hash matches the file on disk after the run", not mismatched, "all match" if not mismatched else ", ".join(mismatched[:5]))
    leftovers = sorted(p.name for p in out.rglob("*") if p.is_file() and TMP_MARK in p.name) if out.is_dir() else []
    add("P05", "no temporary (partially written) files remain", not leftovers, "none" if not leftovers else ", ".join(leftovers[:5]))
    checked = [l for l in prov["links"] if l["status"] != "NOT_CHECKED"]
    bad = [l["link"] for l in checked if l["status"] == "FAIL"]
    add("P06", "the provenance chain is unbroken (fingerprints, snapshot ids, checksums, run ids agree across stages)", not bad, f"{len(checked)} links checked" if not bad else "; ".join(bad))
    passed = [s for s in result.stages if s.status == PASSED]
    add("P07", "every stage that passed recorded at least one output", all(s.outputs for s in passed), f"{len(passed)} passed")
    ing = _json(out / "ingestion" / "ingestion_summary.json") or {}
    add("P08", "raw files were unchanged during ingestion", ing.get("raw_unchanged_during_run") is True if any(s.name == "ingest" and s.status == PASSED for s in result.stages) else None,
        "verified by ingestion" if ing.get("raw_unchanged_during_run") else "ingestion did not pass")
    add("P09", "weather-lane problems do not hide core results", None, "weather BLOCKED" if result.weather_blocked else "weather lane not blocked")
    add("P10", "network retrieval", None, "none: the pipeline has no download path; a missing raw source is a core failure naming the explicit fetch command")
    codes = {int(e[0]) for e in EXIT_TABLE}
    add("P11", "the exit code is one of the documented classes", result.exit_code in codes, f"exit {result.exit_code}")
    return rows


def write_pipeline_outputs(result: PipelineResult, cfg_dir: Path, out: Path, *, repo_root: Path, profile_memory: bool) -> dict[str, Any]:
    d = out / OUT_SUBDIR
    d.mkdir(parents=True, exist_ok=True)
    statuses = {s.name: s.status for s in result.stages}
    prov = provenance(out, statuses)
    ctrl = controls(result, out, prov)

    _write_csv(d / STAGE_CSV, ["stage", "status", "gate", "exit_class", "reason", "warnings", "errors", "output_files", "output_bytes", "outputs_sha256", "removed_outputs"],
               [[s.name, s.status, s.gate, "" if s.exit_class is None else s.exit_class, (s.reason or "").replace("\n", " "), s.warnings, s.errors, len(s.outputs),
                 sum(o["bytes"] for o in s.outputs), _fingerprint(s), len(s.cleaned)] for s in result.stages])
    _write_csv(d / CONTROLS_CSV, ["control_id", "control", "status", "detail"], [[c["control_id"], c["control"], c["status"], c["detail"]] for c in ctrl])

    manifest = {
        "run_id": result.run_id, "pipeline_version": PIPELINE_VERSION, "started_at": result.started_at, "finished_at": result.finished_at, "elapsed_s": result.elapsed_s,
        "target": result.target, "resume_from": result.resume_from, "exit_code": result.exit_code, "exit_meaning": next((e[2] for e in EXIT_TABLE if int(e[0]) == result.exit_code), ""),
        "weather_blocked": result.weather_blocked, "python": platform.python_version(), "offline": True,
        "config_fingerprint": config_fingerprint(cfg_dir), "provenance": prov,
        "stages": [{"stage": s.name, "status": s.status, "gate": s.gate, "exit_class": s.exit_class, "reason": s.reason, "counts": s.counts, "warnings": s.warnings, "errors": s.errors,
                    "elapsed_s": s.elapsed_s, "verifies": s.verifies, "removed_outputs": s.cleaned, "outputs": s.outputs} for s in result.stages],
        "controls": {"pass": sum(c["status"] == "PASS" for c in ctrl), "fail": sum(c["status"] == "FAIL" for c in ctrl), "info": sum(c["status"] == "INFO" for c in ctrl)},
    }
    atomic_write_text(d / MANIFEST_JSON, json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n")

    per_stage = [{"stage": s.name, "status": s.status, "elapsed_s": s.elapsed_s, "output_bytes": sum(o["bytes"] for o in s.outputs), "output_files": len(s.outputs),
                  "peak_python_memory_mb": s.peak_memory_mb} for s in result.stages]
    runtime = {"run_id": result.run_id, "total_elapsed_s": result.elapsed_s, "stages": per_stage, "total_output_bytes": sum(p["output_bytes"] for p in per_stage),
               "memory": "tracemalloc peak Python allocations per stage (MB)" if profile_memory else "not measured (re-run with --profile-memory)", "python": sys.version.split()[0], "platform": platform.platform()}
    atomic_write_text(d / RUNTIME_JSON, json.dumps(runtime, indent=2, sort_keys=True) + "\n")
    atomic_write_text(d / LOG_JSONL, "".join(json.dumps(e, sort_keys=True, ensure_ascii=False) + "\n" for e in result.log))
    return manifest
