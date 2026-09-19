"""Metric CONTRACTS: what each metric means, who is in it, and what it may and may not be used to say.

This file holds declarations only. It contains no calculation. `src/metrics/compute.py` calculates, `src/metrics/evaluate.py` presents, and
tests compare the three so the contract, the code and the documentation cannot drift apart.

The approved reference values are the Phase 2 baseline reproduced by the pipeline (docs/metric_contract.md, decision D28). They are the
tolerance targets. A computed value that misses its tolerance FAILS the metric; the formula is never adjusted to fit.

Language rule: derived_selected_meal_weight_g is DERIVED. It is not consumption, not food waste, not leftovers and not actual intake.
"""
from __future__ import annotations

from dataclasses import dataclass, fields

A, B, C, D, E = ("all_observed_sessions", "non_quarantined_modelled_sessions", "eligible_registered_export_sessions",
                 "core_ready_registered_export_sessions", "non_registered_export_sessions")

TELLS_NOT_WEIGHT = "How much food was actually consumed, left over or wasted; it says nothing about intake."
CANONICAL_SOURCE = ("fact_dining_session",)


@dataclass(frozen=True)
class MetricContract:
    metric_id: str
    metric_name: str
    role: str                       # headline | supporting | diagnostic | blocked
    business_question: str
    definition: str
    unit: str
    grain: str
    population: str                 # the population the metric is computed over (the DENOMINATOR population for ratios)
    numerator_population: str | None
    population_rationale: str
    numerator: str
    denominator: str
    formula: str
    filters: str
    exclusions: str
    quarantine_handling: str
    null_handling: str
    statistical_method: str
    source_tables: tuple[str, ...]
    lineage: str
    interpretation: str
    limitation: str
    tells_us: str
    does_not_tell_us: str
    approved_value: float | int | None
    tolerance: float | None
    evidence_status: str            # READY_WITH_LIMITATION | BLOCKED

    def as_dict(self) -> dict:
        return {f.name: (list(getattr(self, f.name)) if isinstance(getattr(self, f.name), tuple) else getattr(self, f.name)) for f in fields(self)}


LINEAGE = ("metric -> fact_dining_session rows (population filter) -> session_key -> fact_weighing_event rows (event_id = source_file#row) "
           "-> stg_weighing_event -> raw source file and row")
NO_FILTER = "no filter beyond the population; WARN and INFO findings, weather and volume flags never filter a metric"

CONTRACTS: dict[str, MetricContract] = {c.metric_id: c for c in (
    MetricContract(
        "M1", "Median Derived Selected Meal Weight", "headline",
        "What does a typical selected meal weigh at the lunch line?",
        "The median of derived_selected_meal_weight_g over the core-ready registered-export sessions.", "g", "one session key (session_id|registered_export)",
        D, None, "The approved measurement population: registered-export sessions that meet the core readiness criteria. Never pooled with the other export.",
        "not applicable (a location statistic)", "not applicable", "MEDIAN(derived_selected_meal_weight_g) over the population",
        "population D only; " + NO_FILTER,
        "the two quarantined crossover sessions (they are not core-ready); the non-registered-export population; exact-duplicate rows (left out of the sums that build the weight)",
        "quarantined sessions have no canonical weight and are outside population D; they contribute nothing and remain listed",
        "a NULL weight is excluded and counted; it is never read as 0; an empty population raises",
        "median: middle value of the sorted weights (mean of the two middle values for an even count)", ("fact_dining_session",), LINEAGE,
        "Typical DERIVED selected meal weight in the approved measurement population.",
        "DERIVED from weighing events at the line; one population; five weeks; cannot be read as intake.",
        "The typical weight a session recorded across its selected components at the lunch line.", TELLS_NOT_WEIGHT, 499.0, 0.0, "READY_WITH_LIMITATION"),
    MetricContract(
        "M2", "P90 Derived Selected Meal Weight", "headline",
        "How heavy is a large selection: the weight that 90% of sessions do not exceed?",
        "The 90th percentile of derived_selected_meal_weight_g over the core-ready registered-export sessions, by linear interpolation.", "g",
        "one session key (session_id|registered_export)", D, None, "Same population as M1.", "not applicable", "not applicable",
        "PERCENTILE_LINEAR(derived_selected_meal_weight_g, 0.90) over the population", "as M1", "as M1", "as M1", "as M1",
        "linear interpolation at position (n - 1) * 0.90 of the sorted weights; identical to numpy/pandas quantile(0.9) and R type 7; not nearest-rank",
        ("fact_dining_session",), LINEAGE, "Upper end of the DERIVED selected meal weight distribution.",
        "the most period-sensitive metric; describes five weeks; DERIVED, not intake.",
        "How heavy the heavier selections are (the 90th percentile).", TELLS_NOT_WEIGHT, 1039.6, 0.05, "READY_WITH_LIMITATION"),
    MetricContract(
        "M3", "Observed Valid Sessions — Registered-Export Population", "headline",
        "How many registered-export sessions meet the core readiness criteria and therefore contribute to the KPIs?",
        "The number of registered-export session keys that satisfy the core readiness contract: not quarantined, at least one modellable event, no ERROR finding, "
        "valid weights, parsed times.", "sessions", "one session key (session_id|registered_export); per service date in the supporting table",
        D, None, "The same approved measurement population as M1, M2 and M4.", "not applicable", "not applicable", "COUNT(session keys) over the population",
        "population D only; " + NO_FILTER, "the two quarantined crossover sessions (kept in M5's denominator); the non-registered-export population",
        "quarantined sessions are outside population D and listed in the quarantine manifest", "not applicable", "count",
        ("fact_dining_session", "fact_daily_volume"), LINEAGE,
        "How many registered-export sessions were observed, are valid and feed M1, M2 and M4.",
        "an observation of the export; the weekday pattern and six irregular days mean it must not be read as restaurant volume.",
        "How many valid registered-export sessions the export contains.",
        "Demand, customers, diners, visits, transactions or traffic; it does not measure how busy the restaurant was.", 1697, 0.0, "READY_WITH_LIMITATION"),
    MetricContract(
        "M4", "Median Distinct Normalized Components per Session", "headline",
        "How broad is a typical selection, counted in distinct normalized component names?",
        "The median of distinct_component_count over the core-ready registered-export sessions, where a component is a distinct name after trim, whitespace collapse and case-fold.",
        "components", "one session key (session_id|registered_export)", D, None, "Same population as M1.", "not applicable", "not applicable",
        "MEDIAN(distinct_component_count) over the population", "as M1", "as M1", "as M1", "a NULL count is excluded and counted; never read as 0",
        "median: middle value of the sorted counts", ("fact_dining_session", "fact_session_component"), LINEAGE,
        "How many different named components a typical session selected.",
        "counts names within a session; no alias table, so different spellings of one dish would count separately; comparison of components across exports is limited on some days.",
        "How many distinct component names a typical session recorded.", "Which dishes were chosen, nutritional variety, or how much of anything was eaten.", 5, 0.0, "READY_WITH_LIMITATION"),
    MetricContract(
        "M5", "Core Measurement Readiness", "headline",
        "What share of the eligible registered-export sessions can be reconstructed and used?",
        "Core-ready registered-export sessions divided by all eligible registered-export sessions, the denominator being fixed before any quarantine or removal.", "percent",
        "one session key (session_id|registered_export)", C, D,
        "The denominator is every registered-export session in the source (1,699), counted before removal, so the quarantined sessions stay visible in it. It is never recomputed after removal.",
        "core-ready registered-export sessions (population D)", "eligible registered-export sessions (population C, fixed)",
        "100 * COUNT(D) / COUNT(C)", "numerator population D; denominator population C", "none from the denominator; the two quarantined crossover sessions are simply not core-ready",
        "quarantined sessions stay in the denominator and are absent from the numerator; that explains the 2-session gap", "not applicable", "ratio, not a statistic",
        ("fact_dining_session",), LINEAGE,
        "Share of eligible registered-export sessions meeting the approved core measurement readiness criteria.",
        "high because few registered-export sessions carry an ERROR finding, not because the data is proven error-free; weather, WARN rules and volume flags never enter it.",
        "What share of the eligible registered-export sessions meet the core readiness criteria.",
        "That the data, the meals or the measurements are correct or accurate, or that sessions are free of warnings.", 99.88, 0.005, "READY_WITH_LIMITATION"),
    MetricContract(
        "S1", "Weather Context Coverage", "supporting",
        "For what share of eligible registered-export sessions is a weather observation joined?",
        "Eligible registered-export sessions with weather_matched, divided by all eligible registered-export sessions.", "percent", "one session key (session_id|registered_export)",
        C, None, "Same fixed denominator as M5.", "eligible registered-export sessions with a joined weather observation", "eligible registered-export sessions (population C, fixed)",
        "100 * COUNT(weather_matched) / COUNT(C)", "population C; no filter", "none; the two quarantined sessions are NOT_ATTEMPTED (the model does not join quarantined sessions), so they are unmatched here",
        "quarantined sessions are not joined and count as unmatched", "NULL weather values are counted separately and never filled", "ratio",
        ("fact_dining_session", "fact_weather"), LINEAGE + "; weather join -> fact_weather (station x UTC hour) -> stg_weather_observation",
        "Coverage of the contextual weather join (next full UTC hour after the first weighing; r_1h is the hour ending at its timestamp).",
        "context only; regional station roughly 6 km away; the Phase 2 dry run matched all 1,697 core-ready sessions and expected the two quarantined sessions to be joined too, which the model deliberately does not do.",
        "Whether a weather observation is available for the session's hour.", "That weather affected weight, dining behaviour or anything else.", 99.88, 0.005, "READY_WITH_LIMITATION"),
    MetricContract(
        "S2", "Warn-Free Rate", "supporting",
        "What share of eligible registered-export sessions carry no session-level warning?",
        "Core-ready registered-export sessions with no session-level WARN (B04, B07, T04, T05, I06), divided by all eligible registered-export sessions.", "percent",
        "one session key (session_id|registered_export)", C, None, "Same fixed denominator as M5.",
        "core-ready registered-export sessions with no session-level WARN", "eligible registered-export sessions (population C, fixed)",
        "100 * COUNT(core_ready AND NOT has_session_warn) / COUNT(C)", "population C", "event-level warnings (B02, I02), file-level (T07) and day-level (C02) flags are not counted",
        "quarantined sessions stay in the denominator and are not in the numerator", "not applicable", "ratio",
        ("fact_dining_session",), LINEAGE, "Share of eligible registered-export sessions with no session-level warning.",
        "a diagnostic of how many sessions carry a WARN, not a data-quality score; it differs from M5 because a WARN never removes a session from the KPIs.",
        "How many eligible sessions carry no session-level warning.", "Whether the data is correct, or that flagged sessions are wrong (a WARN is a diagnostic flag).", 97.88, 0.005, "READY_WITH_LIMITATION"),
    MetricContract(
        "S2D", "Warn-Free Rate incl. Event-Level Warnings (diagnostic variant)", "diagnostic",
        "How does the warn-free rate change if event-level warnings are also counted?",
        "As S2, but a session with an event-level WARN (B02, I02) and no session-level WARN also counts as warned.", "percent", "one session key (session_id|registered_export)",
        C, None, "Same fixed denominator as M5.", "core-ready sessions with no session-level or event-level WARN", "eligible registered-export sessions (population C, fixed)",
        "100 * COUNT(core_ready AND NOT has_session_warn AND NOT has_event_warn) / COUNT(C)", "population C", "as S2 plus event-level warnings are counted",
        "as S2", "not applicable", "ratio", ("fact_dining_session",), LINEAGE, "Reconciliation of S2 to the event-level view (three sessions differ). It never replaces S2.",
        "diagnostic only; reported so the S2 definition is transparent.", "How much the choice of which WARN rules count changes the rate.", "A better or truer warn-free figure; S2 is the approved one.",
        97.70, 0.005, "READY_WITH_LIMITATION"),
    MetricContract(
        "W1", "Direct Food Waste Measurement", "blocked",
        "How much food was wasted?",
        "BLOCKED / SOURCE GAP. The Flavoria system documents lunch-line waste measurement keyed on tray, but no direct waste records are available in the public data this project can reach.",
        "n/a", "n/a", "n/a", None, "There is no computable population.", "n/a", "n/a", "none: there is no formula, no estimate and no proxy",
        "none", "none", "not applicable", "the value is NULL, never 0", "none", (), "none",
        "No direct waste metric is computed. derived_selected_meal_weight_g is not waste and is not used as a proxy.",
        "permanent unless a public raw waste dataset is found.", "That direct waste data exists conceptually and is not publicly available here.",
        "Any amount of food waste, consumption, or leftovers, or any ratio to selected weight.", None, None, "BLOCKED"),
)}

HEADLINE = ("M1", "M2", "M3", "M4", "M5")
ORDER = ("M1", "M2", "M3", "M4", "M5", "S1", "S2", "S2D", "W1")
