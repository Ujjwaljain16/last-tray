# Phase 2: Required PRD / TRD Changes

*Historical record. Later changes (M3 renamed "Observed Valid Sessions — Registered-Export Population"; warn-free rate 97.88% canonical, with 97.70% as an event-level diagnostic; PRD v3 framing as a measurement-reconstruction pipeline) are in `decision_log.md` D27-D31.*

All changes below **have been applied** to the documents named. Reasons and evidence are in `docs/decision_log.md` (D17-D26) and `docs/phase2_profile_report.md`.

## PRD (`docs/PRD.md`)

| Change | Why | Evidence |
|---|---|---|
| Metrics locked as M1 Median Derived Selected Meal Weight, M2 P90 Derived Selected Meal Weight, M3 Valid Dining Session Volume, M4 Median Distinct Normalized Components per Session, M5 Core Measurement Readiness | review decision | n/a |
| Weather Context Coverage = supporting metric S1, never core | timezone uncertainty must not invalidate weights | KPI preview: excluding the +3h file moves M1 by 6 g |
| **M3 reworded as "observed valid sessions in the registered-export population", explicitly not demand** | registered-export volume is weekday-patterned; the other export is flat | Mon-Wed 41-107, Thu-Fri 2-18; non-registered-export 36-75 |
| M4 defined within a session; `component_weighing_event_count` kept as diagnostic; no alias table; `distinct_component_count_status` | component naming disagrees across exports in one window | 86 of 213 scale-days disjoint in Oct 5-16, 0 of 469 elsewhere; M4 median 5 under every definition |
| Volume irregularity section: Nov 16-20 retained, flagged, not a data error; six flagged days, not one week | Nov 2 and Nov 6 also break the pattern; sessions on flagged days look ordinary | Phase 2 section 8 |
| Population labels: registered-export / non-registered-export, inherited from filenames, not interpreted | source does not define them | Phase 0 and 2 |
| Timezone wording: strongest-supported normalisation, never "confirmed" | evidence supports a decision, the source does not state a timezone | `docs/timezone_decision.md` |
| Warn-free rate added beside M5 | 99.88% alone would hide 34 flagged sessions | M5 1,697/1,699; warn-free 1,663/1,699 |
| Waste stays `BLOCKED / SOURCE GAP` permanently unless an actual public raw dataset is found | review decision | unchanged |

## TRD (`docs/TRD.md`)

| Change | Why | Evidence |
|---|---|---|
| Parse by header name; per-column timestamp format; **sort by parsed time, never row order** | files are out of order; one is newest-first; one mixes formats between columns | 78-464 inversions per file; 154 of 155 sessions reversed in one file |
| Weather join: **ceil** to the next full UTC hour (hour-ending), not floor | `r_1h` covers the hour ending at its timestamp | error 0.021 mm vs 0.378 mm; 1,697/1,697 matched |
| New table `fact_daily_volume` with `low_observed_volume_day`, `volume_irregularity`; days never excluded | volume flags need a home that cannot touch metrics | Phase 2 section 7 |
| Model fields locked: `component_id_normalized`, `timezone_normalization`, `quality_status`, `first_weighing_at`, `last_weighing_at`, `component_weighing_event_count`, `distinct_component_count`, `distinct_component_count_status`, `session_duration_minutes` | review decision | n/a |
| Population code values `registered_export` / `non_registered_export`; key stays `(session_id, population)` | labels inherited from filenames | 2 crossover IDs |
| Thresholds file declared: `config/thresholds.yml` with the values in `phase2_validation_findings.md` §3 | thresholds set from the distribution | Phase 2 section K |
| `core_ready` and M5 definition tightened; warn-free rate | keep weather and WARN rules out of readiness | see PRD |
| Tests added: row order, mixed timestamp formats, hour-ending weather join, volume flags never exclude, M4 within-session | each Phase 2 finding becomes a regression test | n/a |
| Risks table updated (`r_1h` resolved empirically; label semantics; volume regime; component identity) | | |

## Other documents changed

`validation_rules.md` (rewritten with final thresholds and observed counts; B06 retired; S08, T09, I07, C02a/b added), `data_dictionary.md` (fields, population codes, dotted identification times, `fact_daily_volume`), `source_of_truth.md`, `assumptions_limitations.md` (K8-K15, A1-A8, Q1-Q13), `population_decision.md`, `timezone_decision.md`, `decision_log.md`.

## Not changed

Semantic layers (OBSERVED individual component weighing event; DERIVED total selected meal weight; UNKNOWN consumed quantity; SOURCE GAP actual waste quantity), the four evidence statuses, the source-of-truth answers on waste, the pipeline stage list and failure classes. Diagrams: `data-model.png` gained `fact_daily_volume`; the others contain no population wording and are unchanged.

## Items needing your decision before implementation

1. **Approve the proposed thresholds** in `docs/phase2_validation_findings.md` §3, especially B07 [50, 2,200] g and the C02 regime rule (a 4-week baseline hypothesis).
2. **M5 headline.** Confirm `core_ready` = no ERROR (99.88%) as the KPI, with the warn-free rate (97.88%) as a supporting metric, rather than making the warn-free rate the KPI.
3. **Crossover sessions.** Confirm both stay quarantined (effect if included: M1 +0.0 g, M2 +2.8 g).
