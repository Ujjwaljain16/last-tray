"""fact_dining_session and fact_session_component, reconstructed from the CANONICAL event rows and the WP4 dispositions.

This module does not use WP4's session profiles and does not read `rule_weight_sum_g`; that WP4 value is only a control, compared in
src/model/control.py. Two event sets are used, and the difference is deliberate:

  business fields (weight, components, event counts)  -> MODELLABLE events only
  timing and identity fields (first/last, span, tray) -> every event that is not an exact repeat (MODELLABLE + QUARANTINED)

so a quarantined session stays traceable in time but never yields a selected-meal weight or a component count.
`derived_selected_meal_weight_g` is DERIVED. It is not consumed quantity, not food waste and not actual intake.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any

from src.config import Config
from src.model.inputs import ModelInputs

UTC_FMT = "%Y-%m-%dT%H:%M:%SZ"


def parse_utc(text: str | None) -> datetime | None:
    return datetime.strptime(text, UTC_FMT) if text else None


def _group(events: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for e in events:
        groups[e["session_key"]].append(e)
    return dict(sorted(groups.items()))


def selected_meal_weight(modellable: list[dict[str, Any]]) -> int | None:
    """Sum of the modellable events' weights; NULL if there are none or any weight is not a valid integer. Never 0 by default."""
    weights = [e["component_weight_g"] for e in modellable]
    if not weights or any(w is None for w in weights):
        return None
    return sum(weights)


def _extremes(observed: list[dict[str, Any]]) -> tuple[dict | None, dict | None]:
    timed = [e for e in observed if e["event_time_utc"]]
    if not timed:
        return None, None
    key = lambda e: (e["event_time_utc"], e["source_file"], e["source_row_number"])
    return min(timed, key=key), max(timed, key=lambda e: (e["event_time_utc"], e["source_file"], -e["source_row_number"]))


def _single(values: set[str | None]) -> str | None:
    values.discard(None)
    values.discard("")
    return next(iter(values)) if len(values) == 1 else None


def limited_scale_days(inp: ModelInputs) -> set[tuple[str, str]]:
    """(scale_id, local date) cells where the two exports share no normalised component name (rule I07)."""
    cells = set()
    for i in inp.issues:
        if i["rule_id"] == "I07":
            scale, day = i["entity_id"].split("|")
            cells.add((scale, day))
    return cells


def build_sessions(events: list[dict[str, Any]], inp: ModelInputs, cfg: Config) -> list[dict[str, Any]]:
    primary = cfg.populations.primary.code.value
    groups = _group(events)
    populations_of: dict[str, set[str]] = defaultdict(set)
    for e in events:
        populations_of[e["session_id"]].add(e["population"])
    limited = limited_scale_days(inp)
    rows = []
    for key, evs in groups.items():
        first_e = evs[0]
        modellable = [e for e in evs if e["disposition"] == "MODELLABLE"]
        observed = [e for e in evs if e["disposition"] != "DUPLICATE_EXCLUDED"]
        first, last = _extremes(observed)
        v = inp.session_status[key]
        quarantined = key in inp.quarantined_keys
        span = int((parse_utc(last["event_time_utc"]) - parse_utc(first["event_time_utc"])).total_seconds()) if first and last else None
        ident_local = _single({e["identification_time_local"] for e in observed})
        ident_utc = _single({e["identification_time_utc"] for e in observed})
        weight = selected_meal_weight(modellable)
        components = {e["component_id_normalized"] for e in modellable if e["component_id_normalized"]}
        error_ids, warn_ids = v["error_rule_ids"], v["warn_rule_ids"]
        severity = "ERROR" if error_ids else "WARN" if warn_ids else "INFO" if v["info_rule_ids"] else "NONE"
        is_primary = first_e["population"] == primary
        core_ready = bool(is_primary and not quarantined and modellable and not error_ids and weight is not None and first is not None)
        cells = {(e["scale_id"], e["event_time_local"][:10]) for e in modellable if e["event_time_local"]}
        rows.append({
            "session_key": key, "session_id": first_e["session_id"], "population": first_e["population"], "is_primary_population": is_primary,
            "source_snapshot_id": first_e["source_snapshot_id"], "source_files": ";".join(sorted({e["source_file"] for e in evs})),
            "tray_id": _single({e["tray_id"] for e in observed}), "service_date": first["event_time_local"][:10] if first else None,
            "first_weighing_local": first["event_time_local"] if first else None, "first_weighing_utc": first["event_time_utc"] if first else None,
            "last_weighing_local": last["event_time_local"] if last else None, "last_weighing_utc": last["event_time_utc"] if last else None,
            "identification_time_local": ident_local, "identification_time_utc": ident_utc,
            "session_span_s": span, "session_duration_minutes": None if span is None else round(span / 60, 6),
            "event_count": len(evs), "modellable_event_count": len(modellable),
            "duplicate_excluded_event_count": sum(e["disposition"] == "DUPLICATE_EXCLUDED" for e in evs),
            "quarantined_event_count": sum(e["disposition"] == "QUARANTINED" for e in evs),
            "derived_selected_meal_weight_g": weight,
            "distinct_component_count": len(components) if modellable else None,
            "distinct_raw_component_count": len({e["component_name_raw"] for e in modellable}) if modellable else None,
            "distinct_component_count_status": "LIMITED" if cells & limited else "READY_WITH_LIMITATION",
            "identity_conflict": len(populations_of[first_e["session_id"]]) > 1,
            "is_quarantined": quarantined, "quarantine_rule_ids": v["quarantine_rule_ids"] or None, "core_ready": core_ready,
            "max_validation_severity": severity, "validation_error_rule_ids": error_ids or None, "validation_warn_rule_ids": warn_ids or None,
            "has_session_warn": v["session_level_warn"] == "true", "has_event_warn": v["event_level_warn"] == "true",
            "quality_status": "INVALID" if quarantined or error_ids else "WARN" if warn_ids else "VALID",
            # weather join fields are filled by src.model.weather
            "weather_hour_utc": None, "weather_fmisid": None, "weather_join_status": "NO_TIMESTAMP", "weather_matched": False,
            "weather_r_1h_null": None, "weather_ri_10min_null": None,
        })
    return rows


def build_components(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One row per distinct normalised component of a session, from MODELLABLE events. Exact string identity only; no alias table."""
    rows = []
    for key, evs in _group([e for e in events if e["disposition"] == "MODELLABLE" and e["component_id_normalized"]]).items():
        by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for e in evs:
            by_name[e["component_id_normalized"]].append(e)
        for name, es in sorted(by_name.items()):
            weights = [e["component_weight_g"] for e in es]
            rows.append({
                "session_key": key, "session_id": es[0]["session_id"], "population": es[0]["population"], "component_id_normalized": name,
                "component_name_raw_variants": "|".join(sorted({e["component_name_raw"] for e in es})), "component_weighing_event_count": len(es),
                "scale_ids": ";".join(sorted({e["scale_id"] for e in es})),
                "derived_component_weight_g": None if any(w is None for w in weights) else sum(weights),
                "source_snapshot_id": es[0]["source_snapshot_id"], "source_row_lineage": ";".join(sorted(e["event_id"] for e in es)),
            })
    return rows
