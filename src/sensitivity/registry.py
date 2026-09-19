"""The scenario registry: WHAT is tested and WHY, as data. No calculation lives here.

Each scenario changes exactly one documented assumption of the approved baseline. The engine (engine.py) interprets the `operation`
declarations; it contains no scenario-specific logic. Scenario ids and reference values are the Phase 2 approved sensitivity space
(docs/sensitivity_analysis.md, tests/golden/phase2_sensitivity_analysis.csv), reproduced from the canonical model, never tuned.

A scenario is a SENSITIVITY TEST, not an alternative truth. `defensible` says whether a reasonable analyst could hold that assumption;
`diagnostic_only` says the scenario can never become a production rule; `forbidden` marks a comparison that is invalid by design.
"""
from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Any

POP_REG, POP_NON = "registered_export", "non_registered_export"
ALL_KPIS = ("M1", "M2", "M3", "M4")
WITH_READINESS = ("M1", "M2", "M3", "M4", "M5", "S2")

# Approved Phase 2 reference values: (M1 g, M2 g, M3, M4, M5 numerator, S2 baseline %). None = not defined for that scenario.
# Tolerances: grams 0.05 (the reference is published to one decimal), counts exact.
PHASE2_TOLERANCE_G = 0.05

# Robustness classification (transparent, applied identically to every metric and scenario). |delta| is measured against the frozen baseline.
#   STABLE       |delta| < stable_below      (below the approved Phase 2 materiality convention: 10 g on M1, 25 g on M2, no change in M4)
#   SENSITIVE    |delta| < sensitive_below   (material, but within twice the convention; the interpretation may remain)
#   CONDITIONAL  otherwise                   (the result depends strongly on the assumption that was changed)
#   BLOCKED      no value can be produced because required evidence is unavailable
CLASSIFICATION: dict[str, dict[str, Any]] = {
    "M1": {"kind": "absolute", "unit": "g", "stable_below": 10.0, "sensitive_below": 20.0, "basis": "Phase 2 materiality convention |dM1| >= 10 g; sensitive band = 2x"},
    "M2": {"kind": "absolute", "unit": "g", "stable_below": 25.0, "sensitive_below": 75.0, "basis": "Phase 2 materiality convention |dM2| >= 25 g; sensitive band = 3x"},
    "M3": {"kind": "relative", "unit": "fraction of baseline", "stable_below": 0.05, "sensitive_below": 0.20, "basis": "5% and 20% of the 1,697 baseline sessions"},
    "M4": {"kind": "absolute", "unit": "components", "stable_below": 0.5, "sensitive_below": 1.5, "basis": "Phase 2 convention: any change in M4 is material; one component is sensitive"},
    "M5": {"kind": "absolute", "unit": "percentage points", "stable_below": 0.5, "sensitive_below": 5.0, "basis": "readiness moved by half a point is stable; five points is the sensitive limit"},
    "S2": {"kind": "absolute", "unit": "percentage points", "stable_below": 0.5, "sensitive_below": 5.0, "basis": "as M5"},
}
CLASS_ORDER = ("STABLE", "SENSITIVE", "CONDITIONAL", "BLOCKED")


@dataclass(frozen=True)
class ScenarioSpec:
    scenario_id: str
    group: str
    name: str
    assumption_changed: str
    baseline_assumption: str
    alternative_assumption: str
    rationale: str
    affected_tables: tuple[str, ...]
    affected_population: str
    metrics_recalculated: tuple[str, ...]
    operation: dict[str, Any]
    interpretation: str
    decision_impact: str
    defensible: bool
    diagnostic_only: bool
    forbidden: bool = False
    phase2: tuple[float | None, ...] | None = None      # (M1, M2, M3, M4, M5 numerator, S2 %) approved reference, or None for new scenarios

    def as_dict(self) -> dict[str, Any]:
        return {f.name: (list(getattr(self, f.name)) if isinstance(getattr(self, f.name), tuple) else getattr(self, f.name)) for f in fields(self)}


SESSION_TABLES = ("fact_dining_session",)
EVENT_TABLES = ("fact_dining_session", "fact_weighing_event")
BASE_ASSUMPTION = "the approved baseline (registered-export core-ready sessions, crossover quarantined, exact repeats left out of sums, file-specific +3h)"


def S(scenario_id, group, name, assumption, baseline, alternative, rationale, tables, population, metrics, operation, interpretation, impact, defensible,
      diagnostic_only, phase2, forbidden=False) -> ScenarioSpec:
    return ScenarioSpec(scenario_id, group, name, assumption, baseline, alternative, rationale, tables, population, metrics, operation, interpretation, impact,
                        defensible, diagnostic_only, forbidden, phase2)


SCENARIOS: tuple[ScenarioSpec, ...] = (
    S("S00", "baseline", "Approved baseline", "none", BASE_ASSUMPTION, BASE_ASSUMPTION, "The frozen approved interpretation; every other scenario is compared with it.",
      SESSION_TABLES, POP_REG, WITH_READINESS, {"kind": "baseline"}, "The approved metric package (M1 499 g, M2 1,039.6 g, M3 1,697, M4 5, M5 99.88%, S2 97.88%).",
      "none: this is the baseline", True, False, (499.0, 1039.6, 1697, 5.0, 1697, 97.881)),

    # ---- crossover treatment (what-if only; the quarantine is never weakened) -------------------------------------------------------------
    S("S01", "crossover", "Crossover sessions included (both)", "crossover session treatment", "session2266 and session3222 are quarantined in both populations",
      "both registered-export versions are counted as ordinary sessions", "What if the quarantine were lifted? Shows the effect is small on weights and that readiness would be 100% only because the check was removed.",
      EVENT_TABLES, POP_REG, WITH_READINESS, {"kind": "include", "keys": "quarantined_registered"},
      "M1, M2 and M4 barely move; M5 rises to 100% only because the quarantine is lifted, which is not a valid readiness figure.",
      "none: the quarantine stays; M5 must never be reported this way", False, True, (499.0, 1042.4, 1699, 5.0, 1699, None)),
    S("S02", "crossover", "Only session2266 included", "crossover session treatment", "quarantined", "session2266 (an exact cross-export duplicate) counted once in the registered-export population",
      "Isolates the exact duplicate: it would add a second copy of one tray pass.", EVENT_TABLES, POP_REG, WITH_READINESS,
      {"kind": "include", "keys": ["session2266|registered_export"]}, "Adds a duplicate tray pass; effect on weights is negligible.", "none", False, True,
      (499.0, 1039.2, 1698, 5.0, 1698, None)),
    S("S03", "crossover", "Only session3222 included", "crossover session treatment", "quarantined", "session3222 (a version conflict between the exports) counted in the registered-export population",
      "Isolates the version-conflict session.", EVENT_TABLES, POP_REG, WITH_READINESS, {"kind": "include", "keys": ["session3222|registered_export"]},
      "One conflicted session moves M2 by about 3 g.", "none", False, True, (499.5, 1042.6, 1698, 5.0, 1698, None)),

    # ---- the 2,097 g observation: unusual, not invalid -------------------------------------------------------------------------------------
    S("S04", "outlier", "2,097 g session removed", "treatment of the largest observation", "the session holding the 2,097 g event stays in the population",
      "that whole session is left out (analytic only)", "The 2,097 g event is an UNUSUAL observation, not an INVALID one. Tests whether it drives the result.", EVENT_TABLES, POP_REG,
      ALL_KPIS, {"kind": "exclude_session", "selector": "largest_event_session"}, "Removing the session shifts M2 by about -1.6 g: the observation is immaterial.",
      "none: the event stays in canonical data and in the baseline", True, True, (499.0, 1038.0, 1696, 5.0, None, None)),
    S("S05", "outlier", "2,097 g event removed (session kept)", "treatment of the largest observation", "the event counts in its session's weight", "only that event is dropped from its session's weight",
      "Separates the event from the session.", EVENT_TABLES, POP_REG, ALL_KPIS, {"kind": "drop_event", "selector": "largest_event"},
      "Same effect on M2 as removing the session.", "none", True, True, (499.0, 1038.0, 1697, 5.0, None, None)),
    S("S06", "outlier", "Exclude outside data percentiles P0.5-P99.5", "outlier bounds", "no exclusion (B07 [50, 2,200] g is a flag only)",
      "sessions outside the data's own 0.5th and 99.5th percentiles are left out", "Compares a data-driven bound with the approved fixed bound.", SESSION_TABLES, POP_REG, ALL_KPIS,
      {"kind": "exclude_weight_outside", "method": "percentile", "lo": 0.005, "hi": 0.995}, "Trimming the tails lowers M2 by about 2%.", "none: exclusion is diagnostic", True, True,
      (499.0, 1017.0, 1679, 5.0, None, None)),
    S("S07", "outlier", "Exclude outside the approved B07 range", "outlier bounds", "B07 flags sessions outside [50, 2,200] g but keeps them",
      "the B07-flagged sessions are left out", "What if the diagnostic B07 flag were an exclusion rule?", SESSION_TABLES, POP_REG, ALL_KPIS,
      {"kind": "exclude_weight_outside", "method": "threshold", "rule": "B07"}, "Lowers M2 by about 2%.", "none: B07 stays a flag", True, True, (499.0, 1020.5, 1682, 5.0, None, None)),
    S("S08", "outlier", "Exclude single-event sessions (B04)", "session completeness", "single-event sessions are kept", "sessions with one weighing event are left out",
      "The 17 single-event sessions are a diagnostic population; do they drive M1?", SESSION_TABLES, POP_REG, ALL_KPIS,
      {"kind": "exclude_where", "field": "modellable_event_count", "op": "<=", "value": 1}, "M1 +2 g, M2 +4.6 g.", "none: B04 stays a flag", True, True, (501.0, 1044.2, 1680, 5.0, None, None)),
    S("S09", "outlier", "Exclude long sessions (T05)", "session span", "sessions with a span over 600 s are kept", "those sessions are left out",
      "Long spans may merge two tray passes; do they drive the result?", SESSION_TABLES, POP_REG, ALL_KPIS,
      {"kind": "exclude_where", "field": "session_span_s", "op": ">", "value_ref": "T05"}, "Effect below 3 g.", "none: T05 stays a flag", True, True, (498.0, 1037.1, 1690, 5.0, None, None)),
    S("S10", "outlier", "Exclude every session with any WARN", "warning treatment", "WARN findings never remove a session",
      "sessions with a session-level or event-level WARN are left out", "What if every flagged session were excluded? Also shows why M5 and S2 differ.", SESSION_TABLES, POP_REG, ALL_KPIS,
      {"kind": "exclude_where_any_warn"}, "M2 falls by about 25 g (2.4%): flagged sessions are somewhat heavier.", "none: a WARN never excludes", True, True, (499.5, 1015.0, 1660, 5.0, None, None)),

    # ---- timezone of the ONE suspect export (file-specific; nothing else is shifted) ---------------------------------------------------------
    *[S(f"TZ{h}", "timezone", f"Suspect export shifted by +{h}h", "timezone of the suspect registered export", "the file-specific +3h normalization (strongest-supported, not source-confirmed)",
        f"the same file shifted by +{h}h from its raw wall-clock times (all other files unchanged; service-hours rule T03 applied)",
        "The source does not confirm the timezone metadata. The offset is tested across the plausible range, only on the named file.", EVENT_TABLES, POP_REG, WITH_READINESS,
        {"kind": "timezone_shift", "hours": h}, interp, impact, defensible, False, ref)
      for h, interp, impact, defensible, ref in (
          (0, "Raw times are before service hours for many sessions: T03 quarantines 303 of them and M5 falls to 82.05%.",
           "none: contradicted by the cross-export and hour-of-day evidence", False, (505.0, 989.1, 1394, 5.0, 1394, None)),
          (1, "Still leaves 103 sessions outside service hours.", "none: contradicted by the evidence", False, (498.5, 1019.5, 1594, 5.0, 1594, None)),
          (2, "No session leaves service hours; KPIs identical to +3h (weights do not depend on the clock). Only the weather join and hour-of-day differ.",
           "none: KPIs cannot separate +2h, +3h and +4h; the cross-export evidence selects +3h", True, (499.0, 1039.6, 1697, 5.0, 1697, None)),
          (3, "The approved baseline offset, reproduced.", "none: this is the baseline", True, (499.0, 1039.6, 1697, 5.0, 1697, None)),
          (4, "KPIs identical to +3h; the file's first events would be about 1.5 h later than the other exports'.",
           "none: KPIs cannot separate +2h, +3h and +4h; the cross-export evidence selects +3h", True, (499.0, 1039.6, 1697, 5.0, 1697, None)))],

    # ---- period / volume regime (diagnostic exclusions; never rules) ----------------------------------------------------------------------
    S("S20", "volume", "Exclude the six volume-irregularity days", "irregular-volume days", "the six days whose observed volume regime differs from the weekday baseline stay included",
      "those days are left out (diagnostic test only)", "Irregularity is a regime finding, not proof of corrupt data. Tests whether those days drive the profile.", ("fact_dining_session", "fact_daily_volume"), POP_REG,
      ALL_KPIS, {"kind": "exclude_dates", "set": "irregular_volume_days"}, "Removes 252 sessions; M2 +26.4 g (2.5%).", "none: the flag never excludes", True, True, (505.0, 1066.0, 1445, 5.0, None, None)),
    S("S21", "volume", "Exclude 2020-11-16 to 2020-11-20", "final week", "the final week is included", "the final week is left out (diagnostic test only)",
      "Four of the six irregular days fall in this week.", ("fact_dining_session",), POP_REG, ALL_KPIS, {"kind": "exclude_dates", "from": "2020-11-16", "to": "2020-11-20"},
      "Effect below 15 g on M2.", "none", True, True, (499.5, 1052.1, 1530, 5.0, None, None)),
    S("S22", "volume", "Exclude the 16 low-observed-volume days", "low-volume days", "low-volume days are included", "the 16 registered-export days under 30 sessions are left out (diagnostic test only)",
      "Low-volume days follow the weekday pattern (Thursday and Friday).", ("fact_dining_session", "fact_daily_volume"), POP_REG, ALL_KPIS, {"kind": "exclude_dates", "set": "low_volume_days"},
      "M1 -6 g, M2 +13.4 g.", "none", True, True, (493.0, 1053.0, 1507, 5.0, None, None)),
    S("S23", "period", "Period sensitivity: exclude the first two weeks", "study period", "the full 2020-10-05 to 2020-11-20 window",
      "2020-10-05 to 2020-10-16 is left out (period sensitivity, not a correction)", "The first two weeks are the period of the +3h file and of cross-export name disagreement. Not called bad data; tests whether the profile is period dependent.",
      ("fact_dining_session",), POP_REG, ALL_KPIS, {"kind": "exclude_dates", "before": "2020-10-19"}, "M2 falls by 62.6 g (6%): the upper end of the distribution is period dependent; M1 and M4 are not.",
      "M2 is described as period sensitive; the baseline window stays", True, True, (505.0, 977.0, 1312, 5.0, None, None)),

    # ---- definitions -------------------------------------------------------------------------------------------------------------------------------------
    S("S30", "definition", "M4 with raw component names", "component identity", "components are compared after trim, whitespace collapse and case-fold",
      "components are compared as written", "Tests whether the (deliberately minimal) normalization matters.", EVENT_TABLES, POP_REG, ("M4",), {"kind": "m4_definition", "definition": "raw_names"},
      "M4 unchanged.", "none", True, True, (499.0, 1039.6, 1697, 5.0, None, None)),
    S("S31", "definition", "M4 counted as distinct scales", "component identity", "distinct normalized component names", "distinct scales per session", "A name-free variant of breadth.",
      EVENT_TABLES, POP_REG, ("M4",), {"kind": "m4_definition", "definition": "scales"}, "M4 unchanged.", "none", True, True, (499.0, 1039.6, 1697, 5.0, None, None)),
    S("S32", "definition", "M4 counted as weighing events", "component identity", "distinct normalized component names", "weighing events per session", "The crudest variant of breadth.",
      EVENT_TABLES, POP_REG, ("M4",), {"kind": "m4_definition", "definition": "events"}, "M4 unchanged.", "none", True, True, (499.0, 1039.6, 1697, 5.0, None, None)),
    S("S33", "definition", "Exact duplicate rows summed", "duplicate handling", "exact repeat rows are left out of sums", "exact repeat rows are summed",
      "Shows what the duplicate rule protects against (one repeated 67 g row).", EVENT_TABLES, POP_REG, ALL_KPIS, {"kind": "weight_definition", "duplicates": "included"},
      "No headline effect; the rule matters for one session.", "none: exact repeats stay excluded", False, True, (499.0, 1039.6, 1697, 5.0, None, None)),

    # ---- population (diagnostic contrast and a forbidden guardrail) ----------------------------------------------------------------------------
    S("S40", "population", "DIAGNOSTIC: non-registered-export population", "population", "registered-export sessions only",
      "the other export, measured on its own", "Shows the two exports behave differently; never a KPI source and never pooled.", EVENT_TABLES, POP_NON, ALL_KPIS,
      {"kind": "population", "population": POP_NON}, "A different population with a different profile: pooling them would be misleading.", "none: never a KPI source", False, True,
      (192.0, 855.4, 1644, 2.0, None, None)),
    S("G01", "guardrail", "FORBIDDEN COMPARISON: pooled registered and non-registered sessions", "population", "populations are never pooled",
      "both populations pooled into one set (invalid; shown only to demonstrate population-confounding risk)",
      "A guardrail, not a candidate interpretation: it demonstrates why the populations must not be pooled.", EVENT_TABLES, "pooled (forbidden)", ALL_KPIS, {"kind": "pooled"},
      "Pooling changes the headline numbers by an amount that reflects population mix, not measurement.", "none: forbidden; excluded from every range and conclusion", False, True, None, forbidden=True),
)

# The guardrail is registered and executed so its danger is visible, but it is not part of any range or conclusion.
GUARDRAIL_IDS = tuple(s.scenario_id for s in SCENARIOS if s.forbidden or s.group == "guardrail")
SCENARIO_BY_ID = {s.scenario_id: s for s in SCENARIOS}


# ---- registry validation: an illegitimate declaration is refused before anything runs -------------------------------------------------------
APPROVED_OVERRIDE_OFFSET_HOURS = 3          # the approved file-specific normalization; a scenario may test others but never replaces it
KNOWN_METRICS = {"M1", "M2", "M3", "M4", "M5", "S2"}
EXCLUSION_KINDS = {"exclude_session", "exclude_weight_outside", "exclude_where", "exclude_where_any_warn", "exclude_dates", "drop_event"}


def validate_registry(specs: tuple[ScenarioSpec, ...] = SCENARIOS) -> list[str]:
    """Problems with the declarations themselves (empty list = valid). Encodes what a scenario is NOT allowed to be."""
    problems: list[str] = []
    ids = [s.scenario_id for s in specs]
    if len(set(ids)) != len(ids):
        problems.append("scenario ids are not unique")
    baselines = [s for s in specs if s.operation.get("kind") == "baseline"]
    if [s.scenario_id for s in baselines] != ["S00"]:
        problems.append("exactly one scenario, S00, may be the baseline, and it must not change anything")
    for s in specs:
        kind = s.operation.get("kind")
        if not set(s.metrics_recalculated) <= KNOWN_METRICS:
            problems.append(f"{s.scenario_id}: unknown metric in {s.metrics_recalculated} (no waste, consumption or proxy metric may be recalculated)")
        if kind == "pooled" and not (s.forbidden and not s.defensible):
            problems.append(f"{s.scenario_id}: pooling the populations is a forbidden comparison, never a candidate interpretation")
        if kind == "population" and not (s.diagnostic_only and not s.defensible):
            problems.append(f"{s.scenario_id}: an alternative population is a diagnostic contrast only")
        if kind in EXCLUSION_KINDS and not s.diagnostic_only:
            problems.append(f"{s.scenario_id}: an exclusion may only be diagnostic; it can never become a production rule")
        if kind == "include" and not (s.diagnostic_only and not s.defensible):
            problems.append(f"{s.scenario_id}: including quarantined sessions is a what-if only; the quarantine is never weakened")
        if kind == "timezone_shift" and not (isinstance(s.operation.get("hours"), int) and 0 <= s.operation["hours"] <= 4):
            problems.append(f"{s.scenario_id}: a timezone scenario must shift by 0-4 whole hours")
        if s.phase2 is not None and len(s.phase2) != 6:
            problems.append(f"{s.scenario_id}: a Phase 2 reference has six values")
    return problems
