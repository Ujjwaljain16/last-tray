"""Weather structure checks (X01, X03, X07, X08). Context only: nothing here joins weather to sessions (that is the model layer).

Grain: one row = one station (FMISID) x one UTC observation time x one parameter. FMI states timestamps in UTC. The precipitation
convention (r_1h = hour ending at the timestamp) is untouched. NaN stays NULL and is never zero. An ERROR here BLOCKS weather
outputs only; the core lane is unaffected.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from src.config import Config
from src.validate.load import Wx
from src.validate.model import BASIS_ABSENT, BASIS_WEATHER, Issue


def expected_hours(cfg: Config) -> list[datetime]:
    w = cfg.sources.weather
    parse = lambda s: datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    start, end = parse(w.window_start), parse(w.window_end)
    return [start + timedelta(hours=i) for i in range(int((end - start).total_seconds() // 3600) + 1)]


def _ranges(hours: list[datetime]) -> list[tuple[datetime, datetime, int]]:
    out: list[tuple[datetime, datetime, int]] = []
    for h in sorted(hours):
        if out and h - out[-1][1] == timedelta(hours=1):
            out[-1] = (out[-1][0], h, out[-1][2] + 1)
        else:
            out.append((h, h, 1))
    return out


def _iso(t: datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def _wx_issue(rule: str, o: Wx, description: str, observed: str, expected: str) -> Issue:
    return Issue(rule, "weather_observation", o.observation_id, BASIS_WEATHER, description, observed, expected,
                 source_snapshot_id=o.source_snapshot_id, source_file=o.source_file, source_row_lineage=o.observation_id)


def check_weather(weather: list[Wx], cfg: Config) -> list[Issue]:
    w = cfg.sources.weather
    params = list(w.request["parameters"])
    out: list[Issue] = []

    for o in weather:                                       # X07 structure of each row
        if o.fmisid != str(w.fmisid):
            out.append(_wx_issue("X07", o, "observation is not from the configured station", f"FMISID {o.fmisid}", f"FMISID {w.fmisid}"))
        if o.obs_time_utc is None:
            out.append(_wx_issue("X07", o, "observation time is not a UTC timestamp", o.obs_time_raw, "YYYY-MM-DDTHH:MM:SSZ"))
        elif o.obs_time_utc.minute or o.obs_time_utc.second:
            out.append(_wx_issue("X07", o, "observation time is not on the hour", o.obs_time_raw, "an hourly timestamp"))
        if o.parameter not in params:
            out.append(_wx_issue("X07", o, "unrequested parameter", o.parameter, ",".join(params)))
        if o.value_status == "UNPARSEABLE":
            out.append(_wx_issue("X07", o, "value is neither a number nor NaN", o.value_raw, "a number, or NaN stored as NULL"))
    grain = Counter((o.obs_time_utc, o.parameter) for o in weather if o.obs_time_utc)
    for o in weather:
        if o.obs_time_utc and grain[(o.obs_time_utc, o.parameter)] > 1:
            out.append(_wx_issue("X07", o, "the (station, hour, parameter) grain is not unique", f"{grain[(o.obs_time_utc, o.parameter)]} rows", "one row"))

    have: dict[datetime, set[str]] = defaultdict(set)
    for o in weather:
        if o.obs_time_utc:
            have[o.obs_time_utc].add(o.parameter)
    expected = expected_hours(cfg)
    missing = [h for h in expected if h not in have]
    unexpected = [h for h in have if h not in set(expected)]
    for label, hours in (("missing", missing), ("unexpected", unexpected)):        # X01 coverage, as contiguous ranges
        for a, b, n in _ranges(hours):
            out.append(Issue("X01", "weather_hours", f"{label} {_iso(a)}..{_iso(b)}", BASIS_ABSENT, f"{n} {label} weather hour(s)", f"{_iso(a)}..{_iso(b)}",
                             f"{len(expected)} hourly observations from {w.window_start} to {w.window_end}"))
    for p in params:                                                                # X08 parameter completeness
        lacking = [h for h in expected if h in have and p not in have[h]]
        if lacking:
            out.append(Issue("X08", "weather_parameter", p, BASIS_ABSENT, f"{len(lacking)} hour(s) have no {p} observation", f"{_iso(min(lacking))}..{_iso(max(lacking))}", "every hour has every parameter"))
    for o in weather:                                                               # X03 NULL values (never zero)
        if o.value_status == "NAN_SOURCE_NULL":
            out.append(_wx_issue("X03", o, f"the source reports NaN for {o.parameter}; stored as NULL, never zero", o.value_raw, "a number"))
    return out
