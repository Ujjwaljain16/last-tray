"""The verified staging interface for validation.

Validation reads ONLY the staging tables, and only after checking them against what staging recorded about itself: the summary
must say the lane is OK, and each table's SHA-256, header and row count must match. It never opens data/raw and never touches the
ingestion archive. A missing or altered staging table stops the core lane (StagingInputError); a bad weather table blocks only the
weather checks.
"""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.ingest.hashing import digest_file
from src.stage.events import EVENT_COLUMNS
from src.stage.stage import EVENTS_CSV, OUT_SUBDIR, RECON_COLUMNS, RECON_CSV, SUMMARY_JSON, WEATHER_CSV
from src.stage.weather import WEATHER_COLUMNS


class StagingInputError(Exception):
    """A staging artifact is missing, altered, or inconsistent with its own summary. Validation must not run on it."""


@dataclass(frozen=True)
class Ev:
    """The staged event fields validation needs, typed. One row = one component weighing event."""

    event_id: str
    source_snapshot_id: str
    source_file: str
    source_row_number: int
    raw_row_sha256: str
    row_parse_status: str
    schema_variant: str
    population: str
    session_id: str
    session_key: str
    tray_id: str
    scale_id: str
    component_name_raw: str
    component_id_normalized: str
    weight_raw: str
    weight_g: int | None
    weight_parse_status: str
    event_time_raw: str
    event_time_source_format: str
    event_time_local: datetime | None
    event_time_utc: datetime | None
    event_time_status: str
    weighing_type: str
    identification_time_raw: str
    identification_time_source_format: str
    identification_time_local: datetime | None
    identification_time_utc: datetime | None
    identification_time_status: str
    timezone_handling: str
    timezone_offset_hours: int
    unmapped_cells: str


@dataclass(frozen=True)
class Wx:
    observation_id: str
    source_snapshot_id: str
    source_file: str
    fmisid: str
    obs_time_raw: str
    obs_time_utc: datetime | None
    parameter: str
    value_raw: str
    value: float | None
    value_status: str


@dataclass
class StagedInputs:
    summary: dict[str, Any]
    events: list[Ev]
    file_reconciliation: list[dict[str, str]]
    weather: list[Wx] | None                 # None: the weather lane is unusable (see weather_error)
    weather_error: str | None
    table_sha256: dict[str, str]


def _local(s: str) -> datetime | None:
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S") if s else None


def _utc(s: str) -> datetime | None:
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc) if s else None


def _read_table(path: Path, expected_header: tuple[str, ...], recorded_sha: str | None, recorded_rows: int | None) -> list[dict[str, str]]:
    if not path.is_file():
        raise StagingInputError(f"{path.name} is missing: run staging (python -m src.pipeline.run --stages stage)")
    actual = digest_file(path).sha256
    if recorded_sha is None:
        raise StagingInputError(f"{SUMMARY_JSON} records no SHA-256 for {path.name}")
    if actual != recorded_sha:
        raise StagingInputError(f"{path.name} does not match the SHA-256 recorded by staging (expected {recorded_sha[:12]}..., found {actual[:12]}...): it was altered or is stale")
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        if tuple(reader.fieldnames or ()) != expected_header:
            raise StagingInputError(f"{path.name} has an unexpected header")
        rows = list(reader)
    if recorded_rows is not None and len(rows) != recorded_rows:
        raise StagingInputError(f"{path.name} has {len(rows)} rows but staging recorded {recorded_rows}")
    return rows


def _event(r: dict[str, str]) -> Ev:
    return Ev(
        r["event_id"], r["source_snapshot_id"], r["source_file"], int(r["source_row_number"]), r["raw_row_sha256"], r["row_parse_status"],
        r["schema_variant"], r["population"], r["session_id"], r["session_key"], r["tray_id"], r["scale_id"], r["component_name_raw"],
        r["component_id_normalized"], r["weight_raw"], int(r["component_weight_g"]) if r["component_weight_g"] else None,
        r["weight_parse_status"], r["event_time_raw"], r["event_time_source_format"], _local(r["event_time_local"]),
        _utc(r["event_time_canonical_utc"]), r["event_time_status"], r["weighing_type"], r["identification_time_raw"],
        r["identification_time_source_format"], _local(r["identification_time_local"]), _utc(r["identification_time_canonical_utc"]), r["identification_time_status"], r["timezone_handling"],
        int(r["timezone_offset_hours_applied"]), r["unmapped_cells"])


def _weather(r: dict[str, str]) -> Wx:
    return Wx(r["observation_id"], r["source_snapshot_id"], r["source_file"], r["fmisid"], r["obs_time_raw"], _utc(r["obs_time_canonical_utc"]),
              r["parameter"], r["value_raw"], float(r["value"]) if r["value"] else None, r["value_status"])


def load_staging(out_dir: Path) -> StagedInputs:
    d = out_dir / OUT_SUBDIR
    summary_path = d / SUMMARY_JSON
    if not summary_path.is_file():
        raise StagingInputError(f"{SUMMARY_JSON} is missing: staging has not run (python -m src.pipeline.run --stages stage)")
    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise StagingInputError(f"{SUMMARY_JSON} is not valid JSON: {exc}") from exc
    if summary.get("core_outcome") != "OK":
        raise StagingInputError(f"staging reports the core lane as {summary.get('core_outcome')}: there is nothing trustworthy to validate")
    sha = summary.get("output_sha256", {})

    ev_rows = _read_table(d / EVENTS_CSV, EVENT_COLUMNS, sha.get(EVENTS_CSV), summary["events"]["rows"])
    events = [_event(r) for r in ev_rows]
    if len({e.event_id for e in events}) != len(events):
        raise StagingInputError("event_id is not unique in the staged events")
    recon = _read_table(d / RECON_CSV, tuple(RECON_COLUMNS), sha.get(RECON_CSV), None)

    weather: list[Wx] | None = None
    weather_error: str | None = None
    if summary.get("context_outcome") != "OK":
        weather_error = f"staging reports the weather lane as {summary.get('context_outcome')}"
    else:
        try:
            weather = [_weather(r) for r in _read_table(d / WEATHER_CSV, WEATHER_COLUMNS, sha.get(WEATHER_CSV), summary["weather"]["rows"])]
            if len({o.observation_id for o in weather}) != len(weather):
                raise StagingInputError("observation_id is not unique in the staged weather")
        except StagingInputError as exc:
            weather, weather_error = None, str(exc)
    return StagedInputs(summary, events, recon, weather, weather_error, {k: v for k, v in sorted(sha.items())})
