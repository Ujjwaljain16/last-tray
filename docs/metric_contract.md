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

`derived_selected_meal_weight_g` = `SUM(component_weight_g)` over the session's events with `is_exact_duplicate = 0`; NULL if any event weight is invalid. It is DERIVED and never labelled observed.

**Never used in any metric filter:** `weather_matched`, `low_observed_volume_day`, `volume_irregularity`, `has_session_warn` (except in S2), `has_event_warn`, `distinct_component_count_status`, `quality_status`. Invariant I-6: volume flags appear in no WHERE clause of any metric query.

## 3. Lineage: how any number is traced to raw rows

```sql
-- 1. which sessions produced a value (example: M1's population)
SELECT session_id, population, derived_selected_meal_weight_g
FROM fact_dining_session WHERE core_ready = 1;

-- 2. which weighing events produced one session's derived weight
SELECT event_id, scale_id, component_name_raw, component_weight_g, is_exact_duplicate
FROM fact_weighing_event
WHERE session_id = :sid AND population = :pop
ORDER BY event_time_local;          -- event_id = 'source_file#source_row_number': the raw row

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

`outputs/validation/sensitivity_analysis.csv`: 25 scenarios. The baseline row (S00) must equal the rows above. Scenarios S20-S22 (volume) are **analysis only**: they measure the effect of excluding days that the pipeline never excludes. The timezone is **not** selected by the KPIs: TZ2, TZ3 and TZ4 are identical on every KPI, so cross-export evidence, not KPI sensitivity, selects +3h.
