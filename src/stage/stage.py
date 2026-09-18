"""Staging orchestration (WP3): verified raw -> staging tables. Offline. No business logic.

Every read of raw bytes goes through the VerifiedReader (src.ingest.handoff). This module never opens data/raw, never opens a
tar file, and never builds a path to a raw artifact. A failed verification stops that source's staging path: nothing partial is
published, and any stale staging output from an earlier run is REMOVED so it cannot be mistaken for current data.

Core (Flavoria) failure   -> staging FAILED; the run stops.
Context (weather) failure -> weather staging BLOCKED; core staging is unaffected.

Not here: validation rules, sessions, metrics. Staging preserves and normalises; it does not judge.
"""
from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from src.config import Config
from src.ingest.handoff import HandoffError, VerifiedReader
from src.ingest.hashing import digest_file
from src.ingest.manifest import write_csv, write_json
from src.ingest.model import LaneOutcome, Level, Message
from src.stage.events import EVENT_COLUMNS, MemberMeta, StagedEvent, stage_member
from src.stage.timestamps import StagingError, treatment_for
from src.stage.weather import WEATHER_COLUMNS, StagedWeather, stage_weather_chunk

OUT_SUBDIR = "staging"
EVENTS_CSV = "stg_weighing_event.csv"
WEATHER_CSV = "stg_weather_observation.csv"
RECON_CSV = "staging_file_reconciliation.csv"
SUMMARY_JSON = "staging_summary.json"
DETERMINISTIC_FILES = (EVENTS_CSV, WEATHER_CSV, RECON_CSV, SUMMARY_JSON)
RECON_COLUMNS = ["source_file", "population", "schema_variant", "timezone_handling", "timezone_offset_hours_applied", "rows_verified_at_ingestion",
                 "rows_staged", "distinct_sessions", "first_event_time_raw", "last_event_time_raw", "first_event_canonical_utc",
                 "last_event_canonical_utc", "rows_with_non_ok_time_status", "rows_with_non_ok_row_status", "rows_with_non_integer_weight"]

TRANSFORMATIONS = [
    {"field": "event_time_local / identification_time_local", "rule": "wall time as written, plus the file-specific offset when (and only when) an override applies",
     "reason": "cross-export temporal alignment for the one suspect export; otherwise none"},
    {"field": "*_canonical_utc", "rule": "Europe/Helsinki wall time converted with real zoneinfo rules; ambiguous or nonexistent local times give NULL and a status",
     "reason": "the study period crosses the 2020-10-25 clock change; canonical instants must be comparable across files and with FMI (UTC)"},
    {"field": "component_id_normalized", "rule": "trim, collapse whitespace, casefold; NULL if empty. No alias table",
     "reason": "string-level identity only; cross-export names mix language variants with different dishes"},
    {"field": "component_weight_g", "rule": "integer parse of weight_of_a_component; NULL if not an integer",
     "reason": "typed value beside the verbatim weight_raw; no clipping, no judgement"},
    {"field": "scale_line / scale_side / scale_kind / scale_position", "rule": "split scale_identifier on '-'; NULL for unparseable parts",
     "reason": "structure inferred from names; the verbatim scale_id is kept"},
    {"field": "session_key", "rule": "session_id | population", "reason": "the same session_id occurs in both populations; they are never merged"},
    {"field": "weighing_type", "rule": "NULL where the column is absent from the file", "reason": "7 of 11 files lack the column (schema drift)"},
]


@dataclass
class StagingResult:
    core: LaneOutcome = LaneOutcome.OK
    context: LaneOutcome = LaneOutcome.OK
    events: list[StagedEvent] = field(default_factory=list)
    weather: list[StagedWeather] = field(default_factory=list)
    messages: list[Message] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    hashes: dict[str, str] = field(default_factory=dict)


def _remove(*paths: Path) -> None:
    for p in paths:
        if p.exists():
            p.unlink()


def _stage_core(cfg: Config, reader: VerifiedReader) -> tuple[list[StagedEvent], list[dict[str, Any]]]:
    core = reader.handoff["core"]
    if not core["ready"]:
        raise HandoffError(f"core lane is {core['outcome']}: staging must not read raw data")
    events: list[StagedEvent] = []
    recon: list[dict[str, Any]] = []
    for m in sorted(core["members"], key=lambda x: x["file"]):
        meta = MemberMeta.from_handoff(m)
        treatment = treatment_for(cfg, meta.file, meta.timezone)
        rows = stage_member(reader.member(meta.file), meta, cfg, treatment)
        events += rows
        recon.append({
            "source_file": meta.file, "population": meta.population, "schema_variant": meta.schema_variant,
            "timezone_handling": treatment.handling.value, "timezone_offset_hours_applied": treatment.offset_hours,
            "rows_verified_at_ingestion": meta.rows, "rows_staged": len(rows), "distinct_sessions": len({r.session_id for r in rows}),
            "first_event_time_raw": min((r.event_time_raw for r in rows), default=None),
            "last_event_time_raw": max((r.event_time_raw for r in rows), default=None),
            "first_event_canonical_utc": min((r.event_time_canonical_utc for r in rows if r.event_time_canonical_utc), default=None),
            "last_event_canonical_utc": max((r.event_time_canonical_utc for r in rows if r.event_time_canonical_utc), default=None),
            "rows_with_non_ok_time_status": sum(1 for r in rows if r.event_time_status != "OK" or r.identification_time_status != "OK"),
            "rows_with_non_ok_row_status": sum(1 for r in rows if r.row_parse_status != "OK"),
            "rows_with_non_integer_weight": sum(1 for r in rows if r.weight_parse_status != "OK"),
        })
    expected = cfg.sources.flavoria.expected_total_rows
    if len(events) != expected:
        raise StagingError(f"staged {len(events)} events but the pins say {expected}")
    if len({e.event_id for e in events}) != len(events):
        raise StagingError("event_id is not unique: source_file#source_row_number must identify one row")
    return events, recon


def _stage_context(cfg: Config, reader: VerifiedReader) -> list[StagedWeather]:
    ctx = reader.handoff["context"]
    if not ctx["ready"]:
        raise HandoffError(f"context lane is {ctx['outcome']}: staging must not read raw weather data")
    rows: list[StagedWeather] = []
    for c in sorted(ctx["chunks"], key=lambda x: x["file"]):
        rows += stage_weather_chunk(reader.weather_chunk(c["file"]), c, ctx["source_snapshot_id"], ctx["fmisid"])
    expected = sum(s.elements for s in cfg.sources.weather.raw_files)
    if len(rows) != expected:
        raise StagingError(f"staged {len(rows)} weather observations but the pins say {expected}")
    return rows


def _summarise(cfg: Config, res: StagingResult, recon: list[dict[str, Any]], handoff: dict[str, Any]) -> dict[str, Any]:
    ev = res.events
    by_pop = Counter(e.population for e in ev)
    sessions_by_pop: dict[str, set[str]] = {}
    for e in ev:
        sessions_by_pop.setdefault(e.population, set()).add(e.session_id)
    both = sorted(set.intersection(*sessions_by_pop.values())) if len(sessions_by_pop) > 1 else []
    per_file_rows = Counter((e.source_file, e.raw_row_sha256) for e in ev)
    return {
        "stage": "staging",
        "core_outcome": res.core.value, "context_outcome": res.context.value,
        "input_fingerprint": handoff.get("input_fingerprint"),
        "source_snapshot_ids": {"flavoria": handoff["core"].get("source_snapshot_id"), "fmi_weather": handoff["context"].get("source_snapshot_id")},
        "events": {
            "rows": len(ev), "by_population": dict(sorted(by_pop.items())),
            "distinct_session_ids": len({e.session_id for e in ev}), "distinct_session_keys": len({e.session_key for e in ev}),
            "session_ids_present_in_both_populations": both,
            "exact_duplicate_raw_rows_within_file": sum(c - 1 for c in per_file_rows.values() if c > 1),
            "by_timezone_handling": dict(sorted(Counter(e.timezone_handling for e in ev).items())),
            "event_time_status": dict(sorted(Counter(e.event_time_status for e in ev).items())),
            "identification_time_status": dict(sorted(Counter(e.identification_time_status for e in ev).items())),
            "row_parse_status": dict(sorted(Counter(e.row_parse_status for e in ev).items())),
            "weight_parse_status": dict(sorted(Counter(e.weight_parse_status for e in ev).items())),
            "schema_variant": dict(sorted(Counter(str(e.schema_variant) for e in ev).items())),
            "rows_with_weighing_type": sum(1 for e in ev if e.weighing_type is not None),
            "rows_with_unmapped_cells": sum(1 for e in ev if e.unmapped_cells),
            "rows_with_component_name_edge_whitespace": sum(1 for e in ev if e.component_name_had_edge_whitespace),
        } if ev else {"rows": 0},
        "weather": {"rows": len(res.weather), "value_status": dict(sorted(Counter(w.value_status for w in res.weather).items())),
                    "parameters": sorted({w.parameter for w in res.weather}),
                    "distinct_hours": len({w.obs_time_raw for w in res.weather if w.parameter == cfg.sources.weather.request["parameters"][0]})},
        "transformations": TRANSFORMATIONS,
        "messages": [{"level": m.level.value, "code": m.code, "text": m.text} for m in res.messages],
    }


def run_staging(cfg: Config, reader: VerifiedReader, out_dir: Path) -> StagingResult:
    handoff = reader.handoff
    d = out_dir / OUT_SUBDIR
    d.mkdir(parents=True, exist_ok=True)
    res = StagingResult()
    recon: list[dict[str, Any]] = []

    try:
        res.events, recon = _stage_core(cfg, reader)
    except (HandoffError, StagingError) as exc:
        res.core, res.events, recon = LaneOutcome.FAILED, [], []
        res.messages.append(Message(Level.ERROR, "STG", f"core staging stopped: {exc}"))
        _remove(d / EVENTS_CSV, d / RECON_CSV)          # a stale table must never look current

    try:
        res.weather = _stage_context(cfg, reader)
    except (HandoffError, StagingError) as exc:
        res.context, res.weather = LaneOutcome.BLOCKED, []
        res.messages.append(Message(Level.ERROR, "STG", f"weather staging stopped: {exc}. Weather-dependent outputs are blocked; core staging is unaffected"))
        _remove(d / WEATHER_CSV)

    if res.core is LaneOutcome.OK:
        write_csv(d / EVENTS_CSV, res.events, list(EVENT_COLUMNS))
        write_csv(d / RECON_CSV, recon, RECON_COLUMNS)
    if res.context is LaneOutcome.OK:
        write_csv(d / WEATHER_CSV, res.weather, list(WEATHER_COLUMNS))

    res.summary = _summarise(cfg, res, recon, handoff)
    hashes = {n: digest_file(d / n).sha256 for n in (EVENTS_CSV, WEATHER_CSV, RECON_CSV) if (d / n).exists()}
    res.summary["output_sha256"] = dict(sorted(hashes.items()))
    write_json(d / SUMMARY_JSON, res.summary)
    res.hashes = {**hashes, SUMMARY_JSON: digest_file(d / SUMMARY_JSON).sha256}
    return res
