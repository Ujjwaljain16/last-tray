"""Staging of Flavoria weighing events: verified bytes in, one staged row per source data row out.

Grain: one staged row = one source data row = one component weighing event. EVERY row is kept (no filtering, no
deduplication, no repair): duplicates, odd weights and odd timestamps are staged as found and judged later by validation.
Columns are read by NAME, so schema drift (a missing optional column, extra columns, reordering) does not corrupt the data.
Raw text is preserved beside every normalised value, and every row carries its lineage back to the snapshot and raw artifact.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
from dataclasses import dataclass
from typing import Any

from src.config import Config
from src.stage.components import has_edge_whitespace, normalize_component_name, parse_weight, scale_parts
from src.stage.timestamps import StagingError, TimezoneTreatment, iso_local, iso_utc, stage_timestamp
from src.vocab import RowParseStatus

SEP = "\x1f"


@dataclass(frozen=True)
class MemberMeta:
    file: str
    artifact_id: str
    source_snapshot_id: str
    population: str
    schema_variant: str | None
    schema_fingerprint: str | None
    rows: int
    sha256: str
    timezone: dict[str, Any]

    @classmethod
    def from_handoff(cls, m: dict[str, Any]) -> "MemberMeta":
        return cls(m["file"], m["artifact_id"], m["source_snapshot_id"], m["population"], m["schema_variant"], m["schema_fingerprint"],
                   m["rows"], m["sha256"], m["timezone"])


@dataclass(frozen=True)
class StagedEvent:
    """Column order here is the column order of stg_weighing_event.csv."""

    event_id: str
    source_snapshot_id: str
    raw_artifact_id: str
    source_file: str
    source_row_number: int
    raw_row_sha256: str
    row_parse_status: str
    schema_variant: str | None
    schema_fingerprint: str | None
    population: str
    session_id: str
    session_key: str                       # session_id|population: the two populations are never merged
    tray_id: str
    scale_id: str
    scale_line: str | None
    scale_side: str | None
    scale_kind: str | None
    scale_position: int | None
    component_name_raw: str
    component_id_normalized: str | None
    component_name_had_edge_whitespace: bool
    weight_raw: str
    component_weight_g: int | None
    weight_parse_status: str
    weighing_type: str | None
    event_time_raw: str
    event_time_source_format: str | None
    event_time_local: str | None
    event_time_canonical_utc: str | None
    event_time_status: str
    identification_time_raw: str
    identification_time_source_format: str | None
    identification_time_local: str | None
    identification_time_canonical_utc: str | None
    identification_time_status: str
    timezone_handling: str
    timezone_offset_hours_applied: int
    timezone_transformation_reason: str
    unmapped_cells: str | None


EVENT_COLUMNS = tuple(StagedEvent.__dataclass_fields__)


def stage_member(data: bytes, meta: MemberMeta, cfg: Config, treatment: TimezoneTreatment) -> list[StagedEvent]:
    """Stage one verified member. Raises StagingError if it cannot be staged faithfully; never returns a partial result."""
    f = cfg.sources.flavoria
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise StagingError(f"{meta.file}: not UTF-8: {exc}") from exc
    reader = csv.reader(io.StringIO(text))
    header = next(reader, None)
    if not header:
        raise StagingError(f"{meta.file}: empty file")
    index: dict[str, int] = {}
    for i, name in enumerate(header):
        if name.strip():
            if name in index:
                raise StagingError(f"{meta.file}: duplicate column name {name!r}")
            index[name] = i
    missing = [c for c in f.required_columns if c not in index]
    if missing:
        raise StagingError(f"{meta.file}: required column(s) missing: {missing}")
    known = set(f.required_columns) | set(f.optional_columns)
    extra_named = [n for n in index if n not in known]
    blank_idx = [i for i, n in enumerate(header) if not n.strip()]
    last_required = max(index[c] for c in f.required_columns)

    events: list[StagedEvent] = []
    n = 0
    for rec in reader:
        if not any(c.strip() for c in rec):           # blank line: same rule ingestion used to count rows
            continue
        n += 1

        def cell(name: str) -> str:
            i = index.get(name)
            return rec[i] if i is not None and i < len(rec) else ""

        unmapped: dict[str, Any] = {}
        if extra_named:
            unmapped["extra_columns"] = {c: cell(c) for c in extra_named}
        if len(rec) > len(header):
            unmapped["beyond_header"] = rec[len(header):]
        filled = {str(i): rec[i] for i in blank_idx if i < len(rec) and rec[i].strip()}
        if filled:
            unmapped["blank_header_columns"] = filled
        status = RowParseStatus.OK
        if len(rec) <= last_required:
            status = RowParseStatus.SHORT_ROW
        elif len(rec) > len(header) or filled:
            status = RowParseStatus.EXTRA_CELLS

        name_raw, weight_raw, scale_id = cell("component_name"), cell("weight_of_a_component"), cell("scale_identifier")
        weight, wstatus = parse_weight(weight_raw)
        line, side, kind, pos = scale_parts(scale_id)
        ev, idn = stage_timestamp(cell("weighing_event_time"), treatment), stage_timestamp(cell("user_identification_time"), treatment)
        session_id = cell("session_id")
        events.append(StagedEvent(
            event_id=f"{meta.file}#{n}", source_snapshot_id=meta.source_snapshot_id, raw_artifact_id=meta.artifact_id,
            source_file=meta.file, source_row_number=n, raw_row_sha256=hashlib.sha256(SEP.join(rec).encode("utf-8")).hexdigest(),
            row_parse_status=status.value, schema_variant=meta.schema_variant, schema_fingerprint=meta.schema_fingerprint,
            population=meta.population, session_id=session_id, session_key=f"{session_id}|{meta.population}", tray_id=cell("tray_id"),
            scale_id=scale_id, scale_line=line, scale_side=side, scale_kind=kind, scale_position=pos,
            component_name_raw=name_raw, component_id_normalized=normalize_component_name(name_raw),
            component_name_had_edge_whitespace=has_edge_whitespace(name_raw),
            weight_raw=weight_raw, component_weight_g=weight, weight_parse_status=wstatus.value,
            weighing_type=(cell("weighting_type") or None) if "weighting_type" in index else None,   # the SOURCE spells it weighting_type
            event_time_raw=ev.raw, event_time_source_format=ev.source_format, event_time_local=iso_local(ev.local),
            event_time_canonical_utc=iso_utc(ev.utc), event_time_status=ev.status.value,
            identification_time_raw=idn.raw, identification_time_source_format=idn.source_format,
            identification_time_local=iso_local(idn.local), identification_time_canonical_utc=iso_utc(idn.utc),
            identification_time_status=idn.status.value,
            timezone_handling=treatment.handling.value, timezone_offset_hours_applied=treatment.offset_hours,
            timezone_transformation_reason=treatment.reason,
            unmapped_cells=json.dumps(unmapped, sort_keys=True, ensure_ascii=False) if unmapped else None,
        ))
    if n != meta.rows:
        raise StagingError(f"{meta.file}: staged {n} rows but ingestion verified {meta.rows}")
    return events
