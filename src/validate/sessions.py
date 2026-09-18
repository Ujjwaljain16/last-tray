"""Session profiles used by validation rules: one profile per (session_id, population) key.

A profile is a VALIDATION working structure, not the canonical session model (WP5). It exists so that rules such as the
session span, the single-event check or the weight range can be evaluated. Its weight sum is named `rule_weight_sum_g` for that
reason: the approved derived_selected_meal_weight_g is produced by the canonical model, from the same definition.

Exact duplicates (KEEP_FIRST): a row that repeats an earlier row of the SAME file cell for cell is a "repeat". Repeats stay in
staging and in the event status table; they are only left out of session sums, spans and counts. Repeated weighings of the same
scale that are NOT identical rows are additive scoops and are all counted.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta

from src.validate.load import Ev


@dataclass(frozen=True)
class SessionProfile:
    session_key: str
    session_id: str
    population: str
    events: tuple[Ev, ...]              # every staged row of the key, in (file, row) order
    counted: tuple[Ev, ...]             # the same without exact-duplicate repeats
    source_files: tuple[str, ...]
    tray_ids: tuple[str, ...]
    identification_values: tuple[datetime, ...]     # distinct canonical identification instants among counted rows
    first_local: datetime | None
    first_utc: datetime | None
    last_utc: datetime | None
    rule_weight_sum_g: int | None       # None when any counted weight is not a valid integer

    @property
    def service_date(self) -> str | None:
        return self.first_local.date().isoformat() if self.first_local else None

    @property
    def span_s(self) -> float | None:
        return (self.last_utc - self.first_utc).total_seconds() if self.first_utc and self.last_utc else None

    @property
    def identified_minus_last_s(self) -> float | None:
        if not self.identification_values or not self.last_utc:
            return None
        return (min(self.identification_values) - self.last_utc).total_seconds()

    @property
    def lineage(self) -> str:
        return ";".join(e.event_id for e in self.events)


def find_repeats(events: list[Ev]) -> dict[str, str]:
    """event_id of every exact repeat -> event_id of the first row it repeats (same file, identical raw cells)."""
    first: dict[tuple[str, str], str] = {}
    repeats: dict[str, str] = {}
    for e in sorted(events, key=lambda x: (x.source_file, x.source_row_number)):
        k = (e.source_file, e.raw_row_sha256)
        if k in first:
            repeats[e.event_id] = first[k]
        else:
            first[k] = e.event_id
    return repeats


def build_profiles(events: list[Ev], repeats: dict[str, str]) -> dict[str, SessionProfile]:
    grouped: dict[str, list[Ev]] = defaultdict(list)
    for e in sorted(events, key=lambda x: (x.source_file, x.source_row_number)):
        grouped[e.session_key].append(e)
    profiles: dict[str, SessionProfile] = {}
    for key in sorted(grouped):
        evs = grouped[key]
        counted = [e for e in evs if e.event_id not in repeats]
        utc = [e.event_time_utc for e in counted if e.event_time_utc]
        local = [e.event_time_local for e in counted if e.event_time_local]
        weights = [e.weight_g for e in counted]
        profiles[key] = SessionProfile(
            key, evs[0].session_id, evs[0].population, tuple(evs), tuple(counted), tuple(sorted({e.source_file for e in evs})),
            tuple(sorted({e.tray_id for e in evs})), tuple(sorted({e.identification_time_utc for e in counted if e.identification_time_utc})),
            min(local, default=None), min(utc, default=None), max(utc, default=None),
            sum(weights) if weights and all(w is not None for w in weights) else None)  # type: ignore[arg-type]
    return profiles


def raw_wall_time(e: Ev) -> datetime | None:
    """The event time as written in the source file: the staged local time minus the offset an override applied (if any)."""
    return e.event_time_local - timedelta(hours=e.timezone_offset_hours) if e.event_time_local else None
