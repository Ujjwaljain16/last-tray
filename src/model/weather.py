"""fact_weather and the session weather join (context only; no business conclusion is drawn from weather here).

FMI states timestamps in UTC. `r_1h` at time t is the precipitation over the HOUR ENDING at t (approved reading, Phase 2), so a session
is matched to the observation stamped at the end of the hour that contains its first weighing: the first weighing in UTC ceiled to the
next full hour (an event exactly on the hour keeps its own hour). Missing values stay NULL and are never backfilled or interpolated.
A session without weather stays a valid session.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from src.config import Config
from src.model.inputs import ModelInputs
from src.model.sessions import UTC_FMT, parse_utc

PARAMETER_COLUMNS = {"t2m": "t2m_c", "ws_10min": "ws_10min_ms", "r_1h": "r_1h_mm", "ri_10min": "ri_10min_mmh"}


class WeatherModelError(Exception):
    """The staged weather does not have the expected grain: weather outputs are blocked (the core model is unaffected)."""


def ceil_hour(t: datetime) -> datetime:
    floor = t.replace(minute=0, second=0, microsecond=0)
    return floor if t == floor else floor + timedelta(hours=1)


def build_weather(inp: ModelInputs, cfg: Config) -> list[dict[str, Any]]:
    weather = inp.staged.weather
    if weather is None:
        raise WeatherModelError(inp.staged.weather_error or "weather staging is unavailable")
    w = cfg.sources.weather
    params = list(w.request["parameters"])
    unknown = sorted({o.parameter for o in weather} - set(params))
    if unknown:
        raise WeatherModelError(f"unrequested weather parameters: {unknown}")
    by_hour: dict[datetime, dict[str, Any]] = defaultdict(dict)
    for o in weather:
        if o.obs_time_utc is None:
            raise WeatherModelError(f"{o.observation_id}: observation time is not a UTC timestamp")
        if o.parameter in by_hour[o.obs_time_utc]:
            raise WeatherModelError(f"duplicate station-hour-parameter row: {o.obs_time_utc.strftime(UTC_FMT)} {o.parameter}")
        by_hour[o.obs_time_utc][o.parameter] = o
    rows = []
    for hour in sorted(by_hour):
        obs = by_hour[hour]
        row: dict[str, Any] = {"fmisid": int(next(iter(obs.values())).fmisid), "obs_time_utc": hour.strftime(UTC_FMT)}
        statuses = []
        for p in params:
            o = obs.get(p)
            status = "MISSING" if o is None else o.value_status
            statuses.append(status)
            row[PARAMETER_COLUMNS[p]] = o.value_raw.strip() if o is not None and status == "OK" else None
            row[f"{p}_status"] = status
        row.update({
            "is_null_any": any(s != "OK" for s in statuses), "r_1h_convention": w.r_1h_convention,
            "timezone_handling": next(iter(obs.values())).timezone_handling, "source_snapshot_id": next(iter(obs.values())).source_snapshot_id,
            "source_files": ";".join(sorted({o.source_file for o in obs.values()})),
            "source_row_lineage": ";".join(sorted(o.observation_id for o in obs.values())),
        })
        rows.append(row)
    return rows


def join_sessions(sessions: list[dict[str, Any]], weather: list[dict[str, Any]] | None, blocked_reason: str | None = None) -> None:
    """Fill the weather join fields of each session in place."""
    by_hour = {parse_utc(w["obs_time_utc"]): w for w in weather or []}
    for s in sessions:
        if s["is_quarantined"]:
            s["weather_join_status"] = "NOT_ATTEMPTED_QUARANTINED"
            continue
        if not s["first_weighing_utc"]:
            s["weather_join_status"] = "NO_TIMESTAMP"
            continue
        hour = ceil_hour(parse_utc(s["first_weighing_utc"]))
        s["weather_hour_utc"] = hour.strftime(UTC_FMT)
        if weather is None:
            s["weather_join_status"] = "WEATHER_BLOCKED"
            continue
        w = by_hour.get(hour)
        if w is None:
            s["weather_join_status"] = "UNMATCHED_NO_OBSERVATION"
            continue
        s.update({"weather_join_status": "MATCHED", "weather_matched": True, "weather_fmisid": w["fmisid"],
                  "weather_r_1h_null": w["r_1h_status"] != "OK", "weather_ri_10min_null": w["ri_10min_status"] != "OK"})
