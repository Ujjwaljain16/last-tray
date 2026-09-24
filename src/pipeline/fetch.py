"""Explicit source retrieval:  python -m src.pipeline.fetch --source <flavoria|weather>

This is the ONLY command that touches the network. The normal pipeline (python -m src.pipeline.run) is offline and tells
you to come here when a raw source is missing.

  --source flavoria           restore a MISSING pinned archive (verified against size, MD5, SHA-256); a no-op if present
  --source flavoria --refresh retrieve a NEW snapshot into data/raw/flavoria/refresh-<time>/ (existing files untouched)
  --source weather            retrieve a NEW weather snapshot into data/raw/weather/refresh-<time>/ (FMI stamps each
                              response with its retrieval time, so bytes can never equal the pinned bytes; the report says
                              whether the parsed CONTENT is identical)

Pins are never edited by this command. Adopting a refreshed snapshot is a deliberate, documented change to
config/sources.yml. Use --print-pins to get the YAML to review.

Exit codes: 0 OK / RECOVERED / NO_OP;  2 configuration error;  5 retrieval FAILED (nothing was written at a pinned path).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.config import DEFAULT_CONFIG_DIR, ConfigError, env_path, load_config
from src.ingest.requests_client import RequestsClient
from src.ingest.retrieval import FetchOutcome, fetch_flavoria, fetch_weather, pin_snippet

REPO_ROOT = Path(__file__).resolve().parents[2]
EXIT_OK, EXIT_CONFIG, EXIT_FETCH_FAILED = 0, 2, 5


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m src.pipeline.fetch",
                                description="Explicit, network-using retrieval of one source. Never edits pins; never overwrites raw files.")
    p.add_argument("--source", required=True, choices=("flavoria", "weather"), help="which source to retrieve")
    p.add_argument("--refresh", action="store_true", help="retrieve a NEW snapshot even if the pinned file exists (flavoria only; weather always does)")
    p.add_argument("--dest", type=Path, default=env_path("LAST_TRAY_RAW_DIR", REPO_ROOT / "data" / "raw"),
                   help="raw data root (default: ./data/raw, or $LAST_TRAY_RAW_DIR)")
    p.add_argument("--config-dir", type=Path, default=env_path("LAST_TRAY_CONFIG_DIR", DEFAULT_CONFIG_DIR))
    p.add_argument("--print-pins", action="store_true", help="print the YAML pin lines for the retrieved files (for a human to review)")
    return p


def main(argv: list[str] | None = None, client=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        cfg = load_config(args.config_dir)
    except ConfigError as exc:
        print(f"FAILED: configuration: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    client = client or RequestsClient()
    if args.source == "flavoria":
        report = fetch_flavoria(cfg, args.dest, client, refresh=args.refresh)
    else:
        report = fetch_weather(cfg, args.dest, client)
    print(f"{report.source}: {report.outcome.value}")
    for m in report.messages:
        print(f"  {m}")
    for f in report.files:
        print(f"  {f.filename}  {f.size_bytes} bytes  sha256={f.sha256}  attempts={f.attempts}")
    if report.snapshot_dir:
        print(f"  snapshot: {report.snapshot_dir}")
    if args.print_pins and report.files:
        print("  pins for config/sources.yml (review before use):")
        print(pin_snippet(report))
    return EXIT_FETCH_FAILED if report.outcome is FetchOutcome.FAILED else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
