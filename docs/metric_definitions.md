# Metric Definitions (final formulas)

Every metric states: what it means, its grain, who is in and who is out, the source, the validation it depends on, and what it cannot claim. Baseline values come from the exploration run; the pipeline must reproduce them. Sensitivity ranges are from `outputs/validation/sensitivity_analysis.csv`.

**Canonical session** = a `fact_dining_session` row with `core_ready = 1`: registered-export population, at least one valid event, no ERROR-level violation, no identity conflict. Population labels are inherited from source filenames and are not interpreted.

## Core metrics

### M1. Median Derived Selected Meal Weight
| | |
|---|---|
| Purpose | What a typical tray held at the lunch line, in grams |
| Formula | `MEDIAN(derived_selected_meal_weight_g)` |
| Population / grain | canonical sessions / one session |
| Source | FlavoriaFoodWeight1700, derived by summing component weighing events |
| Filters | `core_ready = 1` |
| Exclusions | crossover sessions (quarantined); exact-duplicate rows (excluded from sums); non-registered-export population |
| Never excluded | WARN-flagged sessions, volume-irregularity days, single-event sessions, the 2,097 g event |
| Validation required | S05-S07, B01, T01, T03, I01, I04, C04 pass for the session |
| Baseline | **499 g** (n = 1,697) |
| Sensitivity | 493-505 g across all scenarios; crossover inclusion +0.0 g |
| Status | `READY_WITH_LIMITATION` |
| Limitation | DERIVED; not an observed meal weight; not consumption; one population |

### M2. P90 Derived Selected Meal Weight
| | |
|---|---|
| Purpose | How heavy a large selection is |
| Formula | `PERCENTILE_LINEAR(derived_selected_meal_weight_g, 0.90)` (linear interpolation, as pandas `quantile(0.9)`) |
| Population / grain / filters / exclusions | as M1 |
| Baseline | **1,039.6 g** |
| Sensitivity | 977-1,066 g. Largest effects: excluding 2020-10-05..16 (-62.6 g), no-shift timezone hypothesis (-50.5 g, by quarantining 303 sessions), excluding irregular days (+26.4 g). Crossover inclusion +2.8 g; 2,097 g session removal -1.6 g |
| Status | `READY_WITH_LIMITATION` |
| Limitation | the most period-sensitive metric; describes five weeks |

### M3. Observed Valid Sessions — Registered-Export Population
| | |
|---|---|
| Purpose | How many sessions the registered-export population contributes to the KPIs, in total and per service date |
| Formula | `COUNT(*)` of canonical sessions; per date: `COUNT(*) GROUP BY service_date` |
| Population / grain | canonical sessions / one session |
| Baseline | **1,697** |
| Status | `READY_WITH_LIMITATION` |
| Limitation | **Not demand, diners, customers or traffic.** Registered-export daily volume follows a weekday pattern the other export lacks (Mon-Wed 41-107, Thu-Fri 2-18 in the baseline weeks) and six days break it. Volume flags describe days and never change this count |

### M4. Median Distinct Normalized Components per Session
| | |
|---|---|
| Purpose | How broad a selection is |
| Formula | `MEDIAN(distinct_component_count)`, where `distinct_component_count = COUNT(DISTINCT component_id_normalized)` within the session |
| Population / grain / filters | as M1 |
| Normalisation | trim, collapse whitespace, case-fold. **No alias table** |
| Baseline | **5** |
| Sensitivity | 5 under raw names, distinct scales and event counts (S30-S32) and in every scenario |
| Diagnostic kept | `component_weighing_event_count` |
| Status | `READY_WITH_LIMITATION` (`distinct_component_count_status = LIMITED` for component identity across exports in 2020-10-05..16) |
| Limitation | counts names within a session; cross-export or cross-day component comparison is not offered for the window where the exports disagree |

### M5. Core Measurement Readiness
| | |
|---|---|
| Purpose | What share of the registered-export sessions in the source can be reconstructed and used |
| Formula | `COUNT(core_ready = 1) / COUNT(registered-export session IDs in the source)` |
| **Denominator** | **1,699, every registered-export session ID in the source, fixed before any record is removed or quarantined.** Never recomputed after removal |
| Numerator | canonical sessions (same set as M3) |
| Baseline | **1,697 / 1,699 = 99.88%** |
| Sensitivity | unquarantining the two crossover sessions gives 100% and is not a valid readiness figure; the no-shift timezone hypothesis gives 82.05% (T03 quarantine); +1h gives 93.82%; +2h to +4h unchanged |
| Status | `READY_WITH_LIMITATION` |
| Limitation | high because the registered export has few ERROR-level violations, not because it is proven error-free. Weather, precipitation NULLs, volume flags and WARN rules never enter it |

## Supporting metrics (not core KPIs)

### S1. Weather Context Coverage
`sessions with weather_matched = 1 / 1,699` (same fixed eligible denominator). The profiling dry run: all 1,697 canonical sessions matched; the two quarantined sessions stay in the denominator and are joined by the pipeline like any other (both fall inside the covered window, so 1,699 / 1,699 is expected). Context only; never affects M1-M5. Precipitation NULL count reported separately (67 sessions `r_1h`, 25 `ri_10min`).

### S2. Warn-free Rate
`eligible registered-export sessions with no session-level WARN / 1,699` (fixed denominator). Session-level WARN rules: B04, B07, T04, T05, I06. Baseline **1,663 / 1,699 = 97.88%**. File-level (T07) and day-level (C02) flags are excluded by design.

**Reconciliation to the event-level variant** (diagnostic, does not replace the figure above): 1,699 eligible = 1,663 with no session-level WARN + 34 with a session-level WARN + 2 quarantined crossover sessions. Three of the 1,663 carry an event-level WARN only (`session320`, `session1116`: B02; `session1274`: I02), so the variant is 1,660 / 1,699 = 97.70%. Full reconciliation: `metric_contract.md`, D28.

### S3. Portion spread
`P90 − P10` of `derived_selected_meal_weight_g` (canonical sessions). Baseline 1,039.6 − 314 = 725.6 g. Optional context.

### S4. Population diagnostics
Non-registered-export population profile, labelled DIAGNOSTIC: 1,644 sessions, median derived weight 192 g, 37.7% single-event sessions. Never a KPI source.

## Blocked metric

### W1. Plate waste per session / waste-to-selected ratio
`BLOCKED / SOURCE GAP`, permanently, unless an actual public raw waste dataset is found. Evidence row: value NULL, required source "Flavoria Lunch Line Waste, keyed on tray", limitation "no public waste data; selected weight is not waste". There is no formula, no estimate and no proxy.

## Evidence-table row shape

`metric, value, population, definition, source, records_used, records_excluded, evidence_status, limitation`. `records_excluded` for M1-M5 is the count removed relative to the fixed eligible population (2, the crossover sessions), so the reader can see the denominator was not shrunk quietly.

## Diagnostic fields (not headline)

`component_weighing_event_count`, `session_span_s`, same-scale-repeat rate (222 sessions), `low_observed_volume_day` (16 of 35 days), `volume_irregularity` (6 days), the 2,097 g event, exact-duplicate rows (2), crossover sessions (2), weather-unmatched count, precipitation NULL counts.
