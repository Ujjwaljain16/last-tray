"""Builders for validation tests: staged events written by hand, so each rule can be tested at its exact boundary."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.validate.load import Ev
from src.validate.sessions import build_profiles, find_repeats

REG, NON = "registered_export", "non_registered_export"
_counter = {"n": 0}


def utc_of(local: datetime) -> datetime:
    """Helsinki local -> UTC for October 2020 test times (before the 2020-10-25 change: +3h)."""
    return (local - timedelta(hours=3)).replace(tzinfo=timezone.utc)


def make_event(session_id="s1", population=REG, weight=100, scale="koti2-vasen-salaatti1", name="salad", local="2020-10-09T11:00:00", file="f.csv",
               row=None, tray="tray1", ident_offset_s=60, raw_hash=None, handling="SOURCE_LOCAL_ASSUMED", offset_h=0, ident_at=None, **over) -> Ev:
    _counter["n"] += 1
    row = row or _counter["n"]
    t = datetime.strptime(local, "%Y-%m-%dT%H:%M:%S")
    ident = datetime.strptime(ident_at, "%Y-%m-%dT%H:%M:%S") if ident_at else t + timedelta(seconds=ident_offset_s)
    base = dict(
        event_id=f"{file}#{row}", source_snapshot_id="snap-1", source_file=file, source_row_number=row, raw_row_sha256=raw_hash or f"h{file}{row}",
        row_parse_status="OK", schema_variant="V", population=population, session_id=session_id, session_key=f"{session_id}|{population}", tray_id=tray,
        scale_id=scale, component_name_raw=name, component_id_normalized=name.strip().casefold(), weight_raw=str(weight), weight_g=weight,
        weight_parse_status="OK", event_time_raw=local.replace("T", " "), event_time_source_format="dash", event_time_local=t, event_time_utc=utc_of(t),
        event_time_status="OK", weighing_type="line", identification_time_raw=ident.strftime("%Y-%m-%d %H:%M:%S"), identification_time_source_format="dash",
        identification_time_local=ident, identification_time_utc=utc_of(ident), identification_time_status="OK", timezone_handling=handling,
        timezone_offset_hours=offset_h, unmapped_cells="")
    base.update(over)
    return Ev(**base)


def profiles_of(events: list[Ev]):
    repeats = find_repeats(events)
    return build_profiles(events, repeats), repeats
