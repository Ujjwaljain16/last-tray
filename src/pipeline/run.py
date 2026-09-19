"""Command line entry point:  python -m src.pipeline.run

Normal execution is OFFLINE. This command never downloads anything: if a required raw source is missing it fails clearly
and names the explicit retrieval command (python -m src.pipeline.fetch --source <name>).

Implemented so far: configuration (WP1), ingestion / raw preservation (WP2), staging (WP3), validation / reconciliation (WP4)
the canonical model (WP5) and metrics (WP6). The later stages (sensitivity, evidence, gates) arrive in WP7-WP8. Until then a full run stops with an explicit non-zero exit
code: it must never report success for work it has not done.

Exit codes
    0  the requested stages completed (--check-config, --help, or --stages ingest|stage|validate|model|metrics with both lanes OK or WARNING;
       quarantine is a finding, not a failure)
    2  configuration is missing, malformed, or would change an approved decision
    3  the implemented stages finished, but the stages after them are not implemented yet
    4  core lane FAILED: a raw source is missing, corrupt, mismatched, a timezone override is out of scope, staging could not stage it
       faithfully, validation is BLOCKED (a staging table is missing or altered, or a reconciliation identity broke), or the
       canonical model is BLOCKED (a WP4 input is missing or altered, or a control check failed), or the metrics are BLOCKED or
       FAILED (a canonical table is missing or altered, or a metric missed its approved tolerance)
    6  core lane usable but the context lane (weather) is BLOCKED: weather-dependent outputs cannot be produced
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.config import DEFAULT_CONFIG_DIR, Config, ConfigError, load_config
from src.ingest.handoff import HandoffError, VerifiedReader, load_handoff
from src.ingest.ingest import run_ingestion, utc_now, write_run_record
from src.ingest.manifest import OUT_SUBDIR as INGESTION_SUBDIR
from src.ingest.model import ArtifactStatus, IngestionResult, LaneOutcome
from src.stage.stage import StagingResult, run_staging
from src.metrics.evaluate import MetricsResult, run_metrics
from src.model.build import ModelResult, run_model
from src.validate.validate import ValidationResult, run_validation

REPO_ROOT = Path(__file__).resolve().parents[2]
EXIT_OK = 0
EXIT_CONFIG = 2
EXIT_NOT_IMPLEMENTED = 3
EXIT_CORE_FAILED = 4
EXIT_CONTEXT_BLOCKED = 6


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m src.pipeline.run",
        description="LAST TRAY: reconstruct dining-session measurements from raw lunch-line weighing events, "
        "validate them, compute the KPIs, and state what the evidence can and cannot support. "
        "Selected weight is not consumption, and consumption is not waste. "
        "Runs OFFLINE: it never downloads. Use python -m src.pipeline.fetch to retrieve a source explicitly.",
    )
    p.add_argument("--config-dir", type=Path, default=DEFAULT_CONFIG_DIR, help="directory holding config/*.yml (default: ./config)")
    p.add_argument("--out", type=Path, default=REPO_ROOT / "outputs", help="directory for outputs (default: ./outputs)")
    p.add_argument("--repo-root", type=Path, default=REPO_ROOT, help="repository root containing data/raw (default: this repository)")
    p.add_argument("--stages", choices=("ingest", "stage", "validate", "model", "metrics", "all"), default="all",
                   help="'ingest' runs ingestion; 'stage' adds staging; 'validate' adds validation; 'model' adds the canonical model; 'metrics' adds the metrics; each exits 0 on success. 'all' also reports that later stages are not implemented (default)")
    p.add_argument("--check-config", action="store_true", help="load and validate configuration, print a summary, then exit")
    return p


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


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        cfg = load_config(args.config_dir)
    except ConfigError as exc:
        print(f"FAILED: configuration: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    if args.check_config:
        print(summarise(cfg))
        return EXIT_OK

    started = utc_now()
    result, hashes = run_ingestion(cfg, args.repo_root, args.out)
    write_run_record(result, args.out, hashes, started, utc_now())
    print(describe(result))
    core_failed = result.core_outcome is LaneOutcome.FAILED
    context_blocked = result.context_outcome is LaneOutcome.BLOCKED

    if args.stages != "ingest":
        # Staging ALWAYS runs when requested, even after an ingestion failure: it reads the handoff FILE ingestion wrote, reads raw
        # bytes only through the verified reader, and on a failed lane it REMOVES that lane's stale outputs so an earlier run's
        # table can never look current. A weather problem never stops core staging, and a core problem never keeps stale tables.
        try:
            handoff = load_handoff(args.out / INGESTION_SUBDIR / "staging_handoff.json")
            staged = run_staging(cfg, VerifiedReader(args.repo_root, handoff), args.out)
            print(describe_staging(staged))
            core_failed = core_failed or staged.core is LaneOutcome.FAILED
            context_blocked = context_blocked or staged.context is LaneOutcome.BLOCKED
        except HandoffError as exc:
            print(f"FAILED: {exc}", file=sys.stderr)
            core_failed = True

    if args.stages in ("validate", "model", "metrics", "all"):
        # Validation reads only the staging tables it can verify. If staging failed it finds no trustworthy table, BLOCKS, and removes
        # its own stale outputs, so an earlier run's findings can never look current.
        validated = run_validation(cfg, args.out)
        print(describe_validation(validated))
        core_failed = core_failed or validated.core_status == "BLOCKED"
        context_blocked = context_blocked or validated.weather_status == "BLOCKED"

    if args.stages in ("model", "metrics", "all"):
        # The model reads only verified staging and verified validation outputs. If either is unusable it BLOCKS and removes its own
        # stale tables; if a control check fails it publishes no canonical rows and writes only the control files for inspection.
        modelled = run_model(cfg, args.out)
        print(describe_model(modelled))
        core_failed = core_failed or modelled.core_status == "BLOCKED"
        context_blocked = context_blocked or modelled.weather_status == "BLOCKED"

    if args.stages in ("metrics", "all"):
        # Metrics read only the canonical model tables, verified against the model manifest. A missing or altered table BLOCKS the stage and
        # removes stale metric files; a metric that misses its approved tolerance is reported FAILED, never recalibrated.
        measured = run_metrics(cfg, args.out)
        print(describe_metrics(measured))
        core_failed = core_failed or measured.core_status in ("BLOCKED", "FAILED")
        context_blocked = context_blocked or measured.weather_status == "BLOCKED"

    if core_failed:
        print("FAILED: the core lane could not be verified, staged, validated, modelled or measured, so nothing downstream may run. Stale staging, validation, model and metric outputs were removed. "
              "If a raw source is missing, retrieve it explicitly: python -m src.pipeline.fetch --source <flavoria|weather>", file=sys.stderr)
        return EXIT_CORE_FAILED
    if context_blocked:
        print("BLOCKED: the weather context lane could not be verified, staged, validated or modelled; weather-dependent outputs are blocked. Core outputs are unaffected.", file=sys.stderr)
        return EXIT_CONTEXT_BLOCKED
    if args.stages != "all":
        return EXIT_OK
    print("BLOCKED: stages after the metrics (sensitivity, evidence, gates) are not implemented yet. "
          "Outputs cover ingestion, staging, validation, the canonical model and the metrics only. Use --stages metrics to run the implemented stages.", file=sys.stderr)
    return EXIT_NOT_IMPLEMENTED


if __name__ == "__main__":
    sys.exit(main())
