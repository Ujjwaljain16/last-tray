"""Ingestion manifest writers. Deterministic: sorted rows, fixed columns, LF line endings, no wall-clock values.

The only time-dependent file is ingestion_run.json (run id, start and finish). Everything else is byte-identical for
identical inputs, which is what the idempotency check compares.
"""
from __future__ import annotations

import csv
import json
from dataclasses import asdict, fields
from enum import Enum
from pathlib import Path
from typing import Any, Iterable

from src.config import Config
from src.ingest.hashing import digest_file
from src.ingest.model import ArtifactStatus, IngestionResult, LaneOutcome, SchemaStatus

OUT_SUBDIR = "ingestion"
DETERMINISTIC_FILES = (
    "source_snapshot.csv", "raw_artifact_manifest.csv", "schema_fingerprints.csv", "weather_inventory.csv",
    "staging_handoff.json", "ingestion_summary.json",
)
RUN_RECORD = "ingestion_run.json"     # non-deterministic by design


def _cell(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, Enum):
        return str(v.value)
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (tuple, list)):
        return ";".join(str(x) for x in v)
    return str(v)


def write_csv(path: Path, rows: Iterable[Any], cols: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(cols)
        for r in rows:
            d = asdict(r) if hasattr(r, "__dataclass_fields__") else r
            w.writerow([_cell(d.get(c)) for c in cols])


def write_json(path: Path, obj: Any) -> None:
    path.write_text(json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


def build_handoff(cfg: Config, result: IngestionResult) -> dict[str, Any]:
    """The contract with staging (WP3): what may be read, from where, verified against which snapshot."""
    f = cfg.sources.flavoria
    w = cfg.sources.weather
    core_ready = result.core_outcome in (LaneOutcome.OK, LaneOutcome.WARNING)
    ctx_ready = result.context_outcome in (LaneOutcome.OK, LaneOutcome.WARNING)
    snap_f, snap_w = result.snapshot("flavoria"), result.snapshot("fmi_weather")
    sch = {s.filename: s for s in result.schemas}
    scope = {t.filename: t for t in result.tz_scope}
    members = []
    for a in sorted((a for a in result.artifacts if a.kind == "member"), key=lambda a: a.filename):
        override = cfg.timezone.overrides.get(a.filename)
        applies = bool(override) and scope.get(a.filename) is not None and scope[a.filename].status == "VALID"
        members.append({
            "file": a.filename, "artifact_id": a.artifact_id, "source_snapshot_id": a.source_snapshot_id,
            "population": cfg.populations.population_for_filename(a.filename).value,
            "rows": a.row_count, "sha256": a.sha256, "status": a.status.value,
            "schema_variant": sch[a.filename].variant if a.filename in sch else None,
            "schema_fingerprint": sch[a.filename].fingerprint if a.filename in sch else None,
            "schema_status": sch[a.filename].status.value if a.filename in sch else None,
            "timezone": {
                "normalization": (override.label.value if applies else cfg.timezone.default_label.value),
                "offset_hours": (override.offset_hours if applies else 0),
                "assumed_zone_for_unshifted_times": cfg.timezone.default_assume,
                "scope": "file_specific" if override else "none",
                "source_confirmed": False,
            },
        })
    arc = next((a for a in result.artifacts if a.kind == "archive"), None)
    return {
        "input_fingerprint": result.input_fingerprint,
        "core": {
            "ready": core_ready, "outcome": result.core_outcome.value, "source": "flavoria",
            "source_snapshot_id": snap_f.source_snapshot_id if snap_f else None,
            "source_url": f.archive_url, "license": f.license, "attribution": f.attribution,
            "archive": {"artifact_id": arc.artifact_id, "path": arc.path, "sha256": arc.sha256, "size_bytes": arc.size_bytes, "retrieved_on": arc.retrieved_on} if arc else None,
            "members": members if core_ready else [],
            "required_columns": list(f.required_columns),
        },
        "context": {
            "ready": ctx_ready, "outcome": result.context_outcome.value, "source": "fmi_weather",
            "source_snapshot_id": snap_w.source_snapshot_id if snap_w else None,
            "source_url": w.endpoint, "license": w.license, "license_url": w.license_url, "fmisid": w.fmisid,
            "r_1h_convention": w.r_1h_convention, "expected_hours": w.expected_hours,
            "chunks": [{"file": a.filename, "artifact_id": a.artifact_id, "path": a.path, "sha256": a.sha256, "source_url": a.source_url}
                       for a in sorted(result.artifacts, key=lambda a: a.filename) if a.kind == "weather_chunk"] if ctx_ready else [],
        },
    }


def build_summary(result: IngestionResult) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for a in result.artifacts:
        counts[a.status.value] = counts.get(a.status.value, 0) + 1
    schema_counts: dict[str, int] = {}
    for s in result.schemas:
        schema_counts[s.status.value] = schema_counts.get(s.status.value, 0) + 1
    return {
        "stage": "ingestion",
        "core_outcome": result.core_outcome.value,
        "context_outcome": result.context_outcome.value,
        "ready_for_staging": result.core_outcome in (LaneOutcome.OK, LaneOutcome.WARNING),
        "input_fingerprint": result.input_fingerprint,
        "snapshots": [{"source_snapshot_id": s.source_snapshot_id, "source": s.source_name, "lane": s.lane.value, "status": s.status,
                       "snapshot_sha256": s.snapshot_sha256} for s in sorted(result.snapshots, key=lambda s: s.source_name)],
        "artifact_status_counts": dict(sorted(counts.items())),
        "schema_status_counts": dict(sorted(schema_counts.items())),
        "timezone_override_scope": [asdict(t) | {"reasons": list(t.reasons)} for t in result.tz_scope],
        "raw_unchanged_during_run": result.raw_unchanged,
        "steps": [{"step": n, "status": s} for n, s in result.steps],
        "messages": [{"level": m.level.value, "code": m.code, "text": m.text} for m in result.messages],
    }


def write_ingestion_outputs(cfg: Config, result: IngestionResult, out_dir: Path) -> dict[str, str]:
    """Write every deterministic ingestion output. Returns {filename: sha256}."""
    d = out_dir / OUT_SUBDIR
    d.mkdir(parents=True, exist_ok=True)
    write_csv(d / "source_snapshot.csv", sorted(result.snapshots, key=lambda s: s.source_name),
              [f.name for f in fields(result.snapshots[0])] if result.snapshots else [])
    write_csv(d / "raw_artifact_manifest.csv", sorted(result.artifacts, key=lambda a: (a.source_name, a.kind, a.filename)),
              ["artifact_id", "source_snapshot_id", "source_name", "lane", "kind", "filename", "path", "parent_artifact_id", "source_url",
               "retrieved_on", "version", "in_snapshot_identity", "size_bytes", "md5", "sha256", "expected_size_bytes", "expected_sha256",
               "row_count", "expected_rows", "status", "message"])
    write_csv(d / "schema_fingerprints.csv", sorted(result.schemas, key=lambda s: s.filename),
              ["artifact_id", "filename", "fingerprint", "variant", "status", "named_columns", "blank_columns", "missing_required", "unexpected", "message"])
    write_csv(d / "weather_inventory.csv", sorted(result.weather_chunks, key=lambda c: c.filename),
              ["artifact_id", "filename", "elements", "number_returned", "hours", "parameters", "null_values", "content_sha256",
               "expected_content_sha256", "status", "message"])
    write_json(d / "staging_handoff.json", build_handoff(cfg, result))
    write_json(d / "ingestion_summary.json", build_summary(result))
    return {n: digest_file(d / n).sha256 for n in DETERMINISTIC_FILES}
