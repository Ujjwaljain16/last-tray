"""Command line entry point:  python -m src.pipeline.run

Normal execution is OFFLINE. This command never downloads anything: if a required raw source is missing it fails clearly
and names the explicit retrieval command (python -m src.pipeline.fetch --source <name>).

Implemented so far: configuration (WP1) and ingestion / raw preservation (WP2). The later stages (staging, validation,
model, metrics, sensitivity, evidence, gates) arrive in WP3-WP8. Until then a full run stops with an explicit non-zero exit
code: it must never report success for work it has not done.

Exit codes
    0  the requested stages completed (--check-config, --help, or --stages ingest with both lanes OK or WARNING)
    2  configuration is missing, malformed, or would change an approved decision
    3  ingestion finished, but the stages after it are not implemented yet (outputs cover ingestion only)
    4  core lane FAILED: a required raw source is missing, corrupt, mismatched, or a timezone override is out of scope
    6  core lane usable but the context lane (weather) is BLOCKED: weather-dependent outputs cannot be produced
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.config import DEFAULT_CONFIG_DIR, Config, ConfigError, load_config
from src.ingest.ingest import run_ingestion, utc_now, write_run_record
from src.ingest.model import ArtifactStatus, IngestionResult, LaneOutcome

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
    p.add_argument("--stages", choices=("ingest", "all"), default="all",
                   help="'ingest' runs the implemented ingestion stage and exits 0 on success; 'all' also reports that later stages are not implemented (default)")
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

    if result.core_outcome is LaneOutcome.FAILED:
        print("FAILED: the core lane could not be verified, so nothing downstream may run. "
              "If a raw source is missing, retrieve it explicitly: python -m src.pipeline.fetch --source <flavoria|weather>", file=sys.stderr)
        return EXIT_CORE_FAILED
    if result.context_outcome is LaneOutcome.BLOCKED:
        print("BLOCKED: the weather context lane could not be verified; weather-dependent outputs are blocked. Core outputs are unaffected.", file=sys.stderr)
        return EXIT_CONTEXT_BLOCKED
    if args.stages == "ingest":
        return EXIT_OK
    print("BLOCKED: stages after ingestion (staging, validation, model, metrics, sensitivity, evidence) are not implemented yet. "
          "Outputs cover ingestion only. Use --stages ingest to run the implemented stage.", file=sys.stderr)
    return EXIT_NOT_IMPLEMENTED


if __name__ == "__main__":
    sys.exit(main())
