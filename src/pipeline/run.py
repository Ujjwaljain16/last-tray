"""Command line entry point:  python -m src.pipeline.run

Normal execution is OFFLINE. This command never downloads anything: if a required raw source is missing it fails clearly
and names the explicit retrieval command (python -m src.pipeline.fetch --source <name>).

The pipeline runs six stages in a fixed order behind explicit gates: ingest > stage > validate > model > metrics > sensitivity.
A stage runs only if the stage before it passed. When a stage fails, every later stage is BLOCKED (not run; its stale outputs are removed)
and the exit code is the class of the first failed stage. Each stage verifies its own upstream contract (checksums, headers, row counts,
run ids); nothing is skipped because a file exists. --resume-from re-runs from a later stage against artifacts already on disk, after that
verification. A run writes outputs/pipeline/ (run manifest, stage summary, pipeline controls, runtime summary, run log).

Exit codes (stable; see docs/pipeline.md)
    0  every requested stage passed; both lanes healthy (quarantine is a finding, not a failure)
    2  configuration missing, malformed, or violating an approved decision
    3  retired (all stages are implemented; never returned)
    4  SOURCE: a raw source is missing, corrupt or unverified, a timezone override is out of scope, ingestion or staging failed
    5  FETCH: explicit retrieval failed (python -m src.pipeline.fetch only)
    6  WEATHER: core lane usable but the weather context lane is BLOCKED
    7  VALIDATION: a staging table is missing or altered, or a reconciliation identity broke
    8  MODEL: a validation output is missing or altered, or a canonical control failed
    9  METRICS: a canonical table is missing or altered, or a metric missed its approved value
    10 SENSITIVITY: baseline moved, an approved reference stopped reproducing, registry invalid, or input unusable
    11 ORCHESTRATION: invalid stage order, unexpected exception, or an unwritable pipeline manifest
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from src.config import DEFAULT_CONFIG_DIR, ConfigError, load_config
from src.pipeline.describe import (describe, describe_metrics, describe_model, describe_sensitivity, describe_staging, describe_validation, summarise)  # noqa: F401
from src.pipeline.exit_codes import ExitCode
from src.pipeline.orchestrate import OrchestrationError, RunLogger, run_pipeline
from src.pipeline.report import OUT_SUBDIR as PIPELINE_SUBDIR, clear_pipeline_outputs, new_run_id, previous_output_hashes, write_pipeline_outputs
from src.pipeline.stages import STAGE_ORDER, Context, default_stages

REPO_ROOT = Path(__file__).resolve().parents[2]
EXIT_OK = int(ExitCode.OK)
EXIT_CONFIG = int(ExitCode.CONFIG)
EXIT_CORE_FAILED = int(ExitCode.SOURCE)
EXIT_CONTEXT_BLOCKED = int(ExitCode.WEATHER)
EXIT_ORCHESTRATION = int(ExitCode.ORCHESTRATION)


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
    p.add_argument("--stages", choices=(*STAGE_ORDER, "all"), default="all",
                   help="run the stages up to and including this one, in order, behind the gates ('all' = through sensitivity; default). Exits 0 only if every stage run passed")
    p.add_argument("--resume-from", choices=STAGE_ORDER, default=None,
                   help="start at this stage against the artifacts already on disk (each stage still verifies its upstream contract; nothing is skipped because a file exists)")
    p.add_argument("--profile-memory", action="store_true", help="record peak Python allocation per stage (slower; written to outputs/pipeline/runtime_summary.json)")
    p.add_argument("--check-config", action="store_true", help="load and validate configuration, print a summary, then exit")
    return p


def _failed_controls(out: Path) -> list[str]:
    with (out / PIPELINE_SUBDIR / "pipeline_controls.csv").open(newline="", encoding="utf-8") as fh:
        return [f"{r['control_id']} {r['control']}: {r['detail']}" for r in csv.DictReader(fh) if r["status"] == "FAIL"]


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

    target = "sensitivity" if args.stages == "all" else args.stages
    run_id = new_run_id()
    ctx = Context(cfg, args.out, args.repo_root)
    try:
        last = previous_output_hashes(args.out) if args.resume_from else {}      # what the last run recorded, for the artifacts a resume reuses
        clear_pipeline_outputs(args.out)                                        # a previous run's manifest must never look current
        result = run_pipeline(default_stages(), ctx, target=target, resume_from=args.resume_from, run_id=run_id,
                              logger=RunLogger(run_id), profile_memory=args.profile_memory, echo=print, previous=last)
    except OrchestrationError as exc:
        print(f"FAILED: orchestration: {exc}", file=sys.stderr)
        return EXIT_ORCHESTRATION
    try:
        manifest = write_pipeline_outputs(result, Path(args.config_dir), args.out, repo_root=args.repo_root, profile_memory=args.profile_memory)
    except OSError as exc:
        print(f"FAILED: orchestration: the pipeline manifest could not be written: {exc}", file=sys.stderr)
        return EXIT_ORCHESTRATION

    counts = {s: sum(1 for r in result.stages if r.status == s) for s in ("PASSED", "FAILED", "BLOCKED", "REUSED", "INVALIDATED", "NOT_RUN")}
    print(f"Pipeline {run_id}: " + ", ".join(f"{v} {k}" for k, v in counts.items() if v) + f"; controls {manifest['controls']['pass']} pass, {manifest['controls']['fail']} fail; "
          f"exit {result.exit_code}; manifest: {args.out / PIPELINE_SUBDIR / 'run_manifest.json'}")
    if manifest["controls"]["fail"]:
        print("FAILED: a pipeline control failed: " + "; ".join(_failed_controls(args.out)), file=sys.stderr)
        return EXIT_ORCHESTRATION if result.exit_code == EXIT_OK else result.exit_code
    failure = result.first_failure
    if failure is not None:
        print(f"FAILED: stage {failure.name!r} failed ({failure.reason}); every later stage was blocked and its stale outputs were removed. "
              "If a raw source is missing, retrieve it explicitly: python -m src.pipeline.fetch --source <flavoria|weather>", file=sys.stderr)
    elif result.weather_blocked:
        print("BLOCKED: the weather context lane could not be verified, staged, validated or modelled; weather-dependent outputs are blocked. Core outputs are unaffected.", file=sys.stderr)
    return result.exit_code


if __name__ == "__main__":
    sys.exit(main())
