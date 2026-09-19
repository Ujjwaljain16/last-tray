"""Reconciliation: the counts that must agree, and the counts that describe the data, all as one flat table.

Status: PASS (an expectation held), WARN (a documented, flagged shortfall that does not block, e.g. partial weather coverage), FAIL (an
expectation broke: the affected lane blocks), INFO (a fact reported, no expectation).
Expectations come from the pins in config/sources.yml or from an identity that must hold by construction. The golden values are
compared against this table by the tests, never read by this code.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from src.config import Config
from src.validate.load import Ev, StagedInputs, Wx
from src.validate.rules_weather import expected_hours
from src.validate.sessions import SessionProfile

CHECK_COLUMNS = ("check_id", "area", "description", "expected", "observed", "status", "basis")
COMPLETENESS_COLUMNS = ("field", "rows", "not_applicable_rows", "empty_rows", "malformed_rows", "note")

DISPOSITION_MODELLABLE = "MODELLABLE"
DISPOSITION_REPEAT = "DUPLICATE_EXCLUDED"
DISPOSITION_QUARANTINED = "QUARANTINED"


@dataclass(frozen=True)
class Check:
    check_id: str
    area: str
    description: str
    expected: str
    observed: str
    status: str
    basis: str

    def row(self) -> dict[str, str]:
        return dict(zip(CHECK_COLUMNS, (self.check_id, self.area, self.description, self.expected, self.observed, self.status, self.basis)))


def eq(check_id: str, area: str, description: str, expected: Any, observed: Any, basis: str) -> Check:
    return Check(check_id, area, description, str(expected), str(observed), "PASS" if expected == observed else "FAIL", basis)


def coverage(check_id: str, description: str, expected: int, observed: int) -> Check:
    status = "PASS" if observed == expected else "FAIL" if observed == 0 else "WARN"
    return Check(check_id, "weather", description, str(expected), str(observed), status, "config/sources.yml window")


def info(check_id: str, area: str, description: str, observed: Any, basis: str = "reported") -> Check:
    return Check(check_id, area, description, "", str(observed), "INFO", basis)


def _counts(values) -> str:
    return ";".join(f"{k}={v}" for k, v in sorted(Counter(values).items()))


def disposition(events: list[Ev], repeats: dict[str, str], quarantined: set[str]) -> dict[str, str]:
    """Every staged event gets exactly one disposition. Quarantine wins over repeat. Nothing is dropped."""
    return {e.event_id: (DISPOSITION_QUARANTINED if e.session_key in quarantined else DISPOSITION_REPEAT if e.event_id in repeats else DISPOSITION_MODELLABLE)
            for e in events}


def event_checks(inp: StagedInputs, cfg: Config, disp: dict[str, str]) -> list[Check]:
    f, ev = cfg.sources.flavoria, inp.events
    checks = [eq("E01", "events", "staged events equal the pinned total", f.expected_total_rows, len(ev), "pin: config/sources.yml")]
    by_pop = Counter(e.population for e in ev)
    for pop in sorted({cfg.populations.population_for_filename(m.file).value for m in f.members}):
        pinned = sum(m.rows for m in f.members if cfg.populations.population_for_filename(m.file).value == pop)
        checks.append(eq(f"E02:{pop}", "events", f"events in {pop} equal the sum of its pinned members", pinned, by_pop[pop], "pin: config/sources.yml"))
    by_file = Counter(e.source_file for e in ev)
    for m in sorted(f.members, key=lambda x: x.file):
        checks.append(eq(f"E03:{m.file}", "events", "staged rows equal the pinned member row count", m.rows, by_file[m.file], "pin: config/sources.yml"))
    recon = {r["source_file"]: int(r["rows_staged"]) for r in inp.file_reconciliation}
    checks.append(eq("E04", "events", "staging_file_reconciliation agrees with the staged event table for every file", dict(sorted(recon.items())), dict(sorted(by_file.items())), "staging output"))
    counts = Counter(disp.values())
    partition = counts[DISPOSITION_MODELLABLE] + counts[DISPOSITION_REPEAT] + counts[DISPOSITION_QUARANTINED]
    checks.append(eq("E05", "events", "events_in = modelled + duplicates_excluded + quarantined (rule C04)", len(ev), partition, "identity"))
    checks.append(info("E06", "events", "event dispositions", _counts(disp.values())))
    return checks


def session_checks(inp: StagedInputs, cfg: Config, profiles: dict[str, SessionProfile], both: list[str], quarantined: set[str]) -> list[Check]:
    ids = {p.session_id for p in profiles.values()}
    n_events = sum(len(p.events) for p in profiles.values())
    ident_by_key = sum(1 for p in profiles.values() if len(p.identification_values) > 1)
    pooled_canonical = _pooled_identification_multiplicity(inp.events, raw=False)
    pooled_raw = _pooled_identification_multiplicity(inp.events, raw=True)
    crossover_keys = sorted(k for k, p in profiles.items() if p.session_id in set(both))
    return [
        eq("S01", "sessions", "distinct session_id equals the pinned count", cfg.sources.flavoria.expected_session_ids, len(ids), "pin: config/sources.yml"),
        eq("S02", "sessions", "session keys = session ids + ids present in both populations (why 3,345 differs from 3,343)", len(ids) + len(both), len(profiles), "identity"),
        info("S03", "sessions", "session_ids present in both populations (crossover)", ",".join(both)),
        eq("S04", "sessions", "every crossover session key is quarantined (rule I01)", crossover_keys, sorted(quarantined & set(crossover_keys)), "approved decision"),
        eq("S05", "sessions", "every staged event belongs to exactly one session key", len(inp.events), n_events, "identity"),
        eq("S06", "sessions", "session keys with more than one identification value (approved profiling correction: 0)", 0, ident_by_key, "approved profiling finding"),
        info("S07", "sessions", "the same count if populations were pooled by session_id alone (a pooling artefact; keys are never pooled): canonical instants | raw wall-clock",
              f"{pooled_canonical} | {pooled_raw}"),
    ]


def _pooled_identification_multiplicity(events: list[Ev], *, raw: bool) -> int:
    values: dict[str, set[datetime]] = defaultdict(set)
    for e in events:
        t = (e.identification_time_local - timedelta(hours=e.timezone_offset_hours)) if raw and e.identification_time_local else (e.identification_time_local if raw else e.identification_time_utc)
        if t is not None:
            values[e.session_id].add(t)
    return sum(1 for v in values.values() if len(v) > 1)


def structure_checks(events: list[Ev]) -> list[Check]:
    n = len(events)
    checks = []
    for cid, label, values in (("F01", "row_parse_status", [e.row_parse_status for e in events]), ("F02", "weight_parse_status", [e.weight_parse_status for e in events]),
                               ("F03", "event_time_status", [e.event_time_status for e in events]), ("F04", "identification_time_status", [e.identification_time_status for e in events])):
        checks.append(Check(cid, "structure", f"{label} counts reconcile to all staged events", str(n), f"{sum(Counter(values).values())} ({_counts(values)})",
                            "PASS" if len(values) == n else "FAIL", "identity"))
    return checks


def name_checks(profiles: dict[str, SessionProfile], events: list[Ev]) -> list[Check]:
    differing = sorted(k for k, p in profiles.items() if len({e.component_name_raw for e in p.counted}) != len({e.component_id_normalized for e in p.counted}))
    raw_names, norm_names = {e.component_name_raw for e in events}, {e.component_id_normalized for e in events}
    return [
        eq("N01", "components", "within every session, distinct raw component names equal distinct normalised names (profiling conclusion; observed = sessions that differ)", [], differing, "approved profiling finding"),
        info("N02", "components", "distinct component names across the data: raw | normalised (trim, whitespace collapse, casefold; no alias table)", f"{len(raw_names)} | {len(norm_names)}"),
    ]


def timezone_checks(events: list[Ev], cfg: Config, t10_issues: int, dst_checked: int, dst_failures: int) -> list[Check]:
    shifted = [e for e in events if e.timezone_handling != "SOURCE_LOCAL_ASSUMED"]
    pinned = sum(m.rows for m in cfg.sources.flavoria.members if m.file in cfg.timezone.overrides)
    return [
        eq("Z01", "timezone", "rows carrying a timezone override equal the rows of the configured override file(s), and no others", pinned,
            sum(1 for e in shifted if e.source_file in cfg.timezone.overrides), "config/timezone_overrides.yml"),
        eq("Z02", "timezone", "no row outside the configured override file carries an override", 0, sum(1 for e in shifted if e.source_file not in cfg.timezone.overrides), "approved decision"),
        eq("Z03", "timezone", "rule T10 findings", 0, t10_issues, "approved decision"),
        info("Z04", "timezone", "rows by timezone_handling (provenance labels, not conclusions)", _counts(e.timezone_handling for e in events)),
        eq("Z05", "timezone", f"local -> UTC -> local round-trip failures across {dst_checked} timestamps (DST-aware)", 0, dst_failures, "identity"),
        info("Z06", "timezone", "rows whose event time is ambiguous or nonexistent locally (NULL, never guessed)", sum(1 for e in events if e.event_time_status in ("AMBIGUOUS", "NONEXISTENT"))),
    ]


def duplicate_checks(inp: StagedInputs, repeats: dict[str, str], profiles: dict[str, SessionProfile], quarantined: set[str]) -> list[Check]:
    repeated_scale = 0
    for k, p in profiles.items():
        per = Counter(e.scale_id for e in p.counted)
        repeated_scale += k not in quarantined and any(v > 1 for v in per.values())
    natural: dict[tuple, list[Ev]] = defaultdict(list)
    for e in inp.events:
        natural[(e.session_id, e.event_time_raw, e.scale_id, e.weight_raw, e.component_name_raw)].append(e)
    dup_keys = [v for v in natural.values() if len(v) > 1]
    within = sum(1 for v in dup_keys if len({e.population for e in v}) == 1)
    return [
        eq("D01", "duplicates", "exact repeat rows within a file equal the count staging recorded", inp.summary["events"]["exact_duplicate_raw_rows_within_file"], len(repeats), "staging summary"),
        info("D02", "duplicates", "sessions with the same scale weighed repeatedly (additive scoops, all counted; retired rule B06 is not revived)", repeated_scale),
        info("D03", "duplicates", "natural-key (session, time, scale, weight, name) duplicate groups: total | within one population | across populations",
              f"{len(dup_keys)} | {within} | {len(dup_keys) - within}"),
    ]


def weather_checks(weather: list[Wx] | None, error: str | None, cfg: Config, x07: int) -> list[Check]:
    if weather is None:
        return [Check("K00", "weather", "weather staging is usable", "usable", f"BLOCKED: {error}", "FAIL", "staging output")]
    w = cfg.sources.weather
    pinned = sum(s.elements or 0 for s in w.raw_files)
    hours = {o.obs_time_utc for o in weather if o.obs_time_utc}
    return [
        eq("K01", "weather", "weather observations equal the pinned element count", pinned, len(weather), "pin: config/sources.yml"),
        coverage("K02", "distinct hours equal the expected hourly coverage (partial coverage is flagged by X01; only an empty table blocks)", len(expected_hours(cfg)), len(hours)),
        eq("K03", "weather", "station-hour-parameter grain findings (X07)", 0, x07, "identity"),
        info("K04", "weather", "observations by value_status (NaN is NULL, never zero)", _counts(o.value_status for o in weather)),
        info("K05", "weather", "station and parameters", f"FMISID {w.fmisid}; " + ",".join(sorted({o.parameter for o in weather}))),
    ]


def field_completeness(events: list[Ev]) -> list[dict[str, Any]]:
    """Empty (true missingness) is kept apart from not applicable (the source file does not have the column) and from malformed."""
    n = len(events)
    files_with_type = {e.source_file for e in events if e.weighing_type}
    lacking = sum(1 for e in events if e.source_file not in files_with_type)
    rows = [
        {"field": "session_id", "rows": n, "not_applicable_rows": 0, "empty_rows": sum(1 for e in events if not e.session_id.strip()), "malformed_rows": 0, "note": "required"},
        {"field": "tray_id", "rows": n, "not_applicable_rows": 0, "empty_rows": sum(1 for e in events if not e.tray_id.strip()), "malformed_rows": 0, "note": "required"},
        {"field": "scale_id", "rows": n, "not_applicable_rows": 0, "empty_rows": sum(1 for e in events if not e.scale_id.strip()), "malformed_rows": 0, "note": "required"},
        {"field": "component_name", "rows": n, "not_applicable_rows": 0, "empty_rows": sum(1 for e in events if not e.component_name_raw.strip()), "malformed_rows": 0, "note": "required"},
        {"field": "weight_of_a_component", "rows": n, "not_applicable_rows": 0, "empty_rows": sum(1 for e in events if e.weight_parse_status == "EMPTY"),
         "malformed_rows": sum(1 for e in events if e.weight_parse_status == "NOT_INTEGER"), "note": "required; malformed = not an integer"},
        {"field": "weighing_event_time", "rows": n, "not_applicable_rows": 0, "empty_rows": sum(1 for e in events if not e.event_time_raw.strip()),
         "malformed_rows": sum(1 for e in events if e.event_time_raw.strip() and e.event_time_status != "OK"), "note": "required; malformed = unparseable, ambiguous or nonexistent local time"},
        {"field": "user_identification_time", "rows": n, "not_applicable_rows": 0, "empty_rows": sum(1 for e in events if not e.identification_time_raw.strip()),
         "malformed_rows": sum(1 for e in events if e.identification_time_raw.strip() and e.identification_time_status != "OK"), "note": "required; malformed = unparseable, ambiguous or nonexistent local time"},
        {"field": "weighting_type", "rows": n, "not_applicable_rows": lacking, "empty_rows": sum(1 for e in events if e.source_file in files_with_type and not e.weighing_type),
         "malformed_rows": 0, "note": "optional column; not applicable where the source file has no such column (schema drift), which is not missing data"},
    ]
    return rows
