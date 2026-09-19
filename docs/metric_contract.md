# Metric Contract

`metric_definitions.md` explains what each metric means. **This document is the contract the code must satisfy**: the exact expression over the canonical tables, the population, the denominator, the lineage, the validation each metric depends on, and the golden value the test suite asserts (`tests/golden/golden_values.yml`). If code and this contract disagree, the code is wrong until a decision-log entry says otherwise.

Population labels (`registered_export`, `non_registered_export`) are inherited from source filenames and are not interpreted. Thresholds are diagnostic, not physical.

## 1. Vocabulary

| Term | Meaning |
|---|---|
| **eligible sessions** | every `fact_dining_session` row with `population = 'registered_export'`, counted **before** any quarantine or removal. Baseline **1,699** |
| **canonical session** | eligible session with `core_ready = 1`. Baseline **1,697** |
| **core_ready** | primary population, no ERROR-level violation, no identity conflict. Weather, WARN/INFO rules and volume flags never enter it |
| **lineage** | metric → table → field → filter → session key → `fact_weighing_event.event_id` → raw `source_file#row` |

## 2. Contract

| ID | Expression (SQLite over the canonical tables) | Population | Denominator | Golden |
|---|---|---|---|---|
| **M1** | `MEDIAN(derived_selected_meal_weight_g)` over `fact_dining_session WHERE core_ready = 1` | canonical | n/a | **499.0** |
| **M2** | linear-interpolation 90th percentile of the same column and filter (pandas `quantile(0.9)`) | canonical | n/a | **1039.6** (±0.05) |
| **M3** | `SELECT COUNT(*) FROM fact_dining_session WHERE core_ready = 1`; per date `... GROUP BY service_date` | canonical | n/a | **1697** |
| **M4** | `MEDIAN(distinct_component_count)` over `WHERE core_ready = 1` | canonical | n/a | **5** |
| **M5** | `SUM(core_ready) * 1.0 / COUNT(*)` over `WHERE population = 'registered_export'` | eligible | **1699, fixed before removal** | **1697 / 1699 = 99.88%** |
| **S1** | `SUM(weather_matched) * 1.0 / COUNT(*)` over `WHERE population = 'registered_export'` | eligible | 1699 | dry run: 1697 canonical sessions matched |
| **S2 (canonical)** | `SUM(has_session_warn = 0 AND core_ready = 1) * 1.0 / COUNT(*)` over `WHERE population = 'registered_export'` | eligible | 1699 | **1663 / 1699 = 97.88%** |
| **W1** | none. Evidence row only | n/a | n/a | `BLOCKED / SOURCE GAP`, value NULL |

`derived_selected_meal_weight_g` = `SUM(component_weight_g)` over the session's MODELLABLE events (`disposition = 'MODELLABLE'`: not an exact repeat and not quarantined); NULL if there is none or any weight is invalid. It is DERIVED, never labelled observed, and is NOT consumed quantity, food waste or actual intake. Validation's `rule_weight_sum_g` is a validation working value used only as a reconciliation control (D50).

**Never used in any metric filter:** `weather_matched`, `low_observed_volume_day`, `volume_irregularity`, `has_session_warn` (except in S2), `has_event_warn`, `distinct_component_count_status`, `quality_status`. Invariant I-6: volume flags appear in no WHERE clause of any metric query.

## 3. Lineage: how any number is traced to raw rows

```sql
-- 1. which sessions produced a value (example: M1's population)
SELECT session_id, population, derived_selected_meal_weight_g
FROM fact_dining_session WHERE core_ready = 1;

-- 2. which weighing events produced one session's derived weight
SELECT event_id, scale_id, component_name_raw, component_weight_g, disposition
FROM fact_weighing_event
WHERE session_key = :session_key       -- 'session_id|population'
ORDER BY event_time_utc;          -- event_id = 'source_file#source_row_number': the raw row

-- 3. the invariant that ties them (I-10): the two must agree
SELECT s.session_id
FROM fact_dining_session s
JOIN (SELECT session_id, population, SUM(component_weight_g) AS w
      FROM fact_weighing_event WHERE is_exact_duplicate = 0 GROUP BY 1, 2) e USING (session_id, population)
WHERE s.derived_selected_meal_weight_g <> e.w;      -- must return no rows
```

## 4. Validation each metric depends on

| Metric | Must pass for a session to count | Never removes a session |
|---|---|---|
| M1, M2, M3, M4, M5 | S05, S06, S07, B01, T01, T03, I01, I04, C04 | every WARN and INFO rule (B02, B03, B04, B05, B07, T04, T05, T07, I02, I06, C02a, C02b) |
| S1 | none (context) | everything |
| S2 | none for the denominator; numerator requires `core_ready = 1` and no session-level WARN | n/a |

## 5. Warn-free rate: canonical figure and explicit reconciliation

**Canonical (S2):** eligible registered-export sessions with **no session-level WARN** (B04, B07, T04, T05, I06), over the fixed eligible denominator.

| Item | Value |
|---|---:|
| Population | registered-export |
| Denominator (fixed before removal) | **1,699** |
| Quarantined crossover sessions (I01, ERROR) | 2 |
| Sessions with a session-level WARN | 34 |
| **Sessions with no session-level WARN (numerator)** | **1,663** |
| Check: 1,663 + 34 + 2 | 1,699 |
| **Canonical warn-free rate** | **1,663 / 1,699 = 97.88%** |

**Diagnostic variant (not a replacement):** also counting event-level WARNs (B02, I02).

| Item | Value |
|---|---:|
| Sessions with an event-level WARN and **no** session-level WARN | 3 (`session320`, `session1116`: B02; `session1274`: I02) |
| Numerator | 1,663 − 3 = 1,660 |
| Rate | 1,660 / 1,699 = 97.70% |

**Reason for the difference:** B02 (an event at or above 1,500 g) and I02 (an exact duplicate row) attach to events, not sessions; the canonical definition counts session-level rules only. The choice of which WARN rules belong in "warn-free" is a definition; the canonical one was approved and the variant is disclosed. See `decision_log.md` D28. The figure is never replaced without this reconciliation and a decision-log entry.

## 6. Evidence-row contract (`outputs/evidence/final_evidence.csv`)

`metric, value, population, definition, source, records_used, records_excluded, evidence_status, limitation`

| metric | value | population | records_used | records_excluded | evidence_status |
|---|---|---|---:|---:|---|
| M1 | 499.0 | registered-export | 1,697 | 2 | READY_WITH_LIMITATION |
| M2 | 1039.6 | registered-export | 1,697 | 2 | READY_WITH_LIMITATION |
| M3 | 1697 | registered-export | 1,697 | 2 | READY_WITH_LIMITATION |
| M4 | 5 | registered-export | 1,697 | 2 | READY_WITH_LIMITATION |
| M5 | 99.88% | registered-export (eligible) | 1,697 | 2 | READY_WITH_LIMITATION |
| S1 | to be computed | registered-export (eligible) | | | READY_WITH_LIMITATION |
| S2 | 97.88% | registered-export (eligible) | 1,663 | 36 | READY_WITH_LIMITATION |
| W1 | NULL | n/a | 0 | n/a | **BLOCKED** (required source: Flavoria Lunch Line Waste, keyed on tray) |

`records_excluded` is measured **against the fixed eligible population**, so a reader can see the denominator was not shrunk. For S2 it is 1,699 − 1,663 = 36 (34 with a session-level WARN + 2 quarantined).

## 7. Sensitivity contract

The sensitivity analysis (`outputs/evidence/`, `docs/sensitivity_analysis.md`) reproduces the 25 approved reference scenarios in `outputs/validation/sensitivity_analysis.csv` (frozen in `tests/golden/`) and adds one forbidden guardrail; the frozen baseline is never overwritten. The baseline row (S00) must equal the rows above. Scenarios S20-S22 (volume) are **analysis only**: they measure the effect of excluding days that the pipeline never excludes. The timezone is **not** selected by the KPIs: TZ2, TZ3 and TZ4 are identical on every KPI, so cross-export evidence, not KPI sensitivity, selects +3h.

## 8. Metrics implementation (metrics and evidence)

Implemented in `src/metrics/` and run by `python -m src.pipeline.run --stages metrics`. Outputs in `outputs/metrics/`: `metrics.csv`,
`metric_evidence.csv`, `metric_summary.json`, `metric_contracts.json` (each contract with its computed value, tolerance and pass/fail),
`metric_controls.csv` and `metrics_report.md`. Computation (`compute.py`), contracts (`contracts.py`) and presentation (`evaluate.py`)
are separate files. The metrics read only the canonical model tables, verified against the model manifest (D54); they never read staging or raw files.

### Populations (a metric always names one; there is no default)

| | Name | Definition | Sessions |
|---|---|---|---:|
| A | `all_observed_sessions` | every `(session_id, population)` key, whatever its status | 3,345 |
| B | `non_quarantined_modelled_sessions` | not quarantined and at least one modellable event | 3,341 |
| C | `eligible_registered_export_sessions` | every registered-export session key, counted before any quarantine (M5's fixed denominator) | 1,699 |
| D | `core_ready_registered_export_sessions` | C that meets the core readiness criteria: the approved measurement population | 1,697 |
| E | `non_registered_export_sessions` | the other export; diagnostic; never pooled with C or D | 1,646 |

M1-M4 use D. M5, S1, S2 and S2D use C as the denominator (M5's numerator is D). No headline metric uses A, B or E.

### Results

| ID | Metric | Value | Population | Numerator / denominator | Approved (tolerance) |
|---|---|---|---|---|---|
| M1 | Median Derived Selected Meal Weight | 499 g | D | n = 1,697 | 499.0 (exact) |
| M2 | P90 Derived Selected Meal Weight | 1,039.6 g | D | n = 1,697 | 1,039.6 (0.05) |
| M3 | Observed Valid Sessions — Registered-Export Population | 1,697 | D | count | 1,697 (exact) |
| M4 | Median Distinct Normalized Components per Session | 5 | D | n = 1,697 | 5 (exact) |
| M5 | Core Measurement Readiness | 99.88% | D over C | 1,697 / 1,699 | 99.88 (0.005) |
| S1 | Weather Context Coverage | 99.88% | C | 1,697 / 1,699 | 99.88 (0.005), see below |
| S2 | Warn-Free Rate | 97.88% | C | 1,663 / 1,699 | 97.88 (0.005) |
| S2D | Warn-Free Rate incl. event-level warnings (diagnostic) | 97.70% | C | 1,660 / 1,699 | 97.70 (0.005) |
| W1 | Direct Food Waste Measurement | BLOCKED / SOURCE GAP | n/a | none | no value |

**Percentile method.** M2 is linear interpolation at position `(n - 1) * 0.90` of the sorted weights: the numpy/pandas default, R type 7, and
equal to `statistics.quantiles(..., n=10, method="inclusive")[8]`, which a control checks. It is not nearest-rank.

**M5 and S2 measure different things.** M5 is a readiness ratio: core-ready over eligible, where the 2 missing sessions are the quarantined crossover
sessions. S2 additionally leaves out the 34 core-ready sessions that carry a session-level WARN (B04, B07, T04, T05, I06), which stay in every KPI
(1,663 + 34 + 2 = 1,699). S2D also counts event-level WARNs (B02, I02; three more sessions) and never replaces S2. Neither is a measure of accuracy.

**S1 and the quarantined sessions (differs from the profiling expectation).** The definition above fixes S1's denominator at 1,699 and the profiling dry run
expected all 1,699 to match, on the assumption that the pipeline would also join the two quarantined sessions. The canonical model deliberately does not
join quarantined sessions (`weather_join_status = NOT_ATTEMPTED_QUARANTINED`, D52). S1 is therefore 1,697 / 1,699 = 99.88%: the same numerator as the
the profiling dry run (1,697 core-ready sessions matched, 1,697 of 1,697), and the two "unmatched" sessions are not-attempted, not missing weather. Precipitation
NULLs at the matched hours: 67 sessions for `r_1h`, 25 for `ri_10min`.

**W1.** The Flavoria system documents lunch-line waste measurement keyed on tray; the public data reachable here has no such records. Status BLOCKED / SOURCE GAP, value
empty, no formula, no estimate, no proxy. The configuration refuses to load if the waste source is not BLOCKED, and the metric layer refuses any row that
is about waste, consumption, leftovers or intake other than the blocked W1.

**Failure policy.** A metric that misses its approved value or tolerance (or whose approved numerator or fixed denominator differs) is reported FAILED with the
exact difference, the stage exits 4, and the formula is never adjusted. Missing or altered canonical inputs BLOCK the stage and remove stale metric files.
