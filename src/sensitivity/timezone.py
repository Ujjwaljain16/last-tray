"""Timezone evidence for the ONE suspect export: what each candidate offset would do to the time of day and to the weather join.

Only the file(s) named in config/timezone_overrides.yml are shifted; every other file keeps its canonical time. Raw wall-clock times are
recovered from the canonical event fact (canonical local time minus the offset applied), so the original source timestamps are never altered.
The baseline offset is the configured +3h. These figures describe consequences; they do not choose an offset: the +3h decision rests on
cross-export temporal evidence (an exact 10,800 s difference for session3222 and hour-of-day agreement with the other registered-export
files), and the KPIs cannot separate +2h, +3h and +4h.
"""
from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from src.config import Config
from src.sensitivity.data import Agg, WorkingSet
from src.sensitivity.engine import HELSINKI, UTC, shifted_local, t03_violators, Member

OFFSETS = (0, 1, 2, 3, 4)


def _hour(t: datetime) -> float:
    return t.hour + t.minute / 60 + t.second / 3600


def _ceil_utc(local: datetime) -> datetime:
    utc = local.replace(tzinfo=HELSINKI).astimezone(UTC).replace(tzinfo=None)
    floor = utc.replace(minute=0, second=0, microsecond=0)
    return floor if utc == floor else floor + timedelta(hours=1)


def first_event_walls(aggs: list[Agg], files: set[str]) -> dict[str, datetime]:
    """Session key -> earliest raw wall-clock event time, for sessions whose events sit in an override file."""
    out = {}
    for a in aggs:
        walls = [w for w, f, _ in a.events if f in files]
        if walls:
            out[a.key] = min(walls)
    return out


def median_first_event_hour(aggs: list[Agg], files: set[str], hours: int) -> float:
    """Median over service days of the day's first event hour for the override file, after shifting by `hours`."""
    first: dict[str, datetime] = {}
    for a in aggs:
        for wall, f, _ in a.events:
            if f in files:
                t = shifted_local(wall, hours)
                day = t.date().isoformat()
                if day not in first or t < first[day]:
                    first[day] = t
    return statistics.median(_hour(t) for t in first.values())


def other_files_median_hour(ws: WorkingSet, cfg: Config) -> float:
    """Median of the per-file median first-event hours of the OTHER registered-export files (canonical local time)."""
    files = set(cfg.timezone.overrides)
    per_file: dict[str, dict[str, datetime]] = defaultdict(dict)
    for a in ws.aggs.values():
        if a.population != "registered_export" or a.quarantined:
            continue
        for wall, f, _ in a.events:
            if f in files:
                continue
            first = per_file[f]
            day = wall.date().isoformat()
            if day not in first or wall < first[day]:
                first[day] = wall
    return statistics.median(statistics.median(_hour(t) for t in days.values()) for days in per_file.values())


def timezone_rows(ws: WorkingSet, cfg: Config) -> list[dict[str, Any]]:
    files = set(cfg.timezone.overrides)
    baseline_offset = next(iter(cfg.timezone.overrides.values())).offset_hours
    t07 = cfg.thresholds.rules["T07"]
    members = [Member(a, a.weight, 0) for a in ws.baseline]
    walls = first_event_walls(ws.baseline, files)
    others = other_files_median_hour(ws, cfg)

    def join(h: int, key: str) -> tuple[datetime, float | None, float | None]:
        hour = _ceil_utc(shifted_local(walls[key], h))
        t2m, rain = ws.weather.get(hour, (None, None))
        return hour, t2m, rain

    rows = []
    for h in OFFSETS:
        bad = t03_violators(ws, cfg, h, members)
        changed, diffs, rain_hours, rain_known = 0, [], 0, 0
        for key in walls:
            base_hour, base_t, _ = join(baseline_offset, key)
            hour, t, r = join(h, key)
            changed += hour != base_hour
            if t is not None and base_t is not None:
                diffs.append(abs(t - base_t))
            if r is not None:
                rain_known += 1
                rain_hours += r > 0
        med = median_first_event_hour(ws.baseline, files, h)
        rows.append({
            "offset_hours": h, "is_baseline": h == baseline_offset, "sessions_in_shifted_file": len(walls), "t03_quarantined_sessions": len(bad),
            "median_first_event_hour": round(med, 2), "other_registered_files_median_hour": round(others, 2), "gap_to_other_files_h": round(abs(med - others), 2),
            "inside_t07_band": t07.low <= med < t07.high, "weather_hour_changed_sessions": changed,
            "mean_abs_t2m_diff_c": round(sum(diffs) / len(diffs), 3) if diffs else None,
            "rainy_hour_share_pct": round(100 * rain_hours / rain_known, 2) if rain_known else None})
    return rows
