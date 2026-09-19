# Timezone Investigation and Decision

**Status: ADOPTED WITH RESIDUAL UNCERTAINTY.**

> **A +3 hour normalization is the strongest-supported engineering decision based on cross-export temporal consistency checks; the original source does not explicitly confirm the timezone metadata.**

Nothing in the public dataset or documentation states a timezone. The evidence supports our engineering decision; it is not the source stating `timezone = UTC`. This document records how we decided, what we checked, and what we still cannot prove.

## 1. Question

Flavoria's CSV timestamps (`weighing_event_time`, `user_identification_time`) carry no timezone. FMI weather is UTC. Which zone is each file in?

## 2. Evidence (all from the raw files, reproducible from `data/raw/flavoria/dataset_csv.tar`)

| # | Observation | Result |
|---|---|---|
| E1 | Median time of the first weighing of each service day, by file | `registered_2020_10_05-2020_10_18.csv`: **07:30-07:33** (weekly medians; earliest ever 07:33:07). Every other registered-export file: **10:31-10:35** (weekly medians). |
| E2 | Hour-of-day distribution of that file | Raw: 07 h 25.5%, 08 h 51.3%, 09 h 22.9%. All other registered-export files: 10 h 25.3%, 11 h 53.4%, 12 h 20.8%. Same shape, shifted. |
| E3 | Same-session comparison. `session3222` exists in both the registered-export (dot-format) and non-registered-export (dash-format) files for 2020-10-14 | Every one of its 6 events differs by exactly **3 h 00 m 00 s** (08:24:00 vs 11:24:00, 08:24:06 vs 11:24:06 ...). Weights (623, 6, 33, 68, 227, 410 g) are identical. |
| E4 | File-format signature | The shifted file is the only one using `YYYY.MM.DD` for `weighing_event_time`. Its `user_identification_time` is also dotted and also shifted (same session gap of about 96 s as elsewhere). |
| E5 | Calendar context (this file only) | All 1,931 events fall on 2020-10-05..16, before the local clock change on 2020-10-25. For those dates a UTC timestamp and a Helsinki local timestamp differ by three hours. This is context for one file's date range, **not** a general statement about any timezone. |

## 3. Hypothesis

H1: `registered_2020_10_05-2020_10_18.csv` (registered-export population) is recorded in **UTC**. All other files are recorded in **Europe/Helsinki local time**.

## 4. Validation performed

| Test | Method | Result |
|---|---|---|
| V1 | Shift the file by +h hours and compute L1 distance of its hour-of-day distribution to the other registered-export files (0 = identical) | +0 h: **1.994**; +2 h: 1.029; **+3 h: 0.046**; +4 h: 1.064 |
| V2 | After +3 h, are any events outside the observed service window? | 0 of 1,931 events before 10:00 local; latest event 11:38:59. Without the shift, 1,925 of 1,931 events fall before 10:00, in a window in which no other file has any event. |
| V3 | Exact-offset test on the shared session (E3) | 6 of 6 events differ by exactly 10,800 s. |
| V4 | Alternative H2: "fixed UTC+2 (winter time) recorded in error" | +2 h distance 1.029. Rejected. |
| V5 | Tray-window collision test (a tray cannot be in two sessions at once) | **Uninformative**: 0 collisions at both +0 h and +3 h across 1,684 candidate pairs. Reported so nobody cites it as support. |

## 5. Decision

- Parse every timestamp as a naive wall-clock time first, and **store the raw string untouched** (`event_time_raw`).
- A **file-specific override in configuration** (`config/timezone_overrides.yml`, `scope: file_specific`, `source_confirmed: false`) names `registered_2020_10_05-2020_10_18.csv` and applies +3 hours to `weighing_event_time` and `user_identification_time`. Every other file defaults to `Europe/Helsinki` local time as an assumption. The offset is fixed: no DST-aware conversion is implied for times we cannot verify.
- `event_time_local` is Europe/Helsinki. `timezone_handling` on every event row is one of `SOURCE_LOCAL_ASSUMED` or `NORMALISED_PLUS_3H_STRONGEST_SUPPORT`. The label never disappears from the model, and no output describes the timezone as "confirmed".
- A **cross-check rule (T07)** runs on every file: if a file's median first-event hour lies outside the 10:00-11:00 local band and no override is registered, the file is flagged `WARNING` (`timezone_suspect`) rather than silently converted. This is how we found it, and it will catch the next one.
- The override is applied in transformation, never in the raw layer.

## 5a. File-specific scope and rule T10

The normalization is modelled as a **file-specific, evidence-backed engineering decision**. It is not a statement about any timezone
in general, it is not source-confirmed, and it must never be applied to another file. Rule **T10** (implemented in ingestion,
`src/ingest/tz_scope.py`) refuses to apply it unless **all** of the following hold; otherwise the core lane is **FAILED** and nothing
downstream may run:

| Check | Configured in `valid_for` | Real file |
|---|---|---|
| The override is applied only to the named file | the file name is the registry key | 1 of 11 files |
| Event dates lie inside the range the evidence covered | 2020-10-05 to 2020-10-16 | 2020-10-05 to 2020-10-16 |
| The shift is still visible in the raw times | raw median first-event hour in [7.0, 8.5] | 7.54 |
| After +3h the file passes T07 | median first-event hour in [10, 11) | 10.54 |

Why this matters: if a corrected file were ever delivered under the same name, applying +3h would silently push genuine local times
to about 13:30. The scope check turns that silent error into a loud failure. Tests: `tests/test_tz_scope_and_handoff.py`.

## 5b. How staging applies it

- Every staged timestamp keeps `*_raw` (verbatim), `*_canonical_utc` and `timezone_handling`, plus `timezone_transformation_reason`
  (for this file: "cross-export temporal alignment (file-specific, evidence-backed; not source-confirmed)").
- Files without an override are `SOURCE_LOCAL_ASSUMED` and are converted with Europe/Helsinki zoneinfo rules, so the +3 h before
  2020-10-25 and +2 h after it are respected. **UTC+3 is not a general Helsinki assumption anywhere in the pipeline.**
- The override is applied only if the configuration names the exact filename **and** the ingestion handoff says the same. Any
  disagreement, in either direction, stops staging of the source.
- Canonical UTC was checked against an independent pandas computation for all 12,284 rows (both time columns).

## 6. Impact analysis: what does a wrong decision break?

| Output | Depends on timezone? | Consequence if H1 is wrong |
|---|---|---|
| derived_selected_meal_weight_g, session volume per service day, component count | **No.** Weights and dates are unaffected (UTC 07:33-08:39 stays on the same calendar date). | None |
| Core measurement readiness | No | None |
| Time-of-day patterns | Yes | 385 registered-export sessions (about 23% of the primary population) would be mislocated by 3 h |
| Weather context join and weather coverage | Yes | The same 386 sessions would be joined to the wrong hour of weather |

This is why weather sits outside the core metric set. A timezone uncertainty must never be able to invalidate a weight.

## 6a. Profiling additions

| Check | Result |
|---|---|
| Offset scan -6 h to +6 h (1-hour resolution) | +3 h = **0.046**; +2 h = 1.029; +4 h = 1.064; all others 1.5 to 2.0. Unique minimum. |
| T07 on all 11 files | Raw times: only the suspect file fails (median first event 7.54 h; 1,925 of 1,931 events before 10:00). After +3 h: every file passes (10.48-10.58 h). |
| Exact offset on the shared session | `session3222`: 6 of 6 events differ by exactly 10,800 s. `session2266` differs by 0 s, so it is an exact duplicate, not a shifted one. |
| Independence of KPIs | Excluding the normalised file changes M1 by +6 g (weights and dates do not depend on the clock). |
| Weather consequence | All 385 sessions in the file would join a different weather hour if mishandled (mean absolute temperature difference 1.23 C). |
| Cross-export component names | Disagreements between the two exports (40.4% of scale-days with disjoint name sets) occur **only** in 2020-10-05..16, the same window as the suspect file, and 0 of 469 scale-days elsewhere. This coincidence suggests the two exports were produced by different processes for that window. It is **not** evidence about the timezone and is not used as such (Q11). |

## 6b. Sensitivity of the KPIs to this decision

`outputs/validation/sensitivity_analysis.csv` (scenarios TZ0 to TZ4) recomputes M1-M5 under +0h to +4h. M1, M2, M4 and M5 are identical for +2h, +3h and +4h; +0h and +1h lower M5 to 82.05% and 93.82% by quarantining 303 and 103 sessions under T03. The KPIs therefore cannot distinguish +2h from +3h from +4h: **only the cross-export evidence does**, and the +3h decision was taken from that evidence before the comparison was run. See `docs/sensitivity_analysis.md`.

## 7. Residual uncertainty

- The 3 h offset is inferred from the data, not documented by the source. It is the strongest-supported normalisation, not a confirmed fact. The export owner could confirm it.
- We cannot rule out that the file was exported by a different tool with a different convention that happens to produce the same offset. The offset behaviour is identical for E1-E5, so the practical result is the same.
- Whether the non-registered dash-format files are truly local time is inferred from their service-window agreement with the registered-export local-time files (10:2x-14:43). Not proven either.
- Only the Oct 5-16 window is affected by the override. The DST boundary (2020-10-25, a Sunday with no service) never falls inside an overridden file.
