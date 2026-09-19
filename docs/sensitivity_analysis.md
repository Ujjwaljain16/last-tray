# Sensitivity Analysis and Evidence Robustness (WP7)

**Purpose.** Answer one question with evidence: *would the important conclusions materially change if reasonable, explicitly documented assumptions changed?*
Every scenario changes one assumption of the approved baseline and recomputes the affected metrics. The baseline is frozen (M1 499 g, M2 1,039.6 g, M3 1,697,
M4 5, M5 99.88%, S2 97.88%, W1 BLOCKED / SOURCE GAP) and is never overwritten or tuned. A scenario is a **sensitivity test, not an alternative truth**, and no scenario
is chosen because it gives a better number. This is not a leaderboard.

**How it runs.** `python -m src.pipeline.run` (stage `sensitivity`) reads only the verified canonical model tables (never staging or raw files), runs the scenarios
declared in `src/sensitivity/registry.py`, and writes `outputs/evidence/`: `scenario_registry.json` and `.csv` (the declarations), `sensitivity_results.csv` (one row per scenario),
`metric_sensitivity.csv` (one row per metric and scenario), `timezone_evidence.csv`, `evidence_matrix.csv`, `uncertainty_register.csv`, `sensitivity_summary.json`,
`sensitivity_controls.csv` and four figures. It **fails** (exit 10) if the baseline moves or an approved Phase 2 reference stops reproducing, and reports the difference instead of adjusting anything.

**Phase 2 provenance.** The 25 approved Phase 2 scenarios (S00-S40) were produced by `research/phase2/phase2_e_sensitivity.py`; all 25 are reproduced here from the canonical model
(M1 and M2 within 0.05 g, counts exact), including the weather consequences of each timezone hypothesis. One scenario is new: **G01**, a forbidden guardrail.

**Guardrails.** Population pooling is not a candidate interpretation (G01 demonstrates why). The crossover what-ifs (S01-S03) never weaken the quarantine, and a 100% M5 in S01 is an artifact of lifting it.
The 2,097 g event is an *unusual* observation, not an *invalid* one, and stays in the canonical data and the baseline. Irregular-volume days are a regime finding, not proof of corrupt data.
No scenario produces a consumption or food-waste estimate, band or proxy.

### Figures

| Figure | Shows |
|---|---|
| `outputs/evidence/figures/m1_m2_sensitivity.png` | M1 and M2 under every registered-export scenario, with the baseline marked and the robustness class of each point |
| `outputs/evidence/figures/m5_readiness_what_if.png` | M5 under the crossover what-ifs and the timezone hypotheses, over the fixed denominator |
| `outputs/evidence/figures/timezone_evidence.png` | Time of day and service-hours quarantine by candidate offset for the suspect export |
| `outputs/evidence/figures/period_and_volume_tests.png` | The period and volume-day exclusion tests (diagnostic only) |

<!-- BEGIN GENERATED: rendered by src/sensitivity/report.py from outputs/evidence; do not edit by hand -->

## 1. Baseline definition (frozen)

The approved baseline is recomputed from the canonical model as scenario S00 and must equal the approved package and the independent WP6 computation. It is never overwritten and no scenario is chosen because it gives a nicer number.

| Metric | Baseline | Population |
|---|---:|---|
| M1 Median Derived Selected Meal Weight | 499.0 g | core-ready registered-export sessions |
| M2 P90 Derived Selected Meal Weight | 1,039.6 g | same |
| M3 Observed Valid Sessions — Registered-Export Population | 1,697 | same |
| M4 Median Distinct Normalized Components per Session | 5 | same |
| M5 Core Measurement Readiness | 99.88% (1,697 / 1,699) | eligible registered-export sessions |
| S2 Warn-Free Rate | 97.88% (1,663 / 1,699) | eligible registered-export sessions |
| W1 Direct Food Waste Measurement | BLOCKED / SOURCE GAP | n/a |

## 2. Scenario methodology

Each scenario changes exactly one documented assumption, is declared as data in `src/sensitivity/registry.py` (exported as `outputs/evidence/scenario_registry.json`), and is run by a generic engine on the verified canonical tables; no canonical table, threshold or configuration value is modified. 26 scenarios are registered: the 25 approved Phase 2 scenarios (every one reproduced) and one forbidden guardrail (G01). M5 and S2 are computed only where a scenario varies eligibility or quarantine, always over the fixed denominator of 1,699; an analytic exclusion does not redefine readiness.

**Robustness classes** (one rule set for every metric and scenario; |change| against the frozen baseline):

| Metric | STABLE below | SENSITIVE below | CONDITIONAL at or above | Basis |
|---|---:|---:|---:|---|
| M1 | 10 g | 20 g | 20 g | Phase 2 materiality convention |dM1| >= 10 g; sensitive band = 2x |
| M2 | 25 g | 75 g | 75 g | Phase 2 materiality convention |dM2| >= 25 g; sensitive band = 3x |
| M3 | 5% | 20% | 20% | 5% and 20% of the 1,697 baseline sessions |
| M4 | 0.5 components | 1.5 components | 1.5 components | Phase 2 convention: any change in M4 is material; one component is sensitive |
| M5 | 0.5 percentage points | 5 percentage points | 5 percentage points | readiness moved by half a point is stable; five points is the sensitive limit |
| S2 | 0.5 percentage points | 5 percentage points | 5 percentage points | as M5 |

BLOCKED means no defensible conclusion can be produced because the required evidence is unavailable. A scenario that is a diagnostic population contrast (S40) or a forbidden comparison (G01) is reported but never classified or ranged.

## 3. Scenario table

Deltas are against the baseline. `class` is the worst class over the metrics the scenario recomputes. **M3 falls by construction when sessions are excluded**, so for an exclusion scenario the class can reflect the session-count effect alone (S23 is CONDITIONAL because it leaves out 385 sessions, while its effect on M2 is SENSITIVE); the conclusion classes in sections 5-8 therefore use M1, M2 and M4 for exclusion tests and use M3 and M5 only for the timezone and crossover scenarios. `ref` = Phase 2 reference reproduced.

| ID | Scenario | Group | M1 g | M2 g | M3 | M4 | M5 % | S2 % | ΔM1 | ΔM2 | class | ref |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| S00 | Approved baseline | baseline | 499.0 | 1,039.6 | 1,697 | 5 | 99.88 | 97.88 | +0.0 | +0.0 | stable | yes |
| S01 | Crossover sessions included (both) | crossover | 499.0 | 1,042.4 | 1,699 | 5 | 100.00 | 97.94 | +0.0 | +2.8 | stable | yes |
| S02 | Only session2266 included | crossover | 499.0 | 1,039.2 | 1,698 | 5 | 99.94 | 97.94 | +0.0 | -0.4 | stable | yes |
| S03 | Only session3222 included | crossover | 499.5 | 1,042.6 | 1,698 | 5 | 99.94 | 97.88 | +0.5 | +3.0 | stable | yes |
| S04 | 2,097 g session removed | outlier | 499.0 | 1,038.0 | 1,696 | 5 | n/a | n/a | +0.0 | -1.6 | stable | yes |
| S05 | 2,097 g event removed (session kept) | outlier | 499.0 | 1,038.0 | 1,697 | 5 | n/a | n/a | +0.0 | -1.6 | stable | yes |
| S06 | Exclude outside data percentiles P0.5-P99.5 | outlier | 499.0 | 1,017.0 | 1,679 | 5 | n/a | n/a | +0.0 | -22.6 | stable | yes |
| S07 | Exclude outside the approved B07 range | outlier | 499.0 | 1,020.5 | 1,682 | 5 | n/a | n/a | +0.0 | -19.1 | stable | yes |
| S08 | Exclude single-event sessions (B04) | outlier | 501.0 | 1,044.2 | 1,680 | 5 | n/a | n/a | +2.0 | +4.6 | stable | yes |
| S09 | Exclude long sessions (T05) | outlier | 498.0 | 1,037.1 | 1,690 | 5 | n/a | n/a | -1.0 | -2.5 | stable | yes |
| S10 | Exclude every session with any WARN | outlier | 499.5 | 1,015.0 | 1,660 | 5 | n/a | n/a | +0.5 | -24.6 | stable | yes |
| TZ0 | Suspect export shifted by +0h | timezone | 505.0 | 989.1 | 1,394 | 5 | 82.05 | 80.28 | +6.0 | -50.5 | conditional | yes |
| TZ1 | Suspect export shifted by +1h | timezone | 498.5 | 1,019.5 | 1,594 | 5 | 93.82 | 91.88 | -0.5 | -20.1 | conditional | yes |
| TZ2 | Suspect export shifted by +2h | timezone | 499.0 | 1,039.6 | 1,697 | 5 | 99.88 | 97.88 | +0.0 | +0.0 | stable | yes |
| TZ3 | Suspect export shifted by +3h | timezone | 499.0 | 1,039.6 | 1,697 | 5 | 99.88 | 97.88 | +0.0 | +0.0 | stable | yes |
| TZ4 | Suspect export shifted by +4h | timezone | 499.0 | 1,039.6 | 1,697 | 5 | 99.88 | 97.88 | +0.0 | +0.0 | stable | yes |
| S20 | Exclude the six volume-irregularity days | volume | 505.0 | 1,066.0 | 1,445 | 5 | n/a | n/a | +6.0 | +26.4 | sensitive | yes |
| S21 | Exclude 2020-11-16 to 2020-11-20 | volume | 499.5 | 1,052.1 | 1,530 | 5 | n/a | n/a | +0.5 | +12.5 | sensitive | yes |
| S22 | Exclude the 16 low-observed-volume days | volume | 493.0 | 1,053.0 | 1,507 | 5 | n/a | n/a | -6.0 | +13.4 | sensitive | yes |
| S23 | Period sensitivity: exclude the first two weeks | period | 505.0 | 977.0 | 1,312 | 5 | n/a | n/a | +6.0 | -62.6 | conditional | yes |
| S30 | M4 with raw component names | definition | 499.0 | 1,039.6 | 1,697 | 5 | n/a | n/a | +0.0 | +0.0 | stable | yes |
| S31 | M4 counted as distinct scales | definition | 499.0 | 1,039.6 | 1,697 | 5 | n/a | n/a | +0.0 | +0.0 | stable | yes |
| S32 | M4 counted as weighing events | definition | 499.0 | 1,039.6 | 1,697 | 5 | n/a | n/a | +0.0 | +0.0 | stable | yes |
| S33 | Exact duplicate rows summed | definition | 499.0 | 1,039.6 | 1,697 | 5 | n/a | n/a | +0.0 | +0.0 | stable | yes |
| S40 | DIAGNOSTIC: non-registered-export population | population | 192.0 | 855.4 | 1,644 | 2 | n/a | n/a | -307.0 | -184.2 | not classified | yes |
| G01 | FORBIDDEN COMPARISON: pooled registered and non-registered sessions | guardrail | 413.0 | 950.0 | 3,341 | 4 | n/a | n/a | -86.0 | -89.6 | not classified | new |

G01 is a **forbidden comparison** used only to demonstrate population-confounding risk: pooling the two exports gives M1 413.0 g, M2 950.0 g and M4 4, numbers that describe the population mix and not any measurement. The populations are never pooled. S40 shows the non-registered-export population on its own (a diagnostic contrast, never a KPI source).

## 4. Headline metric ranges

Ranges are over the registered-export scenarios (the diagnostic population contrast and the forbidden guardrail are excluded). "Reasonable" scenarios are those declared defensible.

| Metric | Baseline | Range, all scenarios | Range, defensible only | Largest absolute change | Largest relative change |
|---|---:|---|---|---|---|
| M1 | 499.0 g | 493.0 to 505.0 | 493.0 to 505.0 | TZ0 (+6.0) | TZ0 (+1.2%) |
| M2 | 1,039.6 g | 977.0 to 1,066.0 | 977.0 to 1,066.0 | S23 (-62.6) | S23 (-6.0%) |
| M3 | 1,697 sessions | 1,312 to 1,699 | 1,312 to 1,697 | S23 (-385) | S23 (-22.7%) |
| M4 | 5.0 components | 5.0 to 5.0 | 5.0 to 5.0 | TZ4 (+0.0) | TZ4 (+0.0%) |
| M5 | 99.88 % | 82.05 to 100.00 | 99.88 to 99.88 | TZ0 (-17.83) | TZ0 (-17.9%) |
| S2 | 97.88 % | 80.28 to 97.94 | 97.88 to 97.88 | TZ0 (-17.60) | TZ0 (-18.0%) |

M3 changes by construction when sessions are excluded, so its range is reported but the conclusion about the session count rests on the timezone and crossover scenarios only (question Q5).

### Timezone hypotheses for the suspect export (385 sessions; only that file is shifted)

| Offset | Sessions outside service hours (T03) | Median first-event hour | Gap to the other registered-export files | Weather hour changed | Mean abs. temperature difference | Rainy-hour share |
|---|---:|---:|---:|---:|---:|---:|
| +0h | 303 | 7.54 h | 2.99 h | 385 | 1.231 C | 15.1% |
| +1h | 103 | 8.54 h | 1.99 h | 385 | 0.873 C | 27.5% |
| +2h | 0 | 9.54 h | 0.99 h | 385 | 0.529 C | 36.6% |
| +3h (baseline) | 0 | 10.54 h | 0.01 h | 0 | 0.000 C | 21.3% |
| +4h | 0 | 11.54 h | 1.01 h | 385 | 0.467 C | 11.7% |

**Why the baseline remains +3h.** M1-M4 are identical under +2h, +3h and +4h, so the KPIs cannot choose. The choice rests on cross-export evidence that was gathered before this comparison: an exact 10,800 s difference for `session3222` and a median first-event hour of the shifted file that falls inside the band of the other registered-export files only at +3h (10.54 h against 10.53 h). +0h and +1h are contradicted by the service-hours rule and by the time of day, and would lower M5 to 82.05% and 93.82%. The timezone metadata remains unconfirmed by the source, so time-of-day and weather-join outputs stay conditional.

## 5. Stable conclusions

The conclusion is materially unchanged across the reasonable scenarios (every change is below the STABLE band).

- **Can a selected-meal-weight distribution be reconstructed from the available component weighing events?** (controls: 3,341 of 3,341 weights reconstructed and matched). A distribution of DERIVED selected meal weight (the sum of what was weighed at the line per session) can be reconstructed for the registered-export population. *Cannot conclude:* That the distribution describes what was eaten or wasted.
- **Is the median derived selected meal weight of the same order of magnitude under reasonable scenarios?** (worst over 20 metric-scenario cells). Median derived selected meal weight is about 500 g under every registered-export scenario tested. *Cannot conclude:* That the median is a portion size that was eaten.
- **Does the component-count result remain stable?** (worst over 23 metric-scenario cells). The typical session records five distinct component names, however breadth is counted. *Cannot conclude:* Which dishes were chosen, or that different names are different dishes.
- **Does the treatment of the two crossover sessions change any conclusion?** (worst over 9 metric-scenario cells). No conclusion changes: the largest effect is about 3 g on M2. *Cannot conclude:* That either version is correct. M5 rising to 100% is an artifact of lifting the quarantine.
- **Is the 2,097 g observation influential?** (worst over 6 metric-scenario cells). It is an unusual observation, not an invalid one, and it moves M2 by about 1.6 g. *Cannot conclude:* Whether the value is a scale artifact or a real portion.
- **Should the warn-free rate be read as a second readiness score?** (worst over 2 metric-scenario cells). No: a WARN is a diagnostic flag that never removes a session; excluding flagged sessions moves M2 by about -25 g. *Cannot conclude:* That flagged sessions are wrong or that S2 measures accuracy.

## 6. Sensitive conclusions

The magnitude changes materially with an assumption, but the interpretation may remain.

- **How stable is the upper end of the distribution (P90)?** (worst over 20 metric-scenario cells (driven by M2 in S23)). P90 stays near 1,000-1,070 g, but moves by up to about 60 g (6%) with the study period and with the timezone hypothesis. *Cannot conclude:* A precise P90: it should be quoted with its range and its dependence on the period.
- **Do the six irregular-volume days change the measurement profile?** (worst over 9 metric-scenario cells (driven by M2 in S20)). M1 and M4 are unchanged in practice; M2 moves by up to about 26 g when those days are left out. *Cannot conclude:* That the irregular days are errors, or what caused them. Volume flags never exclude.
- **Does the study period matter (the first two weeks)?** (worst over 3 metric-scenario cells (driven by M2 in S23)). M1 and M4 do not depend on the period; M2 is period sensitive (about -63 g). *Cannot conclude:* That the first two weeks are bad data.

## 7. Conditional conclusions

The conclusion depends strongly on an unresolved assumption.

- **Is the registered-export valid-session count and readiness stable to the timezone and crossover assumptions?** (worst over 16 metric-scenario cells (driven by M5 in TZ0)). Under +2h, +3h and +4h the count and readiness are identical; the count and M5 fall sharply only if the file is treated as un-shifted or shifted by 1 h, which the evidence contradicts. *Cannot conclude:* That readiness is high for a reason other than the few ERROR-level findings; lifting the quarantine (100%) is not a valid readiness figure.
- **Which timezone does the suspect export use, and do the KPIs decide it?** (depends on an unresolved, evidence-backed assumption). The KPIs cannot separate +2h, +3h and +4h; the time-of-day evidence places only +3h inside the band of the other exports. Weather-hour joins depend on the choice. *Cannot conclude:* That +3h is confirmed by the source, or that it is a general Helsinki rule.

## 8. Blocked conclusions

No defensible conclusion can be produced: the required evidence is unavailable. A sensitivity analysis cannot turn missing source data into observed evidence, and no waste estimate, band or proxy is produced.

- **Can actual consumption be determined from selected meal weight alone?** (required evidence is unavailable). Nothing about consumption. *Cannot conclude:* Any amount consumed, left over or eaten.
- **Can food waste be measured from the accessible data?** (required source is not public). That waste is not measurable from the accessible data. *Cannot conclude:* Any waste amount, potential waste, waste band or ratio.

## 9. Uncertainty register summary

Full register: `outputs/evidence/uncertainty_register.csv`.

| ID | Assumption | Impact | Disposition | Sensitivity result |
|---|---|---|---|---|
| U01 | Suspect export timezone: the file's timestamps are 3 hours early (a +3h, file-specific normalization). | HIGH | Retained as +3h, file-specific; labelled NORMALISED_PLUS_3H_STRONGEST_SUPPORT | +2h/+3h/+4h give identical M1-M5; +0h quarantines 303 sessions (M5 82.05%); +1h quarantines 103 (M5 93.82%). |
| U02 | Population labels (registered-export / non-registered-export) come from file names and mean only that. | HIGH | Never pooled; the registered-export population is the measurement population | The diagnostic non-registered-export profile is M1 192 g, M2 855.4 g, M4 2; the forbidden pooled comparison gives M1 413 g (a population-mix artifact). |
| U03 | Crossover sessions: two session ids present in both exports are quarantined rather than resolved. | LOW | Quarantined in both populations; listed; never deleted | Including both changes M2 by +2.8 g and M5 to 100.0% only because the check is removed. |
| U04 | Component identity is the trimmed, whitespace-collapsed, case-folded name; there is no alias table. | LOW | String normalization only; component comparison across exports is limited | M4 is 5 with raw names, 5 counting scales and 5 counting weighing events. |
| U05 | Six days whose observed volume regime differs from the weekday baseline are real observations. | MEDIUM | Flag only; retained; M3 is not demand | Excluding them removes 252 sessions and moves M2 by +26.4 g (+2.5%), M1 by +6 g. |
| U06 | Derived selected meal weight is what was weighed at the line, not what was eaten. | BLOCKING | UNKNOWN in the semantic chain; no consumed column exists | Not testable: no scenario can produce consumption from selection. |
| U07 | Direct food-waste measurement is unavailable. | BLOCKING | BLOCKED / SOURCE GAP | Not testable: no lower or upper waste bound, band or proxy is produced. |
| U08 | The Turku weather station is a regional context, and r_1h is the hour ending at its timestamp. | LOW | Context only; no causal claim | Under the timezone hypotheses, all 385 sessions in the shifted file join a different weather hour (mean temperature difference 1.231 C for +0h). |
| U09 | Five weeks of data represent the measurement profile. | MEDIUM | Full window kept; M2 quoted with its range | Excluding them moves M2 by -62.6 g (-6.0%); M1 by +6 g. |
| U10 | The diagnostic thresholds (B02, B07, T05, C02) describe this data and are not physical limits. | LOW | Flags only | Applying B07 as an exclusion moves M2 by -19.1 g; any WARN as an exclusion by -24.6 g. |

## 10. Evidence gaps

What remains uncertain after testing, and what would resolve it:

- The source owner's confirmation of the export timezone.
- The data owner's definition of the two exports.
- Which version is authoritative.
- A component master list.
- Operational records for those dates.
- A per-tray measurement of the remaining food.
- Per-tray waste records joinable on tray_id.
- On-site sensors or a documented FMI convention.
- More weeks.
- Physical limits from the scale vendor.

## 11. Recommended next instrumentation and data

1. **Per-tray waste and remaining-food measurement, linked by tray id** (the documented but inaccessible waste system): the only way to move W1 and any consumption question out of BLOCKED.
2. **The source owner's confirmation of the export timezone**: it would turn the +3h file-specific decision from evidence-backed to confirmed and settle the weather join.
3. **Operational records** (menu, closures, events) for the six irregular days, and more weeks of data, to explain the volume regime and to test the period dependence of P90.
4. **A component master list** to replace string matching for component identity across exports.
5. **Scale calibration or tray photographs** for the largest observations, to separate unusual from invalid.

<!-- END GENERATED -->
