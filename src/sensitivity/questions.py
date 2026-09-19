"""The evidence matrix questions and the uncertainty register, as declarations. Measured figures are formatted from the computed results; the few
approximate magnitudes quoted in prose ("about 60 g", "about 26 g") are checked against the results by tests, so the text cannot drift.

Robustness rules for a question:
  worst       the most severe class over the listed metrics and scenarios (computed; conservative)
  structural  a conclusion about reconstruction itself, backed by controls rather than by a numeric band
  declared    depends on an unresolved assumption that no scenario can resolve; stated with its reason
  blocked     no defensible conclusion can be produced because the required evidence is unavailable
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from src.sensitivity.registry import GUARDRAIL_IDS


@dataclass(frozen=True)
class Question:
    question_id: str
    question: str
    rule: str
    metrics: tuple[str, ...]
    scenarios: tuple[str, ...]
    baseline_evidence: Callable[["Facts"], str]
    sensitivity_tested: str
    can_conclude: str
    cannot_conclude: str
    next_evidence: str
    declared_class: str | None = None
    basis: str = ""


class Facts:
    """Read-only accessor over computed results, used to format text."""

    def __init__(self, results: dict[str, Any], ranges: dict[str, Any], tz: list[dict[str, Any]]):
        self.results, self.ranges, self.tz = results, ranges, tz

    def v(self, sid: str, metric: str) -> float:
        return getattr(self.results[sid], {"M1": "m1", "M2": "m2", "M3": "m3", "M4": "m4", "M5": "m5", "S2": "s2"}[metric])

    def d(self, sid: str, metric: str) -> float:
        return self.v(sid, metric) - self.v("S00", metric)

    def rng(self, metric: str) -> str:
        lo, hi = self.ranges[metric]["min"], self.ranges[metric]["max"]
        return f"{lo:,.1f}-{hi:,.1f}" if metric in ("M1", "M2") else (f"{lo:g}-{hi:g}" if metric == "M4" else f"{lo:,.2f}-{hi:,.2f}")


QUESTIONS: tuple[Question, ...] = (
    Question("Q1", "Can a selected-meal-weight distribution be reconstructed from the available component weighing events?", "structural", ("M1", "M2"), ("S00", "S33", "S04", "S05"),
             lambda f: f"Weights of all 3,341 non-quarantined sessions were reconstructed independently and equal the validation working value; M1 {f.v('S00', 'M1'):,.0f} g and M2 {f.v('S00', 'M2'):,.1f} g.",
             "Duplicate handling (S33), removal of the largest observation (S04, S05), outlier bounds (S06, S07).",
             "A distribution of DERIVED selected meal weight (the sum of what was weighed at the line per session) can be reconstructed for the registered-export population.",
             "That the distribution describes what was eaten or wasted.", "A source of consumed or discarded weight per tray.", "STABLE", "controls: 3,341 of 3,341 weights reconstructed and matched"),
    Question("Q2", "Is the median derived selected meal weight of the same order of magnitude under reasonable scenarios?", "worst", ("M1",), ("ALL",),
             lambda f: f"Baseline M1 {f.v('S00', 'M1'):,.0f} g.", "All registered-export scenarios: crossover, outliers, timezone, period, volume days, definitions.",
             "Median derived selected meal weight is about 500 g under every registered-export scenario tested.", "That the median is a portion size that was eaten.", "Longer observation window; a second site.", None, ""),
    Question("Q3", "How stable is the upper end of the distribution (P90)?", "worst", ("M2",), ("ALL",),
             lambda f: f"Baseline M2 {f.v('S00', 'M2'):,.1f} g.", "All registered-export scenarios.",
             "P90 stays near 1,000-1,070 g, but moves by up to about 60 g (6%) with the study period and with the timezone hypothesis.",
             "A precise P90: it should be quoted with its range and its dependence on the period.", "A longer window, to see whether the first two weeks are unusual.", None, ""),
    Question("Q4", "Does the component-count result remain stable?", "worst", ("M4",), ("ALL",), lambda f: f"Baseline M4 {f.v('S00', 'M4'):g} components.",
             "All registered-export scenarios and three alternative definitions (raw names, distinct scales, weighing events).",
             "The typical session records five distinct component names, however breadth is counted.", "Which dishes were chosen, or that different names are different dishes.",
             "A component master list to replace string matching.", None, ""),
    Question("Q5", "Is the registered-export valid-session count and readiness stable to the timezone and crossover assumptions?", "worst", ("M3", "M5"),
             ("S01", "S02", "S03", "TZ0", "TZ1", "TZ2", "TZ3", "TZ4"),
             lambda f: f"Baseline M3 {f.v('S00', 'M3'):,} sessions; M5 {f.v('S00', 'M5'):.2f}% ({f.results['S00'].m5_numerator:,} / {f.results['S00'].m5_denominator:,}).",
             "Timezone of the suspect export (+0h to +4h, that file only) and the crossover sessions.",
             "Under +2h, +3h and +4h the count and readiness are identical; the count and M5 fall sharply only if the file is treated as un-shifted or shifted by 1 h, which the evidence contradicts.",
             "That readiness is high for a reason other than the few ERROR-level findings; lifting the quarantine (100%) is not a valid readiness figure.",
             "Confirmation of the timezone metadata from the source owner.", None, ""),
    Question("Q6", "Does the treatment of the two crossover sessions change any conclusion?", "worst", ("M1", "M2", "M4"), ("S01", "S02", "S03"),
             lambda f: "Both crossover session ids are quarantined in both populations; neither version is preferred.", "Including both, or either, registered-export version (what-if only).",
             "No conclusion changes: the largest effect is about 3 g on M2.", "That either version is correct. M5 rising to 100% is an artifact of lifting the quarantine.", "The source owner's account of which version is authoritative.", None, ""),
    Question("Q7", "Do the six irregular-volume days change the measurement profile?", "worst", ("M1", "M2", "M4"), ("S20", "S21", "S22"),
             lambda f: "Six registered-export days have an observed volume regime that differs from the weekday baseline; all are kept.", "Excluding those days, the last week, or the low-volume days (diagnostic only).",
             "M1 and M4 are unchanged in practice; M2 moves by up to about 26 g when those days are left out.", "That the irregular days are errors, or what caused them. Volume flags never exclude.",
             "Operational records (menu, closures, events) for those days.", None, ""),
    Question("Q8", "Does the study period matter (the first two weeks)?", "worst", ("M1", "M2", "M4"), ("S23",),
             lambda f: "The first two weeks contain the +3h-normalized export and the cross-export name disagreement.", "Excluding 2020-10-05 to 2020-10-16 (period sensitivity, not a correction).",
             "M1 and M4 do not depend on the period; M2 is period sensitive (about -63 g).", "That the first two weeks are bad data.", "More weeks of data.", None, ""),
    Question("Q9", "Is the 2,097 g observation influential?", "worst", ("M1", "M2", "M4"), ("S04", "S05"), lambda f: "One event of 2,097 g in session2104 is kept and modellable.",
             "Removing the event or its session (analytic only).", "It is an unusual observation, not an invalid one, and it moves M2 by about 1.6 g.", "Whether the value is a scale artifact or a real portion.",
             "Scale calibration or tray photographs.", None, ""),
    Question("Q10", "Should the warn-free rate be read as a second readiness score?", "worst", ("M1", "M2"), ("S10",),
             lambda f: f"S2 {f.v('S00', 'S2'):.2f}% versus M5 {f.v('S00', 'M5'):.2f}%; the event-level diagnostic is 97.70%.", "Excluding every session with any WARN.",
             "No: a WARN is a diagnostic flag that never removes a session; excluding flagged sessions moves M2 by about -25 g.", "That flagged sessions are wrong or that S2 measures accuracy.", "Ground-truth checks on a sample of flagged sessions.", None, ""),
    Question("Q11", "Which timezone does the suspect export use, and do the KPIs decide it?", "declared", ("M1", "M2", "M3", "M4", "M5"), ("TZ0", "TZ1", "TZ2", "TZ3", "TZ4"),
             lambda f: "A +3h file-specific normalization is the strongest-supported engineering decision; the source does not confirm the timezone metadata.",
             "+0h to +4h on that file only.",
             "The KPIs cannot separate +2h, +3h and +4h; the time-of-day evidence places only +3h inside the band of the other exports. Weather-hour joins depend on the choice.",
             "That +3h is confirmed by the source, or that it is a general Helsinki rule.", "The source owner's confirmation.", "CONDITIONAL", "depends on an unresolved, evidence-backed assumption"),
    Question("Q12", "Can actual consumption be determined from selected meal weight alone?", "blocked", (), (), lambda f: "Consumed quantity is UNKNOWN in the semantic chain.", "None: a sensitivity analysis cannot create consumption data.",
             "Nothing about consumption.", "Any amount consumed, left over or eaten.", "A measurement of what remains on the tray (or a plate-weight system) linked by tray id.", "BLOCKED", "required evidence is unavailable"),
    Question("Q13", "Can food waste be measured from the accessible data?", "blocked", (), (), lambda f: "W1 is BLOCKED / SOURCE GAP.", "None: no lower or upper waste bound, band or proxy is produced.",
             "That waste is not measurable from the accessible data.", "Any waste amount, potential waste, waste band or ratio.", "Per-tray waste weight with tray_id, waste timestamp and waste point, joinable to lunch-line trays.", "BLOCKED", "required source is not public"),
)


def uncertainty_rows(f: Facts) -> list[dict[str, Any]]:
    pct = lambda sid, m: f"{100 * f.d(sid, m) / f.v('S00', m):+.1f}%"
    return [
        {"uncertainty_id": "U01", "assumption": "Suspect export timezone: the file's timestamps are 3 hours early (a +3h, file-specific normalization).",
         "why_it_matters": "It sets the time of day, the service-hours rule, the weather join and readiness for 385 sessions.",
         "current_evidence": "An exact 10,800 s difference on the shared session3222; median first-event hour 7.54 h raw and 10.54 h after +3h against 10.53 h for the other registered-export files. Not source-confirmed.",
         "sensitivity_result": f"+2h/+3h/+4h give identical M1-M5; +0h quarantines {f.results['TZ0'].detail['t03_quarantined_sessions']} sessions (M5 {f.v('TZ0', 'M5'):.2f}%); +1h quarantines {f.results['TZ1'].detail['t03_quarantined_sessions']} (M5 {f.v('TZ1', 'M5'):.2f}%).",
         "impact_level": "HIGH", "affected_metrics": "M5;S2;weather join", "current_disposition": "Retained as +3h, file-specific; labelled NORMALISED_PLUS_3H_STRONGEST_SUPPORT",
         "evidence_that_would_resolve": "The source owner's confirmation of the export timezone."},
        {"uncertainty_id": "U02", "assumption": "Population labels (registered-export / non-registered-export) come from file names and mean only that.",
         "why_it_matters": "Pooling the populations changes every headline number and would confound a business reading.",
         "current_evidence": "The exports differ in weight (median 499 g versus 192 g) and structure; the labels are not interpreted.",
         "sensitivity_result": f"The diagnostic non-registered-export profile is M1 {f.v('S40', 'M1'):,.0f} g, M2 {f.v('S40', 'M2'):,.1f} g, M4 {f.v('S40', 'M4'):g}; the forbidden pooled comparison gives M1 {f.v('G01', 'M1'):,.0f} g (a population-mix artifact).",
         "impact_level": "HIGH", "affected_metrics": "M1;M2;M3;M4;M5", "current_disposition": "Never pooled; the registered-export population is the measurement population",
         "evidence_that_would_resolve": "The data owner's definition of the two exports."},
        {"uncertainty_id": "U03", "assumption": "Crossover sessions: two session ids present in both exports are quarantined rather than resolved.",
         "why_it_matters": "Lifting the quarantine would make readiness look perfect.",
         "current_evidence": "session2266 is identical in both exports; session3222 differs by 10,800 s and two component names.",
         "sensitivity_result": f"Including both changes M2 by {f.d('S01', 'M2'):+.1f} g and M5 to {f.v('S01', 'M5'):.1f}% only because the check is removed.",
         "impact_level": "LOW", "affected_metrics": "M3;M5", "current_disposition": "Quarantined in both populations; listed; never deleted", "evidence_that_would_resolve": "Which version is authoritative."},
        {"uncertainty_id": "U04", "assumption": "Component identity is the trimmed, whitespace-collapsed, case-folded name; there is no alias table.",
         "why_it_matters": "M4 counts names; language variants of one dish would count twice, different dishes with similar names must not merge.",
         "current_evidence": "246 raw and 245 normalized names; the two exports disagree on names for 86 scale-days in the first two weeks.",
         "sensitivity_result": f"M4 is {f.v('S30', 'M4'):g} with raw names, {f.v('S31', 'M4'):g} counting scales and {f.v('S32', 'M4'):g} counting weighing events.",
         "impact_level": "LOW", "affected_metrics": "M4", "current_disposition": "String normalization only; component comparison across exports is limited", "evidence_that_would_resolve": "A component master list."},
        {"uncertainty_id": "U05", "assumption": "Six days whose observed volume regime differs from the weekday baseline are real observations.",
         "why_it_matters": "They could reflect operations, closures or export coverage; excluding them is tempting but unjustified.",
         "current_evidence": "The baseline weeks separate perfectly (Monday-Wednesday high, Thursday-Friday low); the cause of the six exceptions is unresolved.",
         "sensitivity_result": f"Excluding them removes {f.results['S00'].m3 - f.results['S20'].m3} sessions and moves M2 by {f.d('S20', 'M2'):+.1f} g ({pct('S20', 'M2')}), M1 by {f.d('S20', 'M1'):+.0f} g.",
         "impact_level": "MEDIUM", "affected_metrics": "M2;M3", "current_disposition": "Flag only; retained; M3 is not demand", "evidence_that_would_resolve": "Operational records for those dates."},
        {"uncertainty_id": "U06", "assumption": "Derived selected meal weight is what was weighed at the line, not what was eaten.",
         "why_it_matters": "It is easy to read a selected weight as consumption.", "current_evidence": "The data records component weights when selected; nothing records what remained.",
         "sensitivity_result": "Not testable: no scenario can produce consumption from selection.", "impact_level": "BLOCKING", "affected_metrics": "M1;M2", "current_disposition": "UNKNOWN in the semantic chain; no consumed column exists",
         "evidence_that_would_resolve": "A per-tray measurement of the remaining food."},
        {"uncertainty_id": "U07", "assumption": "Direct food-waste measurement is unavailable.", "why_it_matters": "It is the business question the data was meant to inform.",
         "current_evidence": "The documented waste system has no public records; the catalogue page reads TODO.", "sensitivity_result": "Not testable: no lower or upper waste bound, band or proxy is produced.",
         "impact_level": "BLOCKING", "affected_metrics": "W1", "current_disposition": "BLOCKED / SOURCE GAP", "evidence_that_would_resolve": "Per-tray waste records joinable on tray_id."},
        {"uncertainty_id": "U08", "assumption": "The Turku weather station is a regional context, and r_1h is the hour ending at its timestamp.",
         "why_it_matters": "A causal reading of weather would be unsupported.", "current_evidence": "Station about 6 km away; hour-ending reading verified on one rainy day, not documented by FMI; three NaN values kept as NULL.",
         "sensitivity_result": f"Under the timezone hypotheses, all 385 sessions in the shifted file join a different weather hour (mean temperature difference {f.tz[0]['mean_abs_t2m_diff_c']} C for +0h).",
         "impact_level": "LOW", "affected_metrics": "S1", "current_disposition": "Context only; no causal claim", "evidence_that_would_resolve": "On-site sensors or a documented FMI convention."},
        {"uncertainty_id": "U09", "assumption": "Five weeks of data represent the measurement profile.", "why_it_matters": "P90 is period dependent.",
         "current_evidence": "The first two weeks contain the shifted export and the name disagreement.", "sensitivity_result": f"Excluding them moves M2 by {f.d('S23', 'M2'):+.1f} g ({pct('S23', 'M2')}); M1 by {f.d('S23', 'M1'):+.0f} g.",
         "impact_level": "MEDIUM", "affected_metrics": "M2", "current_disposition": "Full window kept; M2 quoted with its range", "evidence_that_would_resolve": "More weeks."},
        {"uncertainty_id": "U10", "assumption": "The diagnostic thresholds (B02, B07, T05, C02) describe this data and are not physical limits.", "why_it_matters": "Turning a flag into an exclusion would change the metrics.",
         "current_evidence": "Thresholds sit in natural gaps of the observed distributions.", "sensitivity_result": f"Applying B07 as an exclusion moves M2 by {f.d('S07', 'M2'):+.1f} g; any WARN as an exclusion by {f.d('S10', 'M2'):+.1f} g.",
         "impact_level": "LOW", "affected_metrics": "M2", "current_disposition": "Flags only", "evidence_that_would_resolve": "Physical limits from the scale vendor."},
    ]


def relevant_scenarios(question: Question, all_ids: list[str]) -> list[str]:
    return [s for s in all_ids if s not in GUARDRAIL_IDS and s != "S40"] if question.scenarios == ("ALL",) else list(question.scenarios)
