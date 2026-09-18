"""Staging of FMI weather: verified bytes in, one staged row per (time, parameter) element out.

FMI states its timestamps in UTC ('Z'), so no zone assumption is involved. NaN stays NULL, never zero. Parsing the XML reuses
the pure parser from ingestion; nothing here reads a file.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from src.ingest.weather import WeatherParseError, parse_weather_xml
from src.stage.timestamps import StagingError, iso_utc
from src.vocab import TimezoneHandling, ValueStatus


@dataclass(frozen=True)
class StagedWeather:
    """Column order here is the column order of stg_weather_observation.csv."""

    observation_id: str
    source_snapshot_id: str
    raw_artifact_id: str
    source_file: str
    element_index: int
    fmisid: int
    obs_time_raw: str
    obs_time_canonical_utc: str | None
    timezone_handling: str
    parameter: str
    value_raw: str
    value: float | None
    value_status: str


WEATHER_COLUMNS = tuple(StagedWeather.__dataclass_fields__)


def _utc(raw: str) -> datetime | None:
    try:
        return datetime.strptime(raw.strip(), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def stage_weather_chunk(data: bytes, chunk: dict, snapshot_id: str, fmisid: int) -> list[StagedWeather]:
    try:
        parsed = parse_weather_xml(data)
    except WeatherParseError as exc:
        raise StagingError(f"{chunk['file']}: {exc}") from exc
    rows = []
    for i, (t, param, raw_value) in enumerate(parsed.triples, start=1):
        value, status = None, ValueStatus.OK
        if raw_value.strip().lower() == "nan":
            status = ValueStatus.NAN_SOURCE_NULL
        else:
            try:
                value = float(raw_value)
            except ValueError:
                status = ValueStatus.UNPARSEABLE
        rows.append(StagedWeather(
            observation_id=f"{chunk['file']}#{i}", source_snapshot_id=snapshot_id, raw_artifact_id=chunk["artifact_id"],
            source_file=chunk["file"], element_index=i, fmisid=fmisid, obs_time_raw=t, obs_time_canonical_utc=iso_utc(_utc(t)),
            timezone_handling=TimezoneHandling.SOURCE_UTC_STATED.value, parameter=param, value_raw=raw_value, value=value,
            value_status=status.value))
    return rows
