"""Console descriptions of each stage result: the human-readable text the CLI prints (kept identical across the WP8 refactor)."""
from __future__ import annotations

from src.config import Config
from src.ingest.model import IngestionResult, LaneOutcome
from src.metrics.evaluate import MetricsResult
from src.model.build import ModelResult
from src.sensitivity.stage import SensitivityResult
from src.stage.stage import StagingResult
from src.validate.validate import ValidationResult

TITLES = {"ingest": "Ingestion", "stage": "Staging (verified reads only)", "validate": "Validation (verified staging only)",
          "model": "Canonical model (verified inputs only)", "metrics": "Metrics (canonical model only)", "sensitivity": "Sensitivity analysis (canonical model only)"}


def describe_failed(stage: str, reason: str) -> str:
    """A stage that could not complete and produced no result object (an unexpected exception or an unreadable handoff)."""
    return "\n".join([TITLES[stage], "  core lane   : FAILED", f"  FAILED: {reason}"])


def describe_blocked(stage: str, upstream: str, reason: str) -> str:
    """A stage whose gate is closed: it was not run, and its stale outputs were removed."""
    return "\n".join([TITLES[stage], "  core lane   : BLOCKED", f"  BLOCKED: upstream stage {upstream!r} failed ({reason}); {stage} was not run and its stale outputs were removed"])


def summarise(cfg: Config) -> str:
    t, tz, pops, src = cfg.thresholds, cfg.timezone, cfg.populations, cfg.sources
    return "\n".join([
        "Configuration OK",
        f"  populations : {', '.join(f'{r.display_name} ({r.role})' for r in pops.rules)}; never pooled",
        f"  thresholds  : {len(t.rules)} rules approved {t.approved_on}; volume flags flag-only",
        f"  timezone    : {len(tz.overrides)} file-specific override(s): "
        + ", ".join(f"{o.filename} (+{o.offset_hours}h, source_confirmed={o.source_confirmed})" for o in tz.overrides.values()),
        f"  flavoria    : {len(src.flavoria.members)} member files, {src.flavoria.expected_total_rows:,} rows expected, {src.flavoria.license}",
        f"  weather     : FMISID {src.weather.fmisid}, {src.weather.expected_hours:,} hours expected, r_1h = {src.weather.r_1h_convention}, {src.weather.license}",
        "  source gaps : " + ", ".join(f"{g.name} [{g.status}]" for g in src.gaps.values()),
    ])


def describe(result: IngestionResult) -> str:
    counts: dict[str, int] = {}
    for a in result.artifacts:
        counts[a.status.value] = counts.get(a.status.value, 0) + 1
    lines = ["Ingestion", *(f"  {n:<32}{s}" for n, s in result.steps)]
    lines.append("  artifacts: " + ", ".join(f"{v} {k}" for k, v in sorted(counts.items())))
    lines.append(f"  input fingerprint: {result.input_fingerprint}")
    lines.append(f"  core lane   : {result.core_outcome.value}")
    lines.append(f"  context lane: {result.context_outcome.value}")
    for m in result.messages:
        if m.level.value != "INFO":
            lines.append(f"  {m.level.value} {m.code}: {m.text}")
    return "\n".join(lines)


def describe_staging(res: StagingResult) -> str:
    ev = res.summary.get("events", {})
    lines = ["Staging (verified reads only)", f"  core lane   : {res.core.value}", f"  context lane: {res.context.value}"]
    if res.core is LaneOutcome.OK:
        lines.append(f"  events staged: {ev['rows']:,}  by population: {ev['by_population']}")
        lines.append(f"  sessions: {ev['distinct_session_ids']:,} ids / {ev['distinct_session_keys']:,} (session_id, population) keys; in both populations: {ev['session_ids_present_in_both_populations']}")
        lines.append(f"  timezone handling: {ev['by_timezone_handling']}")
    if res.context is LaneOutcome.OK:
        lines.append(f"  weather observations staged: {res.summary['weather']['rows']:,}")
    for m in res.messages:
        lines.append(f"  {m.level.value} {m.code}: {m.text}")
    return "\n".join(lines)


def describe_validation(res: ValidationResult) -> str:
    if res.error:
        return f"Validation (verified staging only)\n  core lane   : BLOCKED\n  BLOCKED: {res.error}"
    s = res.summary
    sev, q, r = s["issues"]["by_severity"], s["quarantine"], s["reconciliation"]
    return "\n".join([
        "Validation (verified staging only)", f"  core lane   : {res.core_status}", f"  weather lane: {res.weather_status}", f"  run id      : {res.run_id}",
        f"  findings    : {s['issues']['total']:,} (ERROR {sev['ERROR']}, WARN {sev['WARN']}, INFO {sev['INFO']})",
        f"  quarantine  : {q['session_keys']} session keys ({', '.join(q['session_ids']) or 'none'}), {q['events']} events; kept, listed, never deleted",
        f"  reconciliation: {r['pass']} pass, {r['warn']} warn, {r['fail']} fail, {r['info']} info" + (f"; FAILED: {', '.join(r['failed_checks'])}" if r["fail"] else "")])


def describe_model(res: ModelResult) -> str:
    if res.error and not res.tables:
        return "\n".join(["Canonical model (verified inputs only)", f"  core lane   : {res.core_status}", f"  BLOCKED: {res.error}"])
    c = res.manifest["controls"]
    lines = ["Canonical model (verified inputs only)", f"  core lane   : {res.core_status}", f"  weather lane: {res.weather_status}",
             "  tables      : " + ", ".join(f"{n} {t['rows']:,}" for n, t in res.manifest["tables"].items()),
             f"  controls    : {c['pass']} pass, {c['warn']} warn, {c['fail']} fail, {c['info']} info" + (f"; FAILED: {', '.join(c['failed_checks'])}" if c["fail"] else "")]
    if res.error:
        lines.append(f"  BLOCKED: {res.error}")
    return "\n".join(lines)


def describe_metrics(res: MetricsResult) -> str:
    if res.error:
        return "\n".join(["Metrics (canonical model only)", f"  core lane   : {res.core_status}", f"  BLOCKED: {res.error}"])
    lines = ["Metrics (canonical model only)", f"  core lane   : {res.core_status}", f"  weather lane: {res.weather_status}"]
    lines += [f"  {r['metric_id']:<4}{r['value_display']:<22}{r['status']:<8}{r['metric_name']} [{r['population']}]" for r in res.rows]
    c = res.summary["controls"]
    lines.append(f"  controls    : {c['pass']} pass, {c['fail']} fail, {c['info']} info" + (f"; FAILED: {', '.join(c['failed_checks'])}" if c["fail"] else ""))
    if res.summary["failed_metrics"]:
        lines.append(f"  FAILED metrics: {', '.join(res.summary['failed_metrics'])}: " + "; ".join(f"{m}: {'; '.join(p)}" for m, p in res.summary["problems"].items()))
    return "\n".join(lines)


def describe_sensitivity(res: SensitivityResult) -> str:
    if res.error:
        return "\n".join(["Sensitivity analysis (canonical model only)", f"  core lane   : {res.core_status}", f"  BLOCKED: {res.error}"])
    sm = res.summary
    lines = ["Sensitivity analysis (canonical model only)", f"  core lane   : {res.core_status}",
             f"  scenarios   : {sm['scenarios']['registered']} registered; Phase 2 reproduced {sm['scenarios']['phase2_reproduced']}; guardrail {', '.join(sm['scenarios']['guardrail'])}",
             f"  baseline    : M1 {sm['baseline']['M1']:g} g, M2 {sm['baseline']['M2']:,.1f} g, M3 {sm['baseline']['M3']:,}, M4 {sm['baseline']['M4']:g}, M5 {sm['baseline']['M5']:.2f}%, S2 {sm['baseline']['S2']:.2f}% (frozen)",
             "  ranges      : " + "; ".join(f"{m} {r['min']:,.1f}-{r['max']:,.1f}" for m, r in sm["ranges"].items() if m in ("M1", "M2")),
             f"  conclusions : {sm['conclusion_classes']}", f"  controls    : {sm['controls']['pass']} pass, {sm['controls']['fail']} fail, {sm['controls']['info']} info"]
    for p in sm["baseline_problems"] + sm["phase2_mismatches"]:
        lines.append(f"  FAILED: {p}")
    return "\n".join(lines)
