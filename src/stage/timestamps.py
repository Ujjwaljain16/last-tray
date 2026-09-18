"""Timestamp handling for staging. Pure functions: no file access, no clock.

Every staged timestamp keeps THREE things: the raw text exactly as the source wrote it, a canonical UTC instant, and how the
zone was handled. The raw text is never overwritten.

Zone handling
    SOURCE_LOCAL_ASSUMED   the source states no zone; the wall time is read as Europe/Helsinki local time, using real
                           zoneinfo rules (the study period crosses the 2020-10-25 clock change). An assumption, labelled.
    NORMALISED_PLUS_3H_...  a FILE-SPECIFIC, evidence-backed +3 hour normalization for one export. Not source-confirmed.
                           It is applied only when the configuration AND the ingestion handoff both name that exact file.

Ambiguous local times (clocks go back) and nonexistent local times (clocks go forward) are never guessed: the canonical UTC
value is NULL and the status says why.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from src.config import Config
from src.vocab import LocalTimeStatus, TimezoneHandling

FORMATS = {"dash": "%Y-%m-%d %H:%M:%S", "dot": "%Y.%m.%d %H:%M:%S"}
REASON_DEFAULT = "source states no timezone; wall time read as Europe/Helsinki local time (assumption)"
REASON_OVERRIDE = "cross-export temporal alignment (file-specific, evidence-backed; not source-confirmed)"


class StagingError(Exception):
    """A staging precondition failed. The staging path for that source stops; nothing partial is published."""


@dataclass(frozen=True)
class TimezoneTreatment:
    handling: TimezoneHandling
    offset_hours: int
    zone: str
    reason: str
    scope: str            # file_specific | none


@dataclass(frozen=True)
class StagedTimestamp:
    raw: str
    source_format: str | None
    local: datetime | None            # wall time after any normalization (naive)
    utc: datetime | None              # canonical instant (aware, UTC); None when the local time is ambiguous or nonexistent
    status: LocalTimeStatus


def parse_source_timestamp(raw: str) -> tuple[datetime | None, str | None]:
    """Both source formats. Returns (naive datetime, format name) or (None, None). Fractions and stray text are unparseable."""
    text = raw.strip()
    for name, fmt in FORMATS.items():
        try:
            return datetime.strptime(text, fmt), name
        except ValueError:
            continue
    return None, None


def local_to_utc(naive: datetime, zone: str) -> tuple[datetime | None, LocalTimeStatus]:
    """Convert a wall time in `zone` to UTC, refusing to guess across a clock change."""
    zi = ZoneInfo(zone)
    first, second = naive.replace(tzinfo=zi, fold=0), naive.replace(tzinfo=zi, fold=1)
    if first.utcoffset() != second.utcoffset():
        round_trip = first.astimezone(timezone.utc).astimezone(zi).replace(tzinfo=None)
        return None, (LocalTimeStatus.AMBIGUOUS if round_trip == naive else LocalTimeStatus.NONEXISTENT)
    return first.astimezone(timezone.utc), LocalTimeStatus.OK


def stage_timestamp(raw: str, treatment: TimezoneTreatment) -> StagedTimestamp:
    naive, fmt = parse_source_timestamp(raw)
    if naive is None:
        return StagedTimestamp(raw, None, None, None, LocalTimeStatus.UNPARSEABLE)
    local = naive + timedelta(hours=treatment.offset_hours)
    utc, status = local_to_utc(local, treatment.zone)
    return StagedTimestamp(raw, fmt, local, utc, status)


def iso_local(dt: datetime | None) -> str | None:
    return dt.strftime("%Y-%m-%dT%H:%M:%S") if dt else None


def iso_utc(dt: datetime | None) -> str | None:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ") if dt else None


def treatment_for(cfg: Config, filename: str, handoff_tz: dict[str, Any]) -> TimezoneTreatment:
    """The timezone treatment for one file, with two independent gates so an override can never leak to another file.

    Gate 1: the configuration must name this exact filename. Gate 2: the ingestion handoff must say the same. If the two
    disagree in either direction, staging of the source stops.
    """
    zone = cfg.timezone.default_assume
    override = cfg.timezone.overrides.get(filename)
    if override is None:
        if handoff_tz.get("offset_hours") != 0 or handoff_tz.get("normalization") != TimezoneHandling.SOURCE_LOCAL_ASSUMED.value \
                or handoff_tz.get("scope") != "none":
            raise StagingError(f"the handoff applies a timezone override to {filename!r}, but the configuration has none for that file: refusing")
        return TimezoneTreatment(TimezoneHandling.SOURCE_LOCAL_ASSUMED, 0, zone, REASON_DEFAULT, "none")
    expected = (override.label.value, override.offset_hours, "file_specific", False)
    got = (handoff_tz.get("normalization"), handoff_tz.get("offset_hours"), handoff_tz.get("scope"), handoff_tz.get("source_confirmed"))
    if got != expected:
        raise StagingError(f"the handoff's timezone treatment for {filename!r} {got} disagrees with the configured override {expected}: refusing")
    return TimezoneTreatment(override.label, override.offset_hours, zone, REASON_OVERRIDE, "file_specific")
