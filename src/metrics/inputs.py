"""Inputs of the metric layer: the CANONICAL MODEL tables, verified against the model manifest. Nothing else.

Metrics are computed from `fact_dining_session` (and cross-checked against `fact_session_component`, `fact_daily_volume`, `fact_weather`
and `fact_weighing_event`). They never read staging or raw files: WP5 owns the canonical derived fields. A table is trusted only if it
matches the SHA-256, header and row count the model manifest recorded, the manifest reports a BUILT core lane with no failed control,
and it was built on the validation run that is currently on disk.
"""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.ingest.hashing import digest_file
from src.model import schema
from src.model.build import MANIFEST_JSON, OUT_SUBDIR as MODEL_SUBDIR, TABLE_FILES
from src.validate.validate import OUT_SUBDIR as VALIDATION_SUBDIR, SUMMARY_JSON as VALIDATION_SUMMARY


# The one model control that belongs to the WEATHER lane (fact_weather available). Its failure blocks weather outputs only, never the core metrics.
WEATHER_CONTROL = "M22"


class MetricInputError(Exception):
    """A canonical table is missing, altered or inconsistent. No metric may be computed from it."""


@dataclass(frozen=True)
class SessionRow:
    session_key: str
    session_id: str
    population: str
    source_snapshot_id: str
    service_date: str | None
    derived_selected_meal_weight_g: int | None
    distinct_component_count: int | None
    distinct_raw_component_count: int | None
    modellable_event_count: int
    is_quarantined: bool
    core_ready: bool
    has_session_warn: bool
    has_event_warn: bool
    weather_matched: bool
    weather_join_status: str
    weather_r_1h_null: bool | None
    weather_ri_10min_null: bool | None
    identity_conflict: bool


@dataclass
class MetricInputs:
    sessions: list[SessionRow]
    components: list[dict[str, str]]
    daily_volume: list[dict[str, str]]
    events: list[dict[str, str]]
    weather: list[dict[str, str]] | None          # None: fact_weather unavailable (weather lane blocked)
    weather_error: str | None
    manifest: dict[str, Any]
    snapshot_id: str
    columns: dict[str, tuple[str, ...]] = field(default_factory=dict)


def _bool(text: str) -> bool:
    return text == "true"


def _opt_bool(text: str) -> bool | None:
    return None if text == "" else text == "true"


def _opt_int(text: str) -> int | None:
    return None if text == "" else int(text)


def _session(r: dict[str, str]) -> SessionRow:
    return SessionRow(
        r["session_key"], r["session_id"], r["population"], r["source_snapshot_id"], r["service_date"] or None, _opt_int(r["derived_selected_meal_weight_g"]),
        _opt_int(r["distinct_component_count"]), _opt_int(r["distinct_raw_component_count"]), int(r["modellable_event_count"]), _bool(r["is_quarantined"]),
        _bool(r["core_ready"]), _bool(r["has_session_warn"]), _bool(r["has_event_warn"]), _bool(r["weather_matched"]), r["weather_join_status"],
        _opt_bool(r["weather_r_1h_null"]), _opt_bool(r["weather_ri_10min_null"]), _bool(r["identity_conflict"]))


def _read(path: Path, table: schema.Table, recorded: dict[str, Any]) -> list[dict[str, str]]:
    if not path.is_file():
        raise MetricInputError(f"{path.name} is missing: run the model (python -m src.pipeline.run --stages model)")
    if not recorded.get("sha256"):
        raise MetricInputError(f"{MANIFEST_JSON} records no SHA-256 for {table.name}")
    if digest_file(path).sha256 != recorded["sha256"]:
        raise MetricInputError(f"{path.name} does not match the SHA-256 recorded by the model: it was altered or is stale")
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        if tuple(reader.fieldnames or ()) != table.column_names:
            raise MetricInputError(f"{path.name} does not have the declared canonical columns")
        rows = list(reader)
    if len(rows) != recorded["rows"]:
        raise MetricInputError(f"{path.name} has {len(rows)} rows but the model recorded {recorded['rows']}")
    return rows


def load_metric_inputs(out_dir: Path) -> MetricInputs:
    m = out_dir / MODEL_SUBDIR
    manifest_path = m / MANIFEST_JSON
    if not manifest_path.is_file():
        raise MetricInputError(f"{MANIFEST_JSON} is missing: the canonical model has not been built (python -m src.pipeline.run --stages model)")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise MetricInputError(f"{MANIFEST_JSON} is not valid JSON: {exc}") from exc
    if manifest.get("core_status") != "BUILT":
        raise MetricInputError(f"the model reports its core lane as {manifest.get('core_status')}: no metric may be computed from it")
    controls = manifest.get("controls", {})
    weather_lane_failure = 1 if (manifest.get("weather_status") != "BUILT" and controls.get("failed_checks") == [WEATHER_CONTROL]) else 0
    if controls.get("fail", 1) - weather_lane_failure != 0:
        raise MetricInputError("the model manifest reports failed control checks: no metric may be computed from it")
    validation_summary = out_dir / VALIDATION_SUBDIR / VALIDATION_SUMMARY
    if validation_summary.is_file():
        run_id = json.loads(validation_summary.read_text(encoding="utf-8")).get("run_id")
        if run_id != manifest["inputs"]["validation_run_id"]:
            raise MetricInputError("the canonical model was built on a different validation run than the one on disk: rebuild the model")

    tables = manifest["tables"]
    data = {t.name: _read(m / TABLE_FILES[t.name], t, tables[t.name]) for t in (schema.SESSION, schema.COMPONENT, schema.VOLUME, schema.EVENT)}
    weather, weather_error = None, None
    if manifest.get("weather_status") != "BUILT":
        weather_error = f"the model reports the weather lane as {manifest.get('weather_status')}"
    else:
        try:
            weather = _read(m / TABLE_FILES[schema.WEATHER.name], schema.WEATHER, tables[schema.WEATHER.name])
        except MetricInputError as exc:
            weather_error = str(exc)
    sessions = [_session(r) for r in data[schema.SESSION.name]]
    if len({s.session_key for s in sessions}) != len(sessions):
        raise MetricInputError("session_key is not unique in fact_dining_session")
    snapshots = sorted({s.source_snapshot_id for s in sessions})
    if len(snapshots) != 1:
        raise MetricInputError(f"expected one source snapshot in the session table, found {snapshots}")
    return MetricInputs(sessions, data[schema.COMPONENT.name], data[schema.VOLUME.name], data[schema.EVENT.name], weather, weather_error, manifest, snapshots[0])
