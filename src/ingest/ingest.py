"""Ingestion orchestration (WP2). Runs entirely offline.

    source discovery -> source snapshot identity -> checksum verification -> schema fingerprint
    -> timezone override scope (T10) -> immutable raw preservation check -> ingestion manifest -> staging handoff

It reads raw files, compares them with the pins in config/sources.yml, writes manifests OUTSIDE the raw tree, and stops.
It never downloads, never edits a pin, and never modifies a raw file. Core lane (Flavoria) problems FAIL the run;
context lane (weather) problems BLOCK weather-dependent outputs only.
"""
from __future__ import annotations

import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

from src.config import Config
from src.ingest import preserve, weather
from src.ingest.flavoria import verify_flavoria
from src.ingest.manifest import OUT_SUBDIR, RUN_RECORD, write_ingestion_outputs, write_json
from src.ingest.model import ArtifactStatus, IngestionResult, LaneOutcome, Level, Message
from src.ingest.snapshot import input_fingerprint
from src.ingest.tz_scope import check_all


def run_ingestion(cfg: Config, repo_root: Path, out_dir: Path) -> tuple[IngestionResult, dict[str, str]]:
    """Returns the result and {output filename: sha256} for the deterministic outputs."""
    raw_root = repo_root / "data" / "raw"
    preserve.assert_outputs_outside_raw(out_dir, raw_root)
    result = IngestionResult()
    before = preserve.capture(raw_root)

    # 1. source discovery ---------------------------------------------------------------------------------------------------
    wanted = [repo_root / cfg.sources.flavoria.archive_path] + [repo_root / cfg.sources.weather.local_dir / s.file for s in cfg.sources.weather.raw_files]
    missing = [p.relative_to(repo_root).as_posix() for p in wanted if not p.is_file()]
    result.steps.append(("source discovery", "OK" if not missing else f"MISSING {len(missing)} of {len(wanted)}"))

    # 2-4. snapshot identity, checksum verification, schema fingerprints (per source) ----------------------------------------------
    fl = verify_flavoria(cfg, repo_root)
    wx = weather.verify_weather(cfg, repo_root)
    result.snapshots += [fl.snapshot, wx.snapshot]
    result.artifacts += fl.artifacts + wx.artifacts
    result.schemas += fl.schemas
    result.weather_chunks += wx.chunks
    result.messages += fl.messages + wx.messages
    ids = [s.source_snapshot_id for s in result.snapshots if s.source_snapshot_id]
    result.input_fingerprint = input_fingerprint(ids) if ids else None
    result.steps.append(("source snapshot identity", "OK" if len(ids) == 2 else f"{len(ids)} of 2 snapshots identified"))
    bad = [a for a in result.artifacts if a.status is not ArtifactStatus.VERIFIED]
    result.steps.append(("checksum verification", "OK" if not bad else f"{len(bad)} artifact(s) not verified"))
    drift = [s for s in result.schemas if s.status.value != "KNOWN_VARIANT"]
    result.steps.append(("schema fingerprint", "OK" if not drift else f"{len(drift)} header(s) differ from known variants"))

    # 5. timezone override scope (T10) -----------------------------------------------------------------------------------------------
    result.tz_scope = check_all(cfg, fl.member_bytes)
    for t in result.tz_scope:
        if t.status != "VALID":
            result.messages.append(Message(Level.ERROR, "T10", f"timezone override for {t.filename} is not valid here: " + "; ".join(t.reasons)))
    result.steps.append(("timezone override scope (T10)", "OK" if all(t.status == "VALID" for t in result.tz_scope) else "INVALID"))

    # lane outcomes ---------------------------------------------------------------------------------------------------------------
    core = fl.outcome
    if any(t.status != "VALID" for t in result.tz_scope):
        core = LaneOutcome.FAILED
    result.core_outcome, result.context_outcome = core, wx.outcome

    # 6. raw preservation: the run must leave data/raw exactly as it found it ------------------------------------------------------
    diff = before.diff(preserve.capture(raw_root))
    result.raw_unchanged = not diff
    for line in diff:
        result.messages.append(Message(Level.ERROR, "S01", f"raw preservation violated: {line}"))
    result.steps.append(("raw preservation", "OK" if not diff else "VIOLATED"))
    if diff:
        result.core_outcome = LaneOutcome.FAILED

    # 7-8. ingestion manifest and staging handoff ---------------------------------------------------------------------------------------
    result.steps.append(("ingestion manifest", "OK"))
    result.steps.append(("staging handoff", "READY" if result.core_outcome in (LaneOutcome.OK, LaneOutcome.WARNING) else "NOT READY"))
    hashes = write_ingestion_outputs(cfg, result, out_dir)
    return result, hashes


def write_run_record(result: IngestionResult, out_dir: Path, hashes: dict[str, str], started: datetime, finished: datetime) -> Path:
    """The one non-deterministic ingestion file: who ran what, when. Excluded from idempotency comparison."""
    rec = {
        "run_id": "ingest-" + started.strftime("%Y%m%dT%H%M%SZ"),
        "started_at": started.isoformat(), "finished_at": finished.isoformat(),
        "python": sys.version.split()[0], "platform": platform.platform(),
        "core_outcome": result.core_outcome.value, "context_outcome": result.context_outcome.value,
        "input_fingerprint": result.input_fingerprint, "network_used": False,
        "deterministic_output_sha256": hashes,
    }
    path = out_dir / OUT_SUBDIR / RUN_RECORD
    write_json(path, rec)
    return path


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
