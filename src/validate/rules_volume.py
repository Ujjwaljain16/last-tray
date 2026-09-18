"""Completeness and volume rules (C01, C02a, C02b, C03). FLAG ONLY: no day and no session is ever excluded because of them.

Volume here is the count of observed valid sessions per service day. It is an observation of the export, not a measure of
restaurant demand, and a day whose volume differs from its weekday's baseline regime is NOT a data error. C02b compares the
observed regime with the regime the four baseline weeks establish for that weekday; the baseline is re-derived from the data and
checked against config/thresholds.yml so the configured expectation cannot silently drift from the evidence.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, timedelta

from src.config import Config
from src.validate.model import BASIS_ABSENT, BASIS_DAY, BASIS_POPULATION, Issue
from src.validate.sessions import SessionProfile

WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


@dataclass(frozen=True)
class ServiceDay:
    population: str
    service_date: date
    weekday: str
    sessions: int
    observed_regime: str            # high | low, by the configured session-count boundary
    expected_regime: str | None     # from the weekday baseline; None on a weekend
    low_observed_volume: bool       # C02a
    volume_irregularity: bool       # C02b
    source_files: tuple[str, ...]


def service_days(profiles: dict[str, SessionProfile], quarantined: set[str], cfg: Config) -> list[ServiceDay]:
    """Observed valid sessions (not quarantined) per population and service date."""
    v = cfg.thresholds.volume
    per_day: dict[tuple[str, date], list[SessionProfile]] = defaultdict(list)
    for p in profiles.values():
        if p.session_key not in quarantined and p.first_local:
            per_day[(p.population, p.first_local.date())].append(p)
    days = []
    for (pop, d), ps in sorted(per_day.items()):
        weekday = WEEKDAYS[d.weekday()]
        n = len(ps)
        observed = "high" if n >= v.high_regime_min_sessions else "low"
        primary = pop == cfg.populations.primary.code.value          # the C02 regimes were established on the registered-export population only
        expected = v.expected_regime_by_weekday.get(weekday) if primary else None
        days.append(ServiceDay(pop, d, weekday, n, observed, expected, primary and n < v.high_regime_min_sessions,
                               expected is not None and observed != expected, tuple(sorted({f for p in ps for f in p.source_files}))))
    return days


def derive_baseline_regimes(days: list[ServiceDay], cfg: Config, population: str) -> dict[str, str]:
    """Weekday -> regime established by the baseline weeks; 'mixed' if a baseline weekday does not separate cleanly."""
    v = cfg.thresholds.volume
    seen: dict[str, set[str]] = defaultdict(set)
    for d in days:
        if d.population == population and v.baseline_start <= d.service_date <= v.baseline_end:
            seen[d.weekday].add(d.observed_regime)
    return {wd: (next(iter(r)) if len(r) == 1 else "mixed") for wd, r in sorted(seen.items())}


def check_volume(days: list[ServiceDay], cfg: Config) -> list[Issue]:
    primary = cfg.populations.primary.code.value
    threshold = cfg.thresholds.volume.high_regime_min_sessions
    out: list[Issue] = []
    for d in days:
        if d.population != primary:
            continue
        files = ";".join(d.source_files)
        ident = dict(entity_type="service_day", entity_id=d.service_date.isoformat(), population=d.population, source_file=files)
        if d.low_observed_volume:
            out.append(Issue("C02a", lineage_basis=BASIS_DAY, description=f"low observed volume: {d.sessions} sessions on a {d.weekday} (flag only; the day is kept)",
                             observed_value=f"{d.sessions} sessions", expected_condition=f">= {threshold} sessions", **ident))
        if d.volume_irregularity:
            out.append(Issue("C02b", lineage_basis=BASIS_DAY, description=(f"volume irregularity: {d.sessions} sessions on a {d.weekday}; observed regime {d.observed_regime}, "
                                                                          f"weekday baseline regime {d.expected_regime}. Cause unresolved; NOT a data error; the day is retained"),
                             observed_value=f"{d.observed_regime} ({d.sessions} sessions)", expected_condition=f"{d.expected_regime} regime on a {d.weekday}", **ident))
    return out


def weekdays_between(start: date, end: date) -> list[date]:
    return [start + timedelta(days=i) for i in range((end - start).days + 1) if (start + timedelta(days=i)).weekday() < 5]


def week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def check_coverage(days: list[ServiceDay], cfg: Config) -> list[Issue]:
    """C01 weekdays of the window with no observed session (per population); C03 whole weeks with none."""
    lo, hi = cfg.sources.flavoria.window_start, cfg.sources.flavoria.window_end
    expected = weekdays_between(lo, hi)
    out: list[Issue] = []
    for pop in sorted({d.population for d in days}):
        present = {d.service_date for d in days if d.population == pop}
        missing = [d for d in expected if d not in present]
        if missing:
            out.append(Issue("C01", "population", pop, BASIS_POPULATION, f"{len(missing)} of {len(expected)} weekdays in the study window have no observed session",
                             f"missing: {missing[0]}..{missing[-1]} ({len(missing)} days)", f"all {len(expected)} weekdays", population=pop))
        weeks = Counter(week_start(d) for d in present)
        for w in sorted({week_start(d) for d in expected} - set(weeks)):
            out.append(Issue("C03", "population_week", f"{pop}|{w}", BASIS_ABSENT, f"no data for {pop} in the week starting {w}",
                             "0 sessions", "data for every week of the study window", population=pop))
    return out
