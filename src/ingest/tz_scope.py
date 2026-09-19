"""Rule T10: a file-specific timezone normalization is valid only where the evidence supports it.

The +3h normalization was made for ONE file, on the evidence of cross-export temporal consistency checks. It is not a
general statement about any timezone and it is not source-confirmed. This check refuses to apply it if the file, its date
range, or the shift it was made to correct is not what the evidence covered. Failing this check FAILS the core lane.

This is a scope check on raw text only. Parsing and normalising events is staging.
"""
from __future__ import annotations

import csv
import io
import statistics
from datetime import datetime

from src.config import Config, TimezoneOverride
from src.ingest.model import TzScope


def parse_source_timestamp(raw: str) -> datetime:
    """Both source formats: 'YYYY-MM-DD HH:MM:SS' and 'YYYY.MM.DD HH:MM:SS'. Naive: the source states no timezone."""
    return datetime.strptime(raw.strip().replace(".", "-", 1).replace(".", "-", 1), "%Y-%m-%d %H:%M:%S")


def _hour(dt: datetime) -> float:
    return dt.hour + dt.minute / 60 + dt.second / 3600


def check_override(override: TimezoneOverride, csv_bytes: bytes | None, t07_low: float, t07_high: float) -> TzScope:
    v = override.valid_for
    if csv_bytes is None:
        return TzScope(override.filename, "INVALID", None, None, None, None, ("the file's bytes are not available (archive not verified)",))
    reader = csv.DictReader(io.StringIO(csv_bytes.decode("utf-8-sig")))
    if not reader.fieldnames or "weighing_event_time" not in reader.fieldnames:
        return TzScope(override.filename, "INVALID", None, None, None, None, ("no weighing_event_time column",))
    first_per_day: dict[str, datetime] = {}
    try:
        for row in reader:
            dt = parse_source_timestamp(row["weighing_event_time"])
            key = dt.date().isoformat()
            if key not in first_per_day or dt < first_per_day[key]:
                first_per_day[key] = dt
    except (ValueError, TypeError, KeyError) as exc:
        return TzScope(override.filename, "INVALID", None, None, None, None, (f"unparseable weighing_event_time: {exc}",))
    if not first_per_day:
        return TzScope(override.filename, "INVALID", None, None, None, None, ("no events",))

    days = sorted(first_per_day)
    raw_median = statistics.median(_hour(dt) for dt in first_per_day.values())
    normalised = raw_median + override.offset_hours
    reasons: list[str] = []
    if days[0] < v.first_event_date.isoformat() or days[-1] > v.last_event_date.isoformat():
        reasons.append(f"event dates {days[0]}..{days[-1]} fall outside the validated range {v.first_event_date}..{v.last_event_date}")
    lo, hi = v.raw_median_first_event_hour_band
    if not lo <= raw_median <= hi:
        reasons.append(f"raw median first-event hour {raw_median:.2f} is outside the band [{lo}, {hi}]: the shift this override corrects is not visible in the data")
    if not t07_low <= normalised < t07_high:
        reasons.append(f"after +{override.offset_hours}h the median first-event hour is {normalised:.2f}, outside the T07 band [{t07_low}, {t07_high})")
    return TzScope(override.filename, "INVALID" if reasons else "VALID", days[0], days[-1], round(raw_median, 3), round(normalised, 3), tuple(reasons))


def check_all(cfg: Config, member_bytes: dict[str, bytes]) -> list[TzScope]:
    t07 = cfg.thresholds.rules["T07"]
    return [check_override(o, member_bytes.get(name), t07.low, t07.high) for name, o in sorted(cfg.timezone.overrides.items())]
