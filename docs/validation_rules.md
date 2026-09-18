# Validation Specification (final)

Rules come from business meaning: *can this record honestly support a statement about what a diner selected?* No rule deletes data. Handling: **FLAG** (kept, counted), **QUARANTINE** (kept in the model, excluded from primary metrics, listed), **BLOCK** (stop the affected stage).

Severity: **ERROR** breaks `core_ready`. **WARN** is kept and visible. **INFO** records a fact.

"Observed" counts come from `outputs/validation/validation_issues.csv` (Phase 2 exploration run). Rationale for every threshold: `docs/phase2_validation_findings.md` section 3. Thresholds are declared in `config/thresholds.yml` when the pipeline is built. **Status: approved 2026-09-19.**

> **These are diagnostic validation thresholds derived from the observed structure of this data. They are not claims of physical impossibility or universal abnormality.** A flagged record is not evidence of error, and a WARN or INFO flag never removes a record from the KPI population. Only ERROR-level rules do.

Populations use the labels inherited from source filenames: **registered-export population** (primary) and **non-registered-export population** (diagnostic). Rules that only make sense for the primary population say so.

## STRUCTURAL

| Rule | Description | Severity | Check | Expected | Violation handling | Business consequence | Observed |
|---|---|---|---|---|---|---|---|
| S01 | Source integrity (ingestion) | ERROR | archive exists; size, MD5 (as published by Zenodo) and SHA-256 equal the pins; archive readable; member set equals the pinned set; per-member size, SHA-256 and row count equal the pins; no unsafe member names | 1,277,440 bytes; 11 members; 12,284 rows | BLOCK (core lane FAILED); raw file untouched; **pins never updated, nothing re-downloaded** | No trustworthy input | pass |
| S02 | Required columns present (by **name**, not position) | ERROR | header contains {session_id, weighing_event_time, scale_identifier, weight_of_a_component, component_name, tray_id, user_identification_time} | all 7 | BLOCK that file | Cannot reconstruct a session | pass 11/11 |
| S03 | Optional column `weighting_type` | INFO | column absent | may be absent | FLAG; NULL | None: only value ever seen is `line` | 7 of 11 files lack it (6,990 rows) |
| S04 | Trailing blank columns are empty | WARN | any non-empty value in unnamed columns | empty | FLAG; keep value in staging | Hidden data would be lost | pass, 0 non-empty |
| S05 | Required values non-empty | ERROR | empty `session_id`/`tray_id`/`scale_identifier`/`component_name` | none | QUARANTINE | Event cannot be attributed | 0 |
| S06 | Weight is a numeric integer | ERROR | cast to int | numeric | QUARANTINE event; session weight NULL | Derived weight would be wrong | 0 |
| S07 | Timestamps parse in a known format | ERROR | dash or dot, per column | parses | QUARANTINE | Cannot place the event in time | 0 failures |
| S08 | Unexpected columns | WARN | header has a name outside the known set | none | FLAG; BLOCK if a required column is renamed | Schema drift | none |

## BUSINESS

| Rule | Description | Severity | Check | Expected | Violation handling | Business consequence | Observed |
|---|---|---|---|---|---|---|---|
| B01 | Weight positive | ERROR | `weight_g > 0` | > 0 | QUARANTINE | Physically meaningless | 0 |
| B02 | Large event weight | WARN | **`weight_g >= 1,500`** | rare | FLAG; kept in sums | May be a tray/plate artefact or a genuine bulk portion | 6 (3 + 3); max 2,097 g |
| B03 | Trace weight | INFO | **`weight_g <= 3`** | rare | FLAG; kept | Scale noise or garnish | 99 registered-export, 413 non-registered-export |
| B04 | Single-event session (registered-export only) | WARN | `component_weighing_event_count = 1` | rare | FLAG; kept | Single-item lunch or partial capture | 17 |
| B05 | Same scale weighed repeatedly in a session | INFO | duplicate `(session, scale)` | usually once | FLAG; summed | Repeats are additive scoops (100% same name, 93.8% within 30 s) | 222 sessions (212 + 10) |
| B07 | Derived session weight range | WARN | **outside [50, 2,200] g** | inside | FLAG; kept | Extreme trays influence P90 | registered-export 15 (7 low, 8 high); non-registered-export 470 |

(B06, "re-weigh within 30 s", is **retired**: Phase 2 showed repeats are additive scoops, so B05 covers it.)

## TEMPORAL

| Rule | Description | Severity | Check | Expected | Violation handling | Business consequence | Observed |
|---|---|---|---|---|---|---|---|
| T01 | Event inside study window | ERROR | 2020-10-05 <= date <= 2020-11-20 | inside | QUARANTINE | Out of scope | 0 |
| T02 | Event on a weekday | WARN | Mon-Fri | weekday | FLAG | Ghost event | 0 weekend events; 35 of 35 weekdays present |
| T03 | Event inside service hours (local, after the timezone rule) | ERROR | **09:00 <= hour < 15:00** | 10:13-14:43 observed | QUARANTINE | Clock problem | 0 (1,925 would fail without the +3h rule) |
| T04 | Identification after last weighing | WARN | `identified_at >= last_weighing_at` | true | FLAG; kept | Tray was identified and then returned to the line | 3 (2 + 1) |
| T05 | Session span | WARN | **`session_span_s <= 600`** | median 71 s, P99 155 s | FLAG; kept | May merge two tray passes | 7 (registered-export) |
| T06 | One identification time per (session, population) | WARN | distinct values = 1 | 1 | FLAG | Session boundary uncertain | **0** (Phase 0's "2" was a pooling artefact) |
| T07 | **File timezone consistency** | WARN | **median first-event hour per file in [10.0, 11.0) local** | 10.48-10.58 | FLAG `timezone_suspect`; apply only a registered override | A silent 3 h shift corrupts weather join and time-of-day analysis | 1 file (7.54 h raw); passes at 10.54 after the +3h rule |
| T08 | Timestamp formats recorded | INFO | format per column per file | known | FLAG | Parser must be per column | dotted in 2 files (one only in the identification column) |
| T09 | Row order is not trusted | INFO | events sorted by parsed time before any sequence logic | n/a | n/a | Files list events out of order; one file newest-first | 78-464 inversions per file |
| T10 | **Timezone override scope** | ERROR | override applies only to its named file; event dates within 2020-10-05..16; raw median first-event hour in [7.0, 8.5]; after +3h the median is in the T07 band [10, 11) | all hold | BLOCK (core lane FAILED) | A normalization applied outside the evidence that supports it would silently corrupt time-of-day and the weather join | valid (raw 7.54 h, normalised 10.54 h) |

## IDENTITY

| Rule | Description | Severity | Check | Expected | Violation handling | Business consequence | Observed |
|---|---|---|---|---|---|---|---|
| I01 | Session in one population only | ERROR | `session_id` in both populations | none | QUARANTINE both versions; excluded from primary metrics | Two versions of one tray pass, no authority | 2 sessions (`session2266`, `session3222`) |
| I02 | Exact duplicate events | WARN | all source columns equal within one file | none | keep first; exclude repeats from sums | Double-counted grams | 2 rows |
| I03 | Natural-key uniqueness | INFO | `(session, time, scale, weight, name)` | unique | FLAG | Reconciles I01/I02 | 7 duplicate keys (2 within file + 5 cross-export) |
| I04 | One tray per session | ERROR | distinct `tray_id` per (session, population) = 1 | 1 | QUARANTINE | Cannot attribute | 0 |
| I05 | Tray not in two overlapping sessions | INFO | overlap of [first weighing, identification] | none | FLAG | RFID or export fault | 0 (weak test) |
| I06 | Cross-export agreement | WARN | fields equal for the same event in both populations | identical | FLAG | Timestamp and name conflicts | `session3222`: 10,800 s offset, 2 substantive name conflicts; `session2266`: identical |
| I07 | Component identity stable across exports for the same scale and day | INFO | Jaccard of normalised name sets per scale-day | identical | FLAG cell; mark component identity LIMITED for that day | Component-level comparison unsafe | 86 of 213 scale-days disjoint in 2020-10-05..16; 0 of 469 elsewhere |

## CROSS-SOURCE

| Rule | Description | Severity | Check | Expected | Violation handling | Business consequence | Observed |
|---|---|---|---|---|---|---|---|
| X01 | Weather covers the window | WARN | hours received = expected (1,129) | complete | FLAG; weather outputs `BLOCKED` if empty | Context missing | complete |
| X02 | Session has a weather observation | INFO | `weather_matched` (hour-ending rule, see TRD 7.8) | true | FLAG; **session stays valid** | Context only | 1,697 of 1,697 |
| X03 | Weather parameter non-null | INFO | NULL in `r_1h`, `ri_10min` | none | NULL kept, never 0; affected sessions counted | Precipitation comparison excludes those hours | 3 source NULLs; 67 sessions (`r_1h`), 25 (`ri_10min`) |
| X04 | UTC/local conversion round-trips across DST | ERROR | local to UTC to local equals input | equal | BLOCK weather join | Wrong hour joined | passes for all sessions; 2020-10-25 is a Sunday with no service |
| X05 | Weather station relevance | INFO | station distance to restaurant | small | document | Regional, not on-site | about 6 km (approximate) |
| X06 | Waste source available | ERROR for waste metrics | source retrievable | yes | metric `BLOCKED` | No waste KPI can exist | **not retrievable** |

## COMPLETENESS

| Rule | Description | Severity | Check | Expected | Violation handling | Business consequence | Observed |
|---|---|---|---|---|---|---|---|
| C01 | Every weekday in window represented | WARN | days present vs weekdays | 35/35 | FLAG | Volume comparison | 35/35 overall; non-registered-export 30 (ends 2020-11-13) |
| C02a | Low observed volume day (registered-export) | INFO | **sessions < 30** | high regime >= 41 | FLAG `low_observed_volume_day` | Volume not like-for-like | 16 of 35 days |
| C02b | Volume irregularity | WARN | **observed regime differs from the weekday's regime** (Mon-Wed high, Thu-Fri low; baseline Oct 5-30) | matches | FLAG `volume_irregularity`; **retained in the analytical population, never excluded, not called a data error** | M3 is not a demand indicator | 6 days: Nov 2, 6, 16, 17, 18, 20 |
| C03 | Expected export file present per population-week | WARN | file list vs weeks | all present | FLAG | Diagnostic coverage incomplete | non-registered-export 2020-11-16..20 absent |
| C04 | Events reconcile to sessions | ERROR | `events_in = events_modelled + duplicates_excluded + events_quarantined` | equal | BLOCK model build | Lost data | to be measured in the pipeline |
| C05 | Core readiness | metric | see M5 | high | reported | The readiness KPI | preview 99.88% |

## Core readiness (M5) and warn-free rate: exact definitions

`core_ready` = registered-export session, at least one valid event, no ERROR-level violation (S05-S07, B01, T01, T03, I01, I04, C04), no identity conflict, all weights valid and positive, timestamps parsed. **Weather, precipitation NULLs, volume flags, timezone status and WARN-level rules never enter it.**

| Quantity | Numerator | **Denominator (fixed before any removal)** | Baseline |
|---|---|---|---|
| **M5 Core Measurement Readiness** | `core_ready = 1` sessions | **1,699** = every registered-export session ID in the source | **1,697 / 1,699 = 99.88%** |
| **S2 Warn-free Rate** | eligible sessions with no session-level WARN | **the same 1,699** | **1,663 / 1,699 = 97.88%** (canonical); event-level variant 1,660 / 1,699 = 97.70% (diagnostic) |

WARN rules counted in the canonical warn-free rate: B04, B07, T04, T05, I06 (session-level). The event-level variant also counts B02 and I02. File-level (T07) and day-level (C02) flags are excluded because they describe a documented normalisation and a flag-only day. Neither figure is ever recomputed against a smaller denominator: removing problematic records from the denominator would make the metric 100% by construction.

## Flag-only rules

C02a, C02b and every WARN/INFO rule **flag** records. `low_observed_volume_day` and `volume_irregularity` describe service dates and **never automatically exclude a day or a session from the KPI population**, and are not labelled data errors.

## Rule inventory by handling class

| Handling | Rules |
|---|---|
| **BLOCK** (stop the stage) | S01, S02, S08 (renamed required column), T10, X04, C04, X01 empty |
| **QUARANTINE** (kept in model, out of the canonical population, listed) | S05, S06, S07, B01, T01, T03, I01, I04 |
| **KEEP_FIRST** | I02 |
| **FLAG** (kept in KPIs) | S03, S04, B02, B03, B04, B05, B07, T02, T04, T05, T06, T07, T08, T09, I03, I05, I06, I07, X02, X03, X05, C01, C02a, C02b, C03 |
| **BLOCKED evidence row** | X06 (waste) |

## Output

`outputs/validation/validation_issues.csv`: `issue_id, run_id, rule_id, category, severity, entity_type, entity_id, population, source_file, message, handling, business_consequence`. `validation_summary_by_rule.csv` counts by rule and population.
