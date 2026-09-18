"""fact_weighing_event: one canonical row per staged event. Nothing is removed; disposition says what each row may be used for."""
from __future__ import annotations

from typing import Any

from src.model.inputs import ModelInputs
from src.stage.timestamps import iso_local, iso_utc


def _ids(text: str) -> str:
    return text or ""


def quality_of(error_ids: str, warn_ids: str, disposition: str) -> str:
    if error_ids or disposition == "QUARANTINED":
        return "INVALID"
    return "WARN" if warn_ids else "VALID"


def build_events(inp: ModelInputs) -> list[dict[str, Any]]:
    rows = []
    for e in inp.staged.events:                                   # staging order = (source_file, source_row_number)
        s = inp.event_status[e.event_id]
        disposition = s["disposition"]
        rows.append({
            "event_id": e.event_id, "source_snapshot_id": e.source_snapshot_id, "raw_artifact_id": e.raw_artifact_id, "source_file": e.source_file,
            "source_row_number": e.source_row_number, "raw_row_sha256": e.raw_row_sha256, "population": e.population, "session_id": e.session_id,
            "session_key": f"{e.session_id}|{e.population}", "tray_id": e.tray_id, "scale_id": e.scale_id,
            "station_family": e.scale_id.split("-")[0] if e.scale_id else None, "component_name_raw": e.component_name_raw,
            "component_id_normalized": e.component_id_normalized or None, "weight_raw": e.weight_raw, "component_weight_g": e.weight_g,
            "weight_status": e.weight_parse_status, "weighing_type": e.weighing_type or None, "event_time_raw": e.event_time_raw,
            "event_time_local": iso_local(e.event_time_local), "event_time_utc": iso_utc(e.event_time_utc), "event_time_status": e.event_time_status,
            "identification_time_raw": e.identification_time_raw, "identification_time_local": iso_local(e.identification_time_local),
            "identification_time_utc": iso_utc(e.identification_time_utc), "identification_time_status": e.identification_time_status,
            "timezone_handling": e.timezone_handling, "timezone_offset_hours_applied": e.timezone_offset_hours,
            "timezone_transformation_reason": e.timezone_transformation_reason, "disposition": disposition,
            "is_modellable": disposition == "MODELLABLE", "is_exact_duplicate": disposition == "DUPLICATE_EXCLUDED" or "I02" in s["warn_rule_ids"].split(";"),
            "quarantine_rule_ids": (inp.session_status[f"{e.session_id}|{e.population}"]["quarantine_rule_ids"] or None) if disposition == "QUARANTINED" else None,
            "quality_status": quality_of(s["error_rule_ids"], s["warn_rule_ids"], disposition),
            "validation_error_rule_ids": _ids(s["error_rule_ids"]) or None, "validation_warn_rule_ids": _ids(s["warn_rule_ids"]) or None,
            "validation_info_rule_ids": _ids(s["info_rule_ids"]) or None,
        })
    return rows
