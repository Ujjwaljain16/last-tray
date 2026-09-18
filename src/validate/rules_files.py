"""File-level and timezone rules (S03, T07, T08, T10) and the DST round-trip check (X04).

Timezone status labels are PROVENANCE metadata. Nothing here re-interprets the approved file-specific +3h handling: it only
confirms that the staged data still carries it where, and only where, the configuration says. The wording of the decision is
"strongest-supported engineering decision based on cross-export temporal consistency checks; the original source does not
explicitly confirm the timezone metadata".
"""
from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

from src.config import Config, TimezoneOverride
from src.validate.load import Ev
from src.validate.model import BASIS_EVENT, BASIS_FILE, Issue
from src.validate.sessions import raw_wall_time
from src.vocab import TimezoneHandling

ZONE = ZoneInfo("Europe/Helsinki")


def _by_file(events: list[Ev]) -> dict[str, list[Ev]]:
    files: dict[str, list[Ev]] = defaultdict(list)
    for e in events:
        files[e.source_file].append(e)
    return dict(sorted(files.items()))


def _hour(t: datetime) -> float:
    return t.hour + t.minute / 60 + t.second / 3600


def median_first_event_hour(events: list[Ev], *, raw: bool) -> float | None:
    """Median over service days of the hour of the day's first event: as written in the source (raw) or after the timezone rule."""
    first: dict[str, datetime] = {}
    for e in events:
        t = raw_wall_time(e) if raw else e.event_time_local
        if t is not None and (t.date().isoformat() not in first or t < first[t.date().isoformat()]):
            first[t.date().isoformat()] = t
    return statistics.median(_hour(t) for t in first.values()) if first else None


def file_timezone_profile(events: list[Ev]) -> dict[str, dict]:
    return {f: {"raw": median_first_event_hour(evs, raw=True), "treated": median_first_event_hour(evs, raw=False)} for f, evs in _by_file(events).items()}


def check_files(events: list[Ev], cfg: Config) -> list[Issue]:
    """S03 optional column absent (INFO); T08 dotted timestamp format (INFO); T07 median first-event hour outside the band (WARN)."""
    t07 = cfg.thresholds.rules["T07"]
    prof = file_timezone_profile(events)
    out: list[Issue] = []
    for f, evs in _by_file(events).items():
        first = evs[0]

        def file_issue(rule: str, description: str, observed: str, expected: str) -> Issue:
            return Issue(rule, "file", f, BASIS_FILE, description, observed, expected, population=first.population,
                         source_snapshot_id=first.source_snapshot_id, source_file=f)

        if not any(e.weighing_type for e in evs):
            out.append(file_issue("S03", "the optional column weighting_type is absent from this file (weighing_type is NULL)", f"{len(evs)} rows without it", "column may be absent"))
        dotted = sorted({c for e in evs for c, fmt in (("weighing_event_time", e.event_time_source_format), ("user_identification_time", e.identification_time_source_format)) if fmt == "dot"})
        if dotted:
            out.append(file_issue("T08", "dotted timestamp format (YYYY.MM.DD) in " + ", ".join(dotted), ";".join(dotted), "the parser accepts both formats per column"))
        raw_h, treated_h = prof[f]["raw"], prof[f]["treated"]
        if raw_h is not None and treated_h is not None and not (t07.low <= raw_h < t07.high and t07.low <= treated_h < t07.high):
            override = next((e for e in evs if e.timezone_handling == TimezoneHandling.NORMALISED_PLUS_3H_STRONGEST_SUPPORT.value), None)
            state = ("a file-specific +3h normalization was applied (strongest-supported, not source-confirmed)" if override else "NO normalization was applied")
            out.append(file_issue("T07", f"median first-event hour is outside [{t07.low:g}, {t07.high:g}); {state}",
                                  f"raw median {raw_h:.2f} h; after the timezone rule {treated_h:.2f} h", f"median first-event hour in [{t07.low:g}, {t07.high:g})"))
    return out


def check_override_scope(events: list[Ev], cfg: Config) -> list[Issue]:
    """T10 re-checked on staged rows: the override labels appear on exactly the configured file(s), on every row of them, with the
    configured offset, inside the validated date range and the evidence band; every other row is SOURCE_LOCAL_ASSUMED with offset 0."""
    overrides = cfg.timezone.overrides
    shifted = TimezoneHandling.NORMALISED_PLUS_3H_STRONGEST_SUPPORT.value
    out: list[Issue] = []

    def bad(entity: str, description: str, observed: str, expected: str, ev: Ev | None = None) -> None:
        out.append(Issue("T10", "file" if ev is None else "event", entity, BASIS_FILE if ev is None else BASIS_EVENT, description, observed, expected,
                         population=(ev.population if ev else ""), source_file=(ev.source_file if ev else entity), event_id=(ev.event_id if ev else ""),
                         source_snapshot_id=(ev.source_snapshot_id if ev else ""), source_row_lineage=(ev.event_id if ev else entity)))

    for e in events:
        ov: TimezoneOverride | None = overrides.get(e.source_file)
        if ov is None and (e.timezone_handling != TimezoneHandling.SOURCE_LOCAL_ASSUMED.value or e.timezone_offset_hours != 0):
            bad(e.event_id, "a timezone override label or offset appears on a file that has no configured override",
                f"{e.timezone_handling}, +{e.timezone_offset_hours}h", "SOURCE_LOCAL_ASSUMED, +0h", e)
        if ov is not None and (e.timezone_handling != ov.label.value or e.timezone_offset_hours != ov.offset_hours):
            bad(e.event_id, "a row of the override file does not carry the configured override", f"{e.timezone_handling}, +{e.timezone_offset_hours}h",
                f"{ov.label.value}, +{ov.offset_hours}h", e)
    for name, ov in sorted(overrides.items()):
        rows = [e for e in events if e.source_file == name]
        raw_dates = sorted({t.date() for t in map(raw_wall_time, rows) if t})
        if rows and (raw_dates[0] < ov.valid_for.first_event_date or raw_dates[-1] > ov.valid_for.last_event_date):
            bad(name, "raw event dates fall outside the range the override was validated on", f"{raw_dates[0]}..{raw_dates[-1]}",
                f"{ov.valid_for.first_event_date}..{ov.valid_for.last_event_date}")
        raw_h = median_first_event_hour(rows, raw=True)
        lo, hi = ov.valid_for.raw_median_first_event_hour_band
        if raw_h is not None and not lo <= raw_h <= hi:
            bad(name, "the shift the override corrects is not visible in the raw times", f"raw median {raw_h:.2f} h", f"[{lo:g}, {hi:g}]")
    return out


def check_dst_round_trip(events: list[Ev]) -> tuple[list[Issue], int]:
    """X04: local -> UTC -> local reproduces the staged local time, using the zone database directly (independent of staging code).
    Returns (issues, number of timestamps checked)."""
    out: list[Issue] = []
    checked = 0
    for e in events:
        for label, local, utc in (("weighing_event_time", e.event_time_local, e.event_time_utc), ("user_identification_time", e.identification_time_local, e.identification_time_utc)):
            if local is None or utc is None:
                continue
            checked += 1
            back = utc.astimezone(ZONE).replace(tzinfo=None)
            if back != local:
                out.append(Issue("X04", "event", f"{e.event_id}|{label}", BASIS_EVENT, f"{label}: local -> UTC -> local does not round-trip",
                                 f"{local.isoformat()} -> {utc.isoformat()} -> {back.isoformat()}", "equal", session_key=e.session_key, event_id=e.event_id,
                                 population=e.population, source_snapshot_id=e.source_snapshot_id, source_file=e.source_file, source_row_lineage=e.event_id))
    return out, checked

