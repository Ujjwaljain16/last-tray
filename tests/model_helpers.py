"""Builders for canonical-model tests: staged events plus WP4-style dispositions, assembled into ModelInputs by hand."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from src.model.inputs import ModelInputs
from src.validate.load import Ev, StagedInputs, Wx
from src.validate.sessions import build_profiles, find_repeats

from tests.validate_helpers import make_event  # noqa: F401  (re-exported for the model tests)


def model_inputs(events: list[Ev], quarantine: Iterable[str] = (), errors: dict[str, str] | None = None, warns: dict[str, str] | None = None,
                 session_warn: Iterable[str] = (), issues: list[dict] | None = None, weather: list[Wx] | None = None) -> ModelInputs:
    """Dispositions follow the WP4 rule: quarantined key wins, then exact repeat, else MODELLABLE."""
    quarantined = set(quarantine)
    repeats = find_repeats(events)
    errors, warns = errors or {}, warns or {}
    event_status = {}
    for e in events:
        d = "QUARANTINED" if e.session_key in quarantined else "DUPLICATE_EXCLUDED" if e.event_id in repeats else "MODELLABLE"
        event_status[e.event_id] = {"disposition": d, "error_rule_ids": "", "warn_rule_ids": "I02" if e.event_id in repeats else "", "info_rule_ids": ""}
    profiles = build_profiles(events, repeats)
    status = {}
    for k, p in profiles.items():
        status[k] = {"error_rule_ids": errors.get(k, "I01" if k in quarantined else ""), "warn_rule_ids": warns.get(k, ""), "info_rule_ids": "",
                     "quarantine_rule_ids": "I01" if k in quarantined else "", "session_level_warn": "true" if k in set(session_warn) else "false",
                     "event_level_warn": "false", "rule_weight_sum_g": "" if p.rule_weight_sum_g is None else str(p.rule_weight_sum_g),
                     "span_s": "" if p.span_s is None else f"{p.span_s:g}", "events_staged": str(len(p.events)), "events_counted": str(len(p.counted)),
                     "exact_repeats_excluded": str(len(p.events) - len(p.counted)),
                     "first_weighing_local": p.first_local.isoformat() if p.first_local else ""}
    staged = StagedInputs({}, events, [], weather, None if weather is not None else "no weather", {})
    return ModelInputs(staged, {"weather_status": "PASSED"}, event_status, status, sorted(quarantined), issues or [], [])


def wx(hour: str, parameter="t2m", value="10.5", status="OK", n=[0]) -> Wx:
    n[0] += 1
    t = datetime.strptime(hour, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return Wx(f"w.xml#{n[0]}", "fmi-1", "w.xml", "100949", hour, t, parameter, value if status == "OK" else "NaN", float(value) if status == "OK" else None, status,
              "SOURCE_UTC_STATED")
