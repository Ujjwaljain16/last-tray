"""The orchestrator: runs the six stages in order behind explicit gates. It contains no business logic.

Gate rule. A stage runs only if the stage before it PASSED (or was resumed from). If a stage FAILS, every later stage is BLOCKED: it is not
run and its stale outputs are removed (whether or not it was requested), so an earlier run's output can never be presented as current. If a
stage re-runs and its outputs CHANGED, later stages that are not re-run in this invocation are invalidated the same way. A weather-lane
problem never closes the gate and never hides a core failure: it only changes the exit code when everything else passed.

Resuming (`resume_from`) re-runs a later stage against artifacts already on disk; the stage verifies those artifacts itself (checksums,
headers, row counts, run ids). Nothing is skipped because a file exists.
"""
from __future__ import annotations

import time
import tracemalloc
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence

from src.ingest.hashing import digest_file
from src.pipeline.describe import describe_blocked, describe_failed
from src.pipeline.exit_codes import STAGE_EXIT, ExitCode
from src.pipeline.stages import STAGE_ORDER, Context, StageReport, StageSpec, stage_fingerprint

PASSED, FAILED, BLOCKED, NOT_RUN, REUSED, INVALIDATED = "PASSED", "FAILED", "BLOCKED", "NOT_RUN", "REUSED", "INVALIDATED"


class OrchestrationError(Exception):
    """The pipeline was asked to run in an order or a way its contract forbids."""


@dataclass
class StageRecord:
    name: str
    status: str
    gate: str
    exit_class: int | None = None
    reason: str | None = None
    counts: dict[str, Any] = field(default_factory=dict)
    warnings: int = 0
    errors: int = 0
    elapsed_s: float = 0.0
    peak_memory_mb: float | None = None
    outputs: list[dict[str, Any]] = field(default_factory=list)      # deterministic outputs after the stage: relative path, sha256, bytes
    cleaned: list[str] = field(default_factory=list)                 # outputs removed by this stage's cleanup
    weather_blocked: bool = False
    verifies: str = ""
    console: str = ""


@dataclass
class PipelineResult:
    run_id: str
    started_at: str
    finished_at: str
    target: str
    resume_from: str | None
    stages: list[StageRecord]
    exit_code: int
    weather_blocked: bool
    elapsed_s: float
    log: list[dict[str, Any]] = field(default_factory=list)

    @property
    def first_failure(self) -> StageRecord | None:
        return next((s for s in self.stages if s.status == FAILED), None)


class RunLogger:
    """Structured events (one JSON-able dict each): run, stage, status, counts, reason. Never per-row and never a path."""

    def __init__(self, run_id: str, sink: Callable[[dict[str, Any]], None] | None = None, clock: Callable[[], str] | None = None):
        self.run_id, self.events, self._sink, self._clock = run_id, [], sink, clock or utc_stamp

    def emit(self, event: str, stage: str | None = None, status: str | None = None, **fields: Any) -> None:
        record = {"ts": self._clock(), "run_id": self.run_id, "event": event, "stage": stage, "status": status, **{k: v for k, v in fields.items() if v not in (None, {}, [])}}
        self.events.append(record)
        if self._sink:
            self._sink(record)


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def validate_order(specs: Sequence[StageSpec]) -> None:
    names = [s.name for s in specs]
    if names != list(STAGE_ORDER):
        raise OrchestrationError(f"stages must be exactly {list(STAGE_ORDER)} in that order, got {names}")


def _outputs(spec: StageSpec, out: Path) -> list[dict[str, Any]]:
    rows = []
    for p in sorted(spec.outputs(out)):
        rows.append({"path": p.relative_to(out).as_posix(), "sha256": digest_file(p).sha256, "bytes": p.stat().st_size})
    return rows


def _changed_since_last_run(stage: str, outs: list[dict[str, Any]], previous: dict[str, dict[str, str]]) -> list[str]:
    """Files of a reused stage that differ from what the last run manifest recorded (empty if that manifest said nothing about the stage)."""
    recorded = previous.get(stage)
    if not recorded:
        return []
    now = {o["path"]: o["sha256"] for o in outs}
    return sorted(p for p in set(recorded) | set(now) if recorded.get(p) != now.get(p))


def run_pipeline(specs: Sequence[StageSpec], ctx: Context, *, target: str, resume_from: str | None = None, run_id: str, logger: RunLogger | None = None,
                 profile_memory: bool = False, echo: Callable[[str], None] | None = None,
                 previous: dict[str, dict[str, str]] | None = None) -> PipelineResult:
    validate_order(specs)
    previous_hashes = previous or {}
    names = [s.name for s in specs]
    if target not in names or (resume_from is not None and resume_from not in names):
        raise OrchestrationError(f"unknown stage: target={target!r} resume_from={resume_from!r}")
    t_idx, r_idx = names.index(target), (names.index(resume_from) if resume_from else 0)
    if r_idx > t_idx:
        raise OrchestrationError(f"cannot resume from {resume_from!r}: it comes after the target {target!r}")
    log = logger or RunLogger(run_id)
    say = echo or (lambda text: None)
    started_at, t0 = utc_stamp(), time.perf_counter()
    log.emit("run_start", status="STARTED", target=target, resume_from=resume_from)

    records: list[StageRecord] = []
    first_failure: StageRecord | None = None
    upstream_changed = False
    weather_blocked = False
    prev: StageRecord | None = None

    for i, spec in enumerate(specs):
        gate = "open" if prev is None else f"{prev.name} {prev.status}"
        if i < r_idx:
            outs = _outputs(spec, ctx.out)
            changed = _changed_since_last_run(spec.name, outs, previous_hashes)
            if changed:                                     # a reused artifact no longer matches what the last run manifest recorded: untrusted
                cleaned = spec.clean(ctx.out)
                reason = "reused outputs changed since the last run manifest: " + ", ".join(changed[:5])
                rec = StageRecord(spec.name, FAILED, "resumed: checked against the last run manifest", exit_class=int(STAGE_EXIT[spec.name]), reason=reason, errors=1, cleaned=cleaned,
                                  verifies=spec.verifies, console=describe_failed(spec.name, reason))
                log.emit("stage_reused_mismatch", spec.name, FAILED, reason=reason, removed=len(cleaned))
                say(rec.console)
                first_failure = rec
            else:
                rec = StageRecord(spec.name, REUSED, "resumed: verified by the first stage that runs" + ("; matches the last run manifest" if spec.name in previous_hashes else ""),
                                  verifies=spec.verifies, outputs=outs)
                log.emit("stage_reused", spec.name, REUSED)
            records.append(rec)
            prev = rec
            continue
        if i > t_idx:
            if first_failure is not None or upstream_changed:
                cleaned = spec.clean(ctx.out)
                status, why = (BLOCKED, f"upstream {first_failure.name} FAILED") if first_failure else (INVALIDATED, "an upstream stage re-ran with changed outputs")
                rec = StageRecord(spec.name, status, gate, reason=why, cleaned=cleaned, verifies=spec.verifies)
                log.emit("cleanup", spec.name, status, reason=why, removed=len(cleaned))
            else:
                rec = StageRecord(spec.name, NOT_RUN, gate, verifies=spec.verifies, outputs=_outputs(spec, ctx.out))
            records.append(rec)
            continue
        if first_failure is not None:                       # gate closed: do not run; remove stale outputs
            cleaned = spec.clean(ctx.out)
            reason = first_failure.reason or "failed"
            rec = StageRecord(spec.name, BLOCKED, gate, reason=f"upstream {first_failure.name} FAILED", cleaned=cleaned, verifies=spec.verifies,
                              console=describe_blocked(spec.name, first_failure.name, reason))
            log.emit("stage_blocked", spec.name, BLOCKED, upstream=first_failure.name, reason=reason, removed=len(cleaned))
            say(rec.console)
            records.append(rec)
            prev = rec
            continue

        before = stage_fingerprint(spec, ctx.out)
        log.emit("stage_start", spec.name, "RUNNING", gate=gate)
        if profile_memory:
            tracemalloc.start()
        s0 = time.perf_counter()
        cleaned: list[str] = []
        try:
            report = spec.run(ctx)
        except Exception as exc:                            # an unexpected failure is an orchestration failure, and its outputs are not trusted
            cleaned = spec.clean(ctx.out)
            reason = f"{type(exc).__name__}: {exc}"
            report = StageReport(FAILED, reason, orchestration_failure=True, console=describe_failed(spec.name, reason), errors=1)
        elapsed = time.perf_counter() - s0
        peak = None
        if profile_memory:
            peak = round(tracemalloc.get_traced_memory()[1] / 1_000_000, 1)
            tracemalloc.stop()
        rec = StageRecord(spec.name, report.status, gate, reason=report.reason, counts=report.counts, warnings=report.warnings, errors=report.errors,
                          elapsed_s=round(elapsed, 3), peak_memory_mb=peak, outputs=_outputs(spec, ctx.out), cleaned=cleaned, weather_blocked=report.weather_blocked,
                          verifies=spec.verifies, console=report.console)
        if report.status == FAILED:
            rec.exit_class = int(ExitCode.ORCHESTRATION if report.orchestration_failure else STAGE_EXIT[spec.name])
            first_failure = rec
        weather_blocked = weather_blocked or report.weather_blocked
        upstream_changed = upstream_changed or stage_fingerprint(spec, ctx.out) != before
        log.emit("stage_end", spec.name, report.status, elapsed_s=rec.elapsed_s, counts=report.counts, warnings=report.warnings, errors=report.errors,
                 reason=report.reason if report.status == FAILED else None, weather="BLOCKED" if report.weather_blocked else None)
        say(rec.console)
        records.append(rec)
        prev = rec

    if first_failure is not None:
        exit_code = int(first_failure.exit_class)
    elif weather_blocked:
        exit_code = int(ExitCode.WEATHER)
    else:
        exit_code = int(ExitCode.OK)
    finished_at, elapsed_total = utc_stamp(), time.perf_counter() - t0
    log.emit("run_end", status="OK" if exit_code == 0 else "FAILED" if first_failure else "WEATHER_BLOCKED", exit_code=exit_code, elapsed_s=round(elapsed_total, 3))
    return PipelineResult(run_id, started_at, finished_at, target, resume_from, records, exit_code, weather_blocked, round(elapsed_total, 3), log.events)
