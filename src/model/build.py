"""Canonical model orchestration (WP5): verified staging + verified WP4 outputs in, canonical tables and control evidence out. Offline.

Never opens data/raw. Builds the five canonical tables, reconstructs `derived_selected_meal_weight_g` independently and compares it with
the WP4 working value, and blocks (writing only the control files, so the difference can be inspected) if any core control fails.
Core failure => exit 4 and stale canonical tables removed. Weather failure => fact_weather blocked, core model unaffected.

Not here: M1-M5, sensitivity, dashboards, judgement. Nothing here estimates consumption or waste.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.config import Config
from src.ingest.hashing import digest_file
from src.ingest.manifest import write_csv, write_json
from src.model import control, schema
from src.model.events import build_events
from src.model.inputs import ModelInputError, ModelInputs, load_model_inputs
from src.model.sessions import build_components, build_sessions
from src.model.volume import build_daily_volume
from src.model.weather import WeatherModelError, build_weather, join_sessions
from src.validate.reconcile import Check

OUT_SUBDIR = "model"
MANIFEST_JSON = "model_manifest.json"
CONTROL_CSV = "model_control_summary.csv"
SESSION_CONTROL_CSV = "session_weight_control.csv"
TABLE_FILES = {t.name: f"{t.name}.csv" for t in schema.TABLES}
DETERMINISTIC_FILES = (*TABLE_FILES.values(), MANIFEST_JSON, CONTROL_CSV, SESSION_CONTROL_CSV)
MODEL_VERSION = "wp5-1"


@dataclass
class ModelResult:
    core_status: str = "BUILT"             # BUILT | BLOCKED
    weather_status: str = "BUILT"          # BUILT | BLOCKED
    error: str | None = None
    tables: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    checks: list[Check] = field(default_factory=list)
    control_rows: list[dict[str, Any]] = field(default_factory=list)
    manifest: dict[str, Any] = field(default_factory=dict)
    hashes: dict[str, str] = field(default_factory=dict)

    @property
    def counts(self) -> dict[str, int]:
        return {name: len(rows) for name, rows in self.tables.items()}


def _remove(d: Path, names) -> None:
    for n in names:
        (d / n).unlink(missing_ok=True)


def _manifest(res: ModelResult, inp: ModelInputs, cfg: Config, written: dict[str, str]) -> dict[str, Any]:
    s = inp.validation_summary
    return {
        "stage": "model", "model_version": MODEL_VERSION, "core_status": res.core_status, "weather_status": res.weather_status,
        "inputs": {"input_fingerprint": inp.staged.summary.get("input_fingerprint"), "source_snapshot_ids": inp.staged.summary.get("source_snapshot_ids"),
                   "staging_table_sha256": inp.staged.table_sha256, "validation_run_id": s["run_id"], "validation_output_sha256": s["output_sha256"]},
        "tables": {t.name: {"grain": t.grain, "key": list(t.key), "rows": len(res.tables.get(t.name, [])), "columns": list(t.column_names),
                            "semantic_classes": dict(sorted(Counter(c.cls for c in t.columns).items())), "sha256": written.get(t.name)} for t in schema.TABLES},
        "controls": {"checks": len(res.checks), "pass": sum(c.status == "PASS" for c in res.checks), "warn": sum(c.status == "WARN" for c in res.checks),
                     "fail": sum(c.status == "FAIL" for c in res.checks), "info": sum(c.status == "INFO" for c in res.checks),
                     "failed_checks": [c.check_id for c in res.checks if c.status == "FAIL"]},
        "semantic_chain": ["OBSERVED component weighing events", "DERIVED selected meal weight", "UNKNOWN actual consumed quantity", "SOURCE GAP actual food waste"],
        "field_notes": {"derived_selected_meal_weight_g": "DERIVED from MODELLABLE events; not consumed quantity, not food waste, not actual intake",
                        "rule_weight_sum_g": "WP4 validation working value, used only as a reconciliation control",
                        "sessions": "Observed Valid Sessions; an observation of the export, not demand"},
    }


def run_model(cfg: Config, out_dir: Path) -> ModelResult:
    d = out_dir / OUT_SUBDIR
    d.mkdir(parents=True, exist_ok=True)
    res = ModelResult()
    try:
        inp = load_model_inputs(out_dir)
    except ModelInputError as exc:
        res.core_status, res.weather_status, res.error = "BLOCKED", "BLOCKED", str(exc)
        _remove(d, DETERMINISTIC_FILES)                            # a stale canonical table must never look current
        return res

    events = build_events(inp)
    sessions = build_sessions(events, inp, cfg)
    components = build_components(events)
    weather: list[dict[str, Any]] | None = None
    weather_reason = None
    if inp.validation_summary.get("weather_status") == "BLOCKED":
        weather_reason = "validation reports the weather lane as BLOCKED"
    else:
        try:
            weather = build_weather(inp, cfg)
        except WeatherModelError as exc:
            weather_reason = str(exc)
    join_sessions(sessions, weather, weather_reason)
    volume = build_daily_volume(sessions, cfg)
    res.tables = {"fact_weighing_event": events, "fact_dining_session": sessions, "fact_session_component": components,
                  "fact_weather": weather or [], "fact_daily_volume": volume}
    res.control_rows = control.session_control_rows(sessions, inp)
    res.checks = control.control_checks(events, sessions, components, weather, volume, res.control_rows, inp, cfg)
    if weather is None:
        res.weather_status = "BLOCKED"
    if any(c.status == "FAIL" and c.area != "weather" for c in res.checks):
        res.core_status = "BLOCKED"
        res.error = "control checks failed: " + ", ".join(c.check_id for c in res.checks if c.status == "FAIL" and c.area != "weather")

    _write(d, res, inp, cfg)
    return res


def _write(d: Path, res: ModelResult, inp: ModelInputs, cfg: Config) -> None:
    write_csv(d / CONTROL_CSV, [c.row() for c in res.checks], list(control.CONTROL_COLUMNS))
    write_csv(d / SESSION_CONTROL_CSV, res.control_rows, list(control.SESSION_CONTROL_COLUMNS))
    tables_out = [t for t in schema.TABLES if res.core_status == "BUILT" and not (t.name == "fact_weather" and res.weather_status == "BLOCKED")]
    _remove(d, [TABLE_FILES[t.name] for t in schema.TABLES if t not in tables_out])
    for t in tables_out:
        write_csv(d / TABLE_FILES[t.name], res.tables[t.name], list(t.column_names))
    written = {t.name: digest_file(d / TABLE_FILES[t.name]).sha256 for t in tables_out}
    if res.core_status == "BLOCKED":
        res.tables = {k: [] for k in res.tables}              # a blocked model publishes no canonical rows
    res.manifest = _manifest(res, inp, cfg, written)
    write_json(d / MANIFEST_JSON, res.manifest)
    res.hashes = {n: digest_file(d / n).sha256 for n in DETERMINISTIC_FILES if (d / n).exists()}
