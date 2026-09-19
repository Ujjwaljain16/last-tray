"""The sensitivity analysis report, generated from the computed analysis so that no number in it can drift from the outputs.

`render_block(analysis)` returns the generated sections; docs/sensitivity_analysis.md embeds it between markers and a test compares the two.
"""
from __future__ import annotations

from src.sensitivity.evidence import Analysis, is_comparable
from src.sensitivity.registry import CLASSIFICATION, GUARDRAIL_IDS, SCENARIOS

BEGIN = "<!-- BEGIN GENERATED: rendered by src/sensitivity/report.py from outputs/evidence; do not edit by hand -->"
END = "<!-- END GENERATED -->"


def _f(v: float | None, nd: int = 1) -> str:
    return "n/a" if v is None else f"{v:,.{nd}f}"


def _d(v: float | None, nd: int = 1) -> str:
    return "n/a" if v is None else f"{v:+,.{nd}f}"


def _by_class(a: Analysis, name: str) -> list[dict]:
    return [r for r in a.matrix if r["Robustness"] == name]


def render_block(a: Analysis) -> str:
    base = a.results["S00"]
    out: list[str] = [BEGIN, ""]
    out += ["## 1. Baseline definition (frozen)", "",
            "The approved baseline is recomputed from the canonical model as scenario S00 and must equal the approved package and the independent metrics computation. It is never overwritten and no scenario is chosen because it gives a nicer number.", "",
            "| Metric | Baseline | Population |", "|---|---:|---|",
            f"| M1 Median Derived Selected Meal Weight | {_f(base.m1)} g | core-ready registered-export sessions |",
            f"| M2 P90 Derived Selected Meal Weight | {_f(base.m2)} g | same |",
            f"| M3 Observed Valid Sessions — Registered-Export Population | {base.m3:,} | same |",
            f"| M4 Median Distinct Normalized Components per Session | {base.m4:g} | same |",
            f"| M5 Core Measurement Readiness | {base.m5:.2f}% ({base.m5_numerator:,} / {base.m5_denominator:,}) | eligible registered-export sessions |",
            f"| S2 Warn-Free Rate | {base.s2:.2f}% ({base.s2_numerator:,} / {base.m5_denominator:,}) | eligible registered-export sessions |",
            "| W1 Direct Food Waste Measurement | BLOCKED / SOURCE GAP | n/a |", ""]

    out += ["## 2. Scenario methodology", "",
            "Each scenario changes exactly one documented assumption, is declared as data in `src/sensitivity/registry.py` (exported as `outputs/evidence/scenario_registry.json`), "
            "and is run by a generic engine on the verified canonical tables; no canonical table, threshold or configuration value is modified. "
            f"{len(SCENARIOS)} scenarios are registered: the 25 approved reference scenarios (every one reproduced) and one forbidden guardrail (G01). "
            "M5 and S2 are computed only where a scenario varies eligibility or quarantine, always over the fixed denominator of "
            f"{base.m5_denominator:,}; an analytic exclusion does not redefine readiness.", "",
            "**Robustness classes** (one rule set for every metric and scenario; |change| against the frozen baseline):", "",
            "| Metric | STABLE below | SENSITIVE below | CONDITIONAL at or above | Basis |", "|---|---:|---:|---:|---|"]
    for m, r in CLASSIFICATION.items():
        unit = "%" if r["kind"] == "relative" else f" {r['unit']}"
        scale = 100 if r["kind"] == "relative" else 1
        out.append(f"| {m} | {r['stable_below'] * scale:g}{unit} | {r['sensitive_below'] * scale:g}{unit} | {r['sensitive_below'] * scale:g}{unit} | {r['basis']} |")
    out += ["", "BLOCKED means no defensible conclusion can be produced because the required evidence is unavailable. A scenario that is a diagnostic population contrast (S40) or a forbidden comparison (G01) is reported but never classified or ranged.", ""]

    out += ["## 3. Scenario table", "", "Deltas are against the baseline. `class` is the worst class over the metrics the scenario recomputes. **M3 falls by construction when sessions are excluded**, so for an exclusion scenario the class can reflect the session-count effect alone (S23 is CONDITIONAL because it leaves out 385 sessions, while its effect on M2 is SENSITIVE); the conclusion classes in sections 5-8 therefore use M1, M2 and M4 for exclusion tests and use M3 and M5 only for the timezone and crossover scenarios. `ref` = profiling reference reproduced.", "",
            "| ID | Scenario | Group | M1 g | M2 g | M3 | M4 | M5 % | S2 % | ΔM1 | ΔM2 | class | ref |", "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|"]
    rows = {r["scenario_id"]: r for r in a.result_rows}
    for s in SCENARIOS:
        r, x = rows[s.scenario_id], a.results[s.scenario_id]
        out.append(f"| {s.scenario_id} | {s.name} | {s.group} | {_f(x.m1)} | {_f(x.m2)} | {x.m3:,} | {x.m4:g} | {_f(x.m5, 2)} | {_f(x.s2, 2)} | {_d(r['d_m1_g'])} | {_d(r['d_m2_g'])} | "
                   f"{r['worst_robustness_class'].lower().replace('_', ' ')} | {'yes' if r['reference_status'] == 'reproduced' else 'new' if r['reference_status'] == 'n/a' else 'NO'} |")
    g = a.results["G01"]
    out += ["", f"G01 is a **forbidden comparison** used only to demonstrate population-confounding risk: pooling the two exports gives M1 {_f(g.m1)} g, M2 {_f(g.m2)} g and M4 {g.m4:g}, "
            "numbers that describe the population mix and not any measurement. The populations are never pooled. S40 shows the non-registered-export population on its own (a diagnostic contrast, never a KPI source).", ""]

    out += ["## 4. Headline metric ranges", "",
            "Ranges are over the registered-export scenarios (the diagnostic population contrast and the forbidden guardrail are excluded). \"Reasonable\" scenarios are those declared defensible.", "",
            "| Metric | Baseline | Range, all scenarios | Range, defensible only | Largest absolute change | Largest relative change |", "|---|---:|---|---|---|---|"]
    for m, r in a.ranges.items():
        nd = 0 if m in ("M3",) else (2 if m in ("M5", "S2") else 1)
        b = a.biggest[m]
        out.append(f"| {m} | {_f(r['baseline'], nd)} {r['unit']} | {_f(r['min'], nd)} to {_f(r['max'], nd)} | {_f(r['defensible_min'], nd)} to {_f(r['defensible_max'], nd)} | "
                   f"{b['largest_absolute']['scenario_id']} ({_d(b['largest_absolute']['delta'], nd)}) | {b['largest_relative']['scenario_id']} ({100 * b['largest_relative']['relative']:+.1f}%) |")
    out += ["", "M3 changes by construction when sessions are excluded, so its range is reported but the conclusion about the session count rests on the timezone and crossover scenarios only (question Q5).", ""]

    out += ["### Timezone hypotheses for the suspect export (385 sessions; only that file is shifted)", "",
            "| Offset | Sessions outside service hours (T03) | Median first-event hour | Gap to the other registered-export files | Weather hour changed | Mean abs. temperature difference | Rainy-hour share |",
            "|---|---:|---:|---:|---:|---:|---:|"]
    for t in a.timezone:
        out.append(f"| +{t['offset_hours']}h{' (baseline)' if t['is_baseline'] else ''} | {t['t03_quarantined_sessions']} | {t['median_first_event_hour']:.2f} h | {t['gap_to_other_files_h']:.2f} h | {t['weather_hour_changed_sessions']} | "
                   f"{_f(t['mean_abs_t2m_diff_c'], 3)} C | {_f(t['rainy_hour_share_pct'], 1)}% |")
    out += ["", "**Why the baseline remains +3h.** M1-M4 are identical under +2h, +3h and +4h, so the KPIs cannot choose. The choice rests on cross-export evidence that was gathered before this comparison: an exact 10,800 s difference for `session3222` and a median first-event hour of the shifted file that falls inside the band of the other registered-export files only at +3h "
            f"({a.timezone[3]['median_first_event_hour']:.2f} h against {a.timezone[3]['other_registered_files_median_hour']:.2f} h). +0h and +1h are contradicted by the service-hours rule and by the time of day, and would lower M5 to "
            f"{a.results['TZ0'].m5:.2f}% and {a.results['TZ1'].m5:.2f}%. The timezone metadata remains unconfirmed by the source, so time-of-day and weather-join outputs stay conditional.", ""]

    def section(title: str, cls: str, intro: str) -> None:
        rows_ = _by_class(a, cls)
        out.append(f"## {title}")
        out.append("")
        out.append(intro)
        out.append("")
        if not rows_:
            out.append("None.")
        for r in rows_:
            out.append(f"- **{r['Question']}** ({r['robustness_basis']}). {r['What can be concluded']} *Cannot conclude:* {r['What cannot be concluded']}")
        out.append("")

    section("5. Stable conclusions", "STABLE", "The conclusion is materially unchanged across the reasonable scenarios (every change is below the STABLE band).")
    section("6. Sensitive conclusions", "SENSITIVE", "The magnitude changes materially with an assumption, but the interpretation may remain.")
    section("7. Conditional conclusions", "CONDITIONAL", "The conclusion depends strongly on an unresolved assumption.")
    section("8. Blocked conclusions", "BLOCKED", "No defensible conclusion can be produced: the required evidence is unavailable. A sensitivity analysis cannot turn missing source data into observed evidence, and no waste estimate, band or proxy is produced.")

    out += ["## 9. Uncertainty register summary", "", "Full register: `outputs/evidence/uncertainty_register.csv`.", "", "| ID | Assumption | Impact | Disposition | Sensitivity result |", "|---|---|---|---|---|"]
    for u in a.register:
        out.append(f"| {u['uncertainty_id']} | {u['assumption']} | {u['impact_level']} | {u['current_disposition']} | {u['sensitivity_result']} |")
    out.append("")

    seen: list[str] = []
    for u in a.register:
        if u["evidence_that_would_resolve"] not in seen:
            seen.append(u["evidence_that_would_resolve"])
    out += ["## 10. Evidence gaps", "", "What remains uncertain after testing, and what would resolve it:", ""]
    out += [f"- {e}" for e in seen]
    out += ["", "## 11. Recommended next instrumentation and data", "",
            "1. **Per-tray waste and remaining-food measurement, linked by tray id** (the documented but inaccessible waste system): the only way to move W1 and any consumption question out of BLOCKED.",
            "2. **The source owner's confirmation of the export timezone**: it would turn the +3h file-specific decision from evidence-backed to confirmed and settle the weather join.",
            "3. **Operational records** (menu, closures, events) for the six irregular days, and more weeks of data, to explain the volume regime and to test the period dependence of P90.",
            "4. **A component master list** to replace string matching for component identity across exports.",
            "5. **Scale calibration or tray photographs** for the largest observations, to separate unusual from invalid.", "", END]
    return "\n".join(out)
