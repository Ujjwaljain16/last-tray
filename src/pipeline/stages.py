"""The six pipeline stages as uniform, gated units. This module ORCHESTRATES existing logic: each adapter calls the stage's own runner and
translates its result into a StageReport. No business rule lives here.

Every stage verifies its own upstream contract when it runs (checksums, headers, row counts, run ids); nothing is trusted because a file
exists. Each stage also has a cleanup function that removes exactly its own deterministic outputs; the orchestrator calls it when the stage's
gate is closed, so a stale output can never survive a failed upstream dependency.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from src.config import Config
from src.fsutil import TMP_MARK
from src.ingest.handoff import HandoffError, VerifiedReader, load_handoff
from src.ingest.hashing import digest_file
from src.ingest.ingest import run_ingestion, utc_now, write_run_record
from src.ingest.manifest import DETERMINISTIC_FILES as INGESTION_FILES, OUT_SUBDIR as INGESTION_DIR
from src.ingest.model import LaneOutcome
from src.metrics.evaluate import DETERMINISTIC_FILES as METRIC_FILES, MetricContractError, OUT_SUBDIR as METRIC_DIR, run_metrics
from src.model.build import DETERMINISTIC_FILES as MODEL_FILES, OUT_SUBDIR as MODEL_DIR, run_model
from src.pipeline.describe import (describe, describe_failed, describe_metrics, describe_model, describe_sensitivity, describe_staging, describe_validation)
from src.sensitivity.evidence import SensitivityError
from src.sensitivity.stage import DETERMINISTIC_FILES as SENS_FILES, OUT_SUBDIR as SENS_DIR, run_sensitivity
from src.stage.stage import DETERMINISTIC_FILES as STAGING_FILES, OUT_SUBDIR as STAGING_DIR, run_staging
from src.validate.validate import DETERMINISTIC_FILES as VALIDATION_FILES, OUT_SUBDIR as VALIDATION_DIR, run_validation

STAGE_ORDER = ("ingest", "stage", "validate", "model", "metrics", "sensitivity")


@dataclass(frozen=True)
class Context:
    cfg: Config
    out: Path
    repo_root: Path


@dataclass
class StageReport:
    status: str                              # PASSED | FAILED
    reason: str | None = None
    weather_blocked: bool = False
    orchestration_failure: bool = False      # an unexpected exception, not a stage's own verdict
    counts: dict[str, Any] = field(default_factory=dict)
    warnings: int = 0
    errors: int = 0
    console: str = ""


@dataclass(frozen=True)
class StageSpec:
    name: str
    run: Callable[[Context], StageReport]
    clean: Callable[[Path], list[str]]
    outputs: Callable[[Path], list[Path]]
    verifies: str                            # what the stage checks about its upstream before it will run


# ---- helpers ------------------------------------------------------------------------------------------------------------------------------------
def _files(out: Path, subdir: str, names) -> list[Path]:
    return [out / subdir / n for n in names if (out / subdir / n).is_file()]


def _cleaner(subdir: str, names) -> Callable[[Path], list[str]]:
    def clean(out: Path) -> list[str]:
        d = out / subdir
        removed = []
        for n in names:
            p = d / n
            if p.is_file():
                p.unlink()
                removed.append(f"{subdir}/{n}")
        for p in sorted(d.rglob("*")) if d.is_dir() else []:
            if p.is_file() and TMP_MARK in p.name:
                p.unlink()
                removed.append(f"{subdir}/{p.relative_to(d).as_posix()}")
        return sorted(removed)

    return clean


def stage_fingerprint(spec: StageSpec, out: Path) -> str:
    """A hash of the stage's current deterministic outputs (name and content); equal fingerprints mean unchanged outputs."""
    import hashlib
    h = hashlib.sha256()
    for p in sorted(spec.outputs(out)):
        h.update(p.relative_to(out).as_posix().encode("utf-8") + b"\0" + digest_file(p).sha256.encode("ascii") + b"\0")
    return h.hexdigest()


# ---- adapters -----------------------------------------------------------------------------------------------------------------------------------
def _ingest(ctx: Context) -> StageReport:
    started = utc_now()
    result, hashes = run_ingestion(ctx.cfg, ctx.repo_root, ctx.out)
    write_run_record(result, ctx.out, hashes, started, utc_now())
    levels = Counter(m.level.value for m in result.messages)
    failed = result.core_outcome is LaneOutcome.FAILED
    first_error = next((m.text for m in result.messages if m.level.value == "ERROR"), "core lane failed")
    statuses = Counter(a.status.value for a in result.artifacts)
    return StageReport("FAILED" if failed else "PASSED", first_error if failed else None, result.context_outcome is LaneOutcome.BLOCKED,
                       counts={"artifacts": len(result.artifacts), **{f"artifacts_{k.lower()}": v for k, v in sorted(statuses.items())}},
                       warnings=levels.get("WARNING", 0), errors=levels.get("ERROR", 0), console=describe(result))


def _stage(ctx: Context) -> StageReport:
    try:
        handoff = load_handoff(ctx.out / INGESTION_DIR / "staging_handoff.json")
        res = run_staging(ctx.cfg, VerifiedReader(ctx.repo_root, handoff), ctx.out)
    except HandoffError as exc:
        return StageReport("FAILED", str(exc), console=describe_failed("stage", str(exc)), errors=1)
    levels = Counter(m.level.value for m in res.messages)
    failed = res.core is LaneOutcome.FAILED
    ev = res.summary.get("events", {})
    return StageReport("FAILED" if failed else "PASSED", next((m.text for m in res.messages if m.level.value == "ERROR"), "core staging failed") if failed else None,
                       res.context is LaneOutcome.BLOCKED, counts={"events": ev.get("rows", 0), "weather_observations": res.summary.get("weather", {}).get("rows", 0)},
                       warnings=levels.get("WARNING", 0), errors=levels.get("ERROR", 0), console=describe_staging(res))


def _validate(ctx: Context) -> StageReport:
    res = run_validation(ctx.cfg, ctx.out)
    failed = res.core_status == "BLOCKED"
    sev = res.summary.get("issues", {}).get("by_severity", {}) if res.summary else {}
    counts = {"findings": res.summary.get("issues", {}).get("total", 0), "quarantined_session_keys": res.summary.get("quarantine", {}).get("session_keys", 0),
              "reconciliation_checks": res.summary.get("reconciliation", {}).get("checks", 0)} if res.summary else {}
    reason = res.error or ("reconciliation failed: " + ", ".join(res.summary.get("reconciliation", {}).get("failed_checks", [])) if failed else None)
    return StageReport("FAILED" if failed else "PASSED", reason if failed else None, res.weather_status == "BLOCKED", counts=counts,
                       warnings=sev.get("WARN", 0), errors=sev.get("ERROR", 0), console=describe_validation(res))


def _model(ctx: Context) -> StageReport:
    res = run_model(ctx.cfg, ctx.out)
    failed = res.core_status == "BLOCKED"
    controls = res.manifest.get("controls", {}) if res.manifest else {}
    return StageReport("FAILED" if failed else "PASSED", res.error if failed else None, res.weather_status == "BLOCKED",
                       counts={f"rows_{k}": v for k, v in res.counts.items()}, warnings=controls.get("warn", 0), errors=controls.get("fail", 0), console=describe_model(res))


def _metrics(ctx: Context) -> StageReport:
    try:
        res = run_metrics(ctx.cfg, ctx.out)
    except MetricContractError as exc:
        _cleaner(METRIC_DIR, METRIC_FILES)(ctx.out)
        return StageReport("FAILED", f"metric contract violation: {exc}", console=describe_failed("metrics", str(exc)), errors=1)
    failed = res.core_status in ("BLOCKED", "FAILED")
    controls = res.summary.get("controls", {}) if res.summary else {}
    reason = res.error or ("metrics failed their contract: " + ", ".join(res.summary.get("failed_metrics", []) + controls.get("failed_checks", [])) if failed else None)
    return StageReport("FAILED" if failed else "PASSED", reason if failed else None, res.weather_status == "BLOCKED",
                       counts={"metrics": len(res.rows), "controls": controls.get("checks", 0)}, errors=controls.get("fail", 0) + len(res.summary.get("failed_metrics", [])),
                       console=describe_metrics(res))


def _sensitivity(ctx: Context) -> StageReport:
    try:
        res = run_sensitivity(ctx.cfg, ctx.out)
    except SensitivityError as exc:
        _cleaner(SENS_DIR, SENS_FILES)(ctx.out)
        return StageReport("FAILED", str(exc), console=describe_failed("sensitivity", str(exc)), errors=1)
    failed = res.core_status in ("BLOCKED", "FAILED")
    controls = res.summary.get("controls", {}) if res.summary else {}
    reason = res.error or ("; ".join(res.summary.get("baseline_problems", []) + res.summary.get("phase2_mismatches", [])) or "controls failed") if failed else None
    return StageReport("FAILED" if failed else "PASSED", reason, False,
                       counts={"scenarios": res.summary.get("scenarios", {}).get("registered", 0), "controls": controls.get("checks", 0)} if res.summary else {},
                       errors=controls.get("fail", 0), console=describe_sensitivity(res))


def default_stages() -> tuple[StageSpec, ...]:
    return (
        StageSpec("ingest", _ingest, lambda out: [], lambda out: _files(out, INGESTION_DIR, INGESTION_FILES), "the pinned raw archive and weather files (size, MD5, SHA-256, row counts, schema, timezone-override scope)"),
        StageSpec("stage", _stage, _cleaner(STAGING_DIR, STAGING_FILES), lambda out: _files(out, STAGING_DIR, STAGING_FILES), "the ingestion handoff, and the SHA-256 of every raw member it reads"),
        StageSpec("validate", _validate, _cleaner(VALIDATION_DIR, VALIDATION_FILES), lambda out: _files(out, VALIDATION_DIR, VALIDATION_FILES), "each staging table against the checksum, header and row count staging recorded"),
        StageSpec("model", _model, _cleaner(MODEL_DIR, MODEL_FILES), lambda out: _files(out, MODEL_DIR, MODEL_FILES), "staging tables and every validation output against their recorded checksums and run id"),
        StageSpec("metrics", _metrics, _cleaner(METRIC_DIR, METRIC_FILES), lambda out: _files(out, METRIC_DIR, METRIC_FILES), "each canonical table against the model manifest (checksum, header, row count, validation run id)"),
        StageSpec("sensitivity", _sensitivity, _cleaner(SENS_DIR, SENS_FILES), lambda out: _files(out, SENS_DIR, SENS_FILES), "the canonical tables against the model manifest, and the frozen baseline against the approved package"),
    )
