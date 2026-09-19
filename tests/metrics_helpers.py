"""Builders for metric tests: canonical session rows written by hand so each metric can be tested at its exact boundary."""
from __future__ import annotations

import itertools

from src.metrics.inputs import SessionRow

REG, NON = "registered_export", "non_registered_export"
_ids = itertools.count(1)


def session(weight=500, components=5, population=REG, quarantined=False, core_ready=None, session_warn=False, event_warn=False, weather=True,
            service_date="2020-10-12", session_id=None, modellable=None, **over) -> SessionRow:
    n = next(_ids)
    sid = session_id or f"s{n}"
    ready = (population == REG and not quarantined and weight is not None) if core_ready is None else core_ready
    base = dict(session_key=f"{sid}|{population}", session_id=sid, population=population, source_snapshot_id="snap-1", service_date=service_date,
                derived_selected_meal_weight_g=None if quarantined else weight, distinct_component_count=None if quarantined else components,
                distinct_raw_component_count=None if quarantined else components, modellable_event_count=0 if quarantined else (modellable if modellable is not None else 3),
                is_quarantined=quarantined, core_ready=ready, has_session_warn=session_warn, has_event_warn=event_warn, weather_matched=weather and not quarantined,
                weather_join_status="NOT_ATTEMPTED_QUARANTINED" if quarantined else ("MATCHED" if weather else "UNMATCHED_NO_OBSERVATION"),
                weather_r_1h_null=None, weather_ri_10min_null=None, identity_conflict=quarantined)
    base.update(over)
    return SessionRow(**base)
