"""Session-level rules (I01, I04, I06, I07, B04, B05, B07, T04, T05, T06) over (session_id, population) keys.

A session is a DERIVED grouping of component weighing events. Its key always carries the population, so a session_id that
appears in both exports is two keys, never one merged session. The weight and span rules are DIAGNOSTIC: a flagged session is
kept, counted and visible; only ERROR-level rules (here I01 and I04) quarantine.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from src.config import Rule
from src.validate.load import Ev
from src.validate.model import BASIS_ROWS, BASIS_SESSION, Issue
from src.validate.sessions import SessionProfile, raw_wall_time


def _issue(rule_id: str, p: SessionProfile, description: str, observed: str, expected: str) -> Issue:
    first = p.events[0]
    return Issue(rule_id, "session", p.session_key, BASIS_SESSION, description, observed, expected, session_key=p.session_key,
                 population=p.population, source_snapshot_id=first.source_snapshot_id, source_file=";".join(p.source_files),
                 source_row_lineage=p.lineage)


def session_ids_in_both_populations(profiles: dict[str, SessionProfile]) -> list[str]:
    pops: dict[str, set[str]] = defaultdict(set)
    for p in profiles.values():
        pops[p.session_id].add(p.population)
    return sorted(sid for sid, s in pops.items() if len(s) > 1)


def check_crossover(profiles: dict[str, SessionProfile]) -> list[Issue]:
    """I01 (ERROR, QUARANTINE): the same session_id in both populations. Both versions are quarantined; neither is preferred."""
    both = set(session_ids_in_both_populations(profiles))
    return [_issue("I01", p, f"session_id {p.session_id} exists in both populations; both versions are quarantined and neither is preferred",
                   f"{p.session_id} in {sorted({q.population for q in profiles.values() if q.session_id == p.session_id})}", "a session_id belongs to one population")
            for p in profiles.values() if p.session_id in both]


def check_identity(profiles: dict[str, SessionProfile]) -> list[Issue]:
    """I04 one tray per session key (ERROR); T06 one identification instant per session key (WARN)."""
    out: list[Issue] = []
    for p in profiles.values():
        trays = [t for t in p.tray_ids if t]
        if len(trays) > 1:
            out.append(_issue("I04", p, "the session key has more than one tray_id", ";".join(trays), "exactly one tray_id"))
        if len(p.identification_values) > 1:
            out.append(_issue("T06", p, "the session key has more than one identification time",
                              ";".join(v.strftime("%Y-%m-%dT%H:%M:%SZ") for v in p.identification_values), "exactly one identification instant"))
    return out


def check_session_metrics(profiles: dict[str, SessionProfile], rules: dict[str, Rule], primary_population: str) -> list[Issue]:
    """B04 single-event session (primary population only), B07 weight range, T05 span, T04 identification before the last weighing."""
    b07, t05 = rules["B07"], rules["T05"]
    out: list[Issue] = []
    for p in profiles.values():
        if p.population == primary_population and len(p.counted) == 1:
            out.append(_issue("B04", p, "session with a single weighing event (a diagnostic population, not automatically invalid)",
                              f"{len(p.counted)} event; {p.rule_weight_sum_g} g", "more than one weighing event"))
        w = p.rule_weight_sum_g
        if w is not None and (w < b07.low or w > b07.high):
            out.append(_issue("B07", p, f"session weight {w} g is outside the diagnostic range (review needed, not automatically invalid)",
                              f"{w} g", f"{b07.low:g} <= weight <= {b07.high:g} g"))
        if p.span_s is not None and p.span_s > t05.value:
            out.append(_issue("T05", p, f"session span {p.span_s:.0f} s is above the diagnostic threshold (may merge two tray passes)",
                              f"{p.span_s:.0f} s", f"<= {t05.value:g} s"))
        gap = p.identified_minus_last_s
        if gap is not None and gap < 0:
            out.append(_issue("T04", p, "identification is earlier than the last weighing", f"{gap:.0f} s", "identification at or after the last weighing"))
    return out


def check_repeated_scales(profiles: dict[str, SessionProfile], quarantined: set[str]) -> list[Issue]:
    """B05 (INFO): the same scale weighed more than once in a session. Repeats are additive scoops and are all counted. Retired B06 is NOT revived."""
    out: list[Issue] = []
    for p in profiles.values():
        if p.session_key in quarantined:
            continue
        per_scale: dict[str, int] = defaultdict(int)
        for e in p.counted:
            per_scale[e.scale_id] += 1
        repeated = {s: n for s, n in sorted(per_scale.items()) if n > 1}
        if repeated:
            out.append(_issue("B05", p, "the same scale was weighed repeatedly; repeats are additive scoops and are summed",
                              ";".join(f"{s} x{n}" for s, n in repeated.items()), "usually once per scale"))
    return out


def _versions(profiles: dict[str, SessionProfile], session_id: str) -> list[SessionProfile]:
    return sorted((p for p in profiles.values() if p.session_id == session_id), key=lambda p: p.population)


def compare_versions(a: SessionProfile, b: SessionProfile) -> dict:
    """Pair the two versions' counted events by (scale, weight, time order) and describe how they differ."""
    def key(e: Ev):
        return (e.scale_id, e.weight_g if e.weight_g is not None else -1, e.event_time_utc or datetime.min)

    ea, eb = sorted(a.counted, key=key), sorted(b.counted, key=key)
    same_multiset = [(e.scale_id, e.weight_g) for e in ea] == [(e.scale_id, e.weight_g) for e in eb]
    out = {"events": (len(ea), len(eb)), "same_scale_weight_multiset": same_multiset, "staged_deltas_s": set(), "raw_wall_deltas_s": set(), "name_conflicts": 0}
    if same_multiset:
        for x, y in zip(ea, eb):
            if x.event_time_utc and y.event_time_utc:
                out["staged_deltas_s"].add(int((y.event_time_utc - x.event_time_utc).total_seconds()))
            rx, ry = raw_wall_time(x), raw_wall_time(y)
            if rx and ry:
                out["raw_wall_deltas_s"].add(int((ry - rx).total_seconds()))
            out["name_conflicts"] += x.component_id_normalized != y.component_id_normalized
    return out


def check_cross_export(profiles: dict[str, SessionProfile]) -> list[Issue]:
    """I06: how the two exports' versions of a crossover session differ. Identical versions are reported as INFO, disagreement as WARN."""
    out: list[Issue] = []
    for sid in session_ids_in_both_populations(profiles):
        vs = _versions(profiles, sid)
        if len(vs) != 2:
            continue
        c = compare_versions(vs[0], vs[1])
        identical = c["same_scale_weight_multiset"] and c["staged_deltas_s"] <= {0} and c["name_conflicts"] == 0
        observed = (f"events {c['events'][0]} vs {c['events'][1]}; same scale/weight multiset: {c['same_scale_weight_multiset']}; "
                    f"staged time deltas (s): {sorted(c['staged_deltas_s'])}; raw wall-clock deltas (s): {sorted(c['raw_wall_deltas_s'])}; "
                    f"component-name conflicts: {c['name_conflicts']} of {min(c['events'])}")
        out.append(Issue("I06", "session_id", sid, BASIS_ROWS,
                         "the two exports' versions are identical event for event" if identical else "the two exports' versions of this session disagree",
                         observed, "identical versions", population="both", source_snapshot_id=vs[0].events[0].source_snapshot_id,
                         source_file=";".join(sorted({f for p in vs for f in p.source_files})), source_row_lineage=";".join(p.lineage for p in vs),
                         severity="INFO" if identical else ""))
    return out


def check_component_identity_across_exports(events: list[Ev]) -> list[Issue]:
    """I07 (INFO): for a scale and day seen in both populations, the normalised component-name sets share nothing. Uses the staged
    normalised name only (no alias table), so the finding is about the strings, not about which dishes they are."""
    cells: dict[tuple[str, str], dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    rows: dict[tuple[str, str], list[str]] = defaultdict(list)
    for e in events:
        if e.event_time_local and e.component_id_normalized:
            cell = (e.scale_id, e.event_time_local.date().isoformat())
            cells[cell][e.population].add(e.component_id_normalized)
            rows[cell].append(e.event_id)
    out: list[Issue] = []
    for cell, by_pop in sorted(cells.items()):
        if len(by_pop) < 2:
            continue
        sets = [by_pop[p] for p in sorted(by_pop)]
        if not set.intersection(*sets):
            out.append(Issue("I07", "scale_day", f"{cell[0]}|{cell[1]}", BASIS_ROWS,
                             "the two exports share no normalised component name for this scale and day",
                             " || ".join("; ".join(sorted(s)) for s in sets), "overlapping component names", population="both",
                             source_row_lineage=";".join(sorted(rows[cell]))))
    return out


def count_cross_export_cells(events: list[Ev]) -> tuple[int, int, int]:
    """(scale-days seen in both populations, identical name sets, disjoint name sets): descriptive evidence for I07."""
    cells: dict[tuple[str, str], dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for e in events:
        if e.event_time_local and e.component_id_normalized:
            cells[(e.scale_id, e.event_time_local.date().isoformat())][e.population].add(e.component_id_normalized)
    both = [list(v.values()) for v in cells.values() if len(v) > 1]
    return len(both), sum(1 for s in both if all(x == s[0] for x in s)), sum(1 for s in both if not set.intersection(*s))
