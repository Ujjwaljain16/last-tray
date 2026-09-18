# Phase 2 Profile Report

Real data, no cleaning. Reproduce with `python research/phase2/phase2_a_schema_population_tz.py`, then `phase2_b_...`, `phase2_c_...`, `phase2_d_...` (exploration scripts, not the production pipeline). Machine-readable results are in `outputs/phase2/`.

**Population labels.** "registered-export population" and "non-registered-export population" are **inherited from source filenames**. The public documentation reviewed for this project does not define what they mean, so we do not read them as customer-registration status. Session keys are `(session_id, population)`. The two populations are never pooled.

**Corrections to Phase 0 numbers.** Phase 0 pooled the two crossover sessions across populations. Re-profiled per `(session_id, population)`: sessions with more than one identification value = **0** (was 2), sessions spanning more than 10 minutes = **7** (was 8; the eighth was `session3222` pooled across exports, 10,873 s), same-scale repeats = **512 events in 222 sessions** (was 538). Nothing else moved.

---

## 1. Schema drift

| Finding | Evidence |
|---|---|
| Two header variants | 4 files carry 8 named columns including `weighting_type`; **7 files carry 7** (6,990 of 12,284 rows). Column order is identical within each variant. |
| `weighting_type` has one value | `line` (5,294 rows where present) |
| Every file has 4 trailing blank header columns | 4 blank header columns x 11 files; every cell under them is empty (**0 non-empty**) |
| Encoding | All 11: UTF-8 BOM, CRLF |
| Three filename patterns | `registered_2020_10_05-2020_10_18.csv` alone uses underscores. The date ranges `10-19..10-25` and `10-25..10-31` overlap on the 25th (a Sunday with no service). No session appears in two files of one population. |
| Two timestamp formats | Dashed (`2020-10-09 11:07:07`) in 10 files; **dotted** (`2020.10.16 07:47:02`) in the UTC-suspect file. `non_registered_2020-11-09_2020-11-15.csv` has dashed weighing times but **dotted identification times** for all 580 rows. |
| **Row order is not chronological anywhere** | 78 to 464 time inversions per file. `non_registered_2020-11-09_2020-11-15.csv` lists each session's events **newest first** (154 of 155 multi-event sessions). Any logic that relies on file order would be wrong. |
| Session IDs carry no time information | Spearman(session number, first weighing) = 0.001. IDs run 0..3342 across both exports: an anonymised label, so a contiguous ID range says nothing about completeness. |

**Consequence for the pipeline:** parse by header name, not position; sort by parsed time, never by row order; accept both timestamp formats per column, not per file.

## 2. Population-level profile

Crossover sessions excluded from both. Full table: `outputs/phase2/population_profile.csv`.

| Measure | registered-export | non-registered-export |
|---|---:|---:|
| Sessions | 1,697 | 1,644 |
| Weighing events | 8,360 | 3,900 |
| Events per session, mean / median | 4.93 / 5 | 2.37 / 2 |
| Single-event sessions | 17 (1.00%) | 620 (37.71%) |
| Sessions with a hot-food scale | 97.2% | 74.9% |
| Derived selected weight P10 / median / P90 | 314 / 499 / 1,040 g | 4 / 192 / 855 g |
| Sessions under 50 g | 0.41% | 28.41% |
| Median distinct components | 5 | 2 |
| Session span, median / P99 | 71 s / 155 s | 24 s / 122 s |
| Service days covered | 35 | 30 |

The Phase 0 population decision stands with cleaner numbers. Non-registered-export sessions contain far less per session, with 28% below 50 g. The cause is not identifiable from the source (see Q2).

## 3. Timestamp and timezone validation

Full evidence: `docs/timezone_decision.md`. New in Phase 2:

- **T07 (file median first-event hour in 10:00-11:00) behaves as designed.** Only `registered_2020_10_05-2020_10_18.csv` fails on raw times (7.54 h; 1,925 of its 1,931 events before 10:00). After the +3h normalisation every file passes (10.48-10.58 h). All other files pass on raw times.
- **Offset scan, -6 h to +6 h** (L1 distance of hour-of-day distribution to the other registered-export files): +3 h = **0.046**, +2 h = 1.029, +4 h = 1.064, all other offsets 1.5-2.0. The test has 1-hour resolution, so it cannot separate 3 h from 3 h ± 30 min. The exact 10,800 s difference on `session3222` does.
- **Crossover sessions, event by event:** `session3222` (6 events): every timestamp differs by exactly **10,800 s**; weights and scales are identical. `session2266` (5 events): every field identical (0 s), so it is an exact duplicate across the two exports. My earlier scramble came from pairing by row order.
- **Weather join consequence:** all 385 sessions in the normalised file would join to a different weather hour if the timezone were mishandled (mean absolute temperature difference 1.23 °C).

**Status:** "+3h is the strongest-supported normalization decision based on cross-export consistency evidence; source metadata does not explicitly confirm the timezone." Weights and service dates are timezone-independent (KPI preview below excludes the file and moves M1 by 6 g).

## 4. Session reconstruction diagnostics

- 3,345 `(session_id, population)` rows for 3,343 IDs. **0** sessions with more than one tray, **0** with more than one identification value, **0** spanning more than one file.
- **Exact duplicate rows: 2** (`session1274` in the registered-export population, `session209` in the non-registered-export population). Kept once, excluded from sums.
- **Same scale weighed twice in a session (B05): 512 events in 222 sessions** (212 registered-export, 10 non-registered-export), 259 second-or-later events. 93.8% follow within 30 s, 97.7% within 60 s, **100% carry the same component name**, and the second reading is smaller than the first 59.8% of the time. A cumulative reading would always be larger, so these read as **additive scoops**: summing is appropriate. Repeats carry a median 7% (P90 31%) of their session's derived weight.
- **Identification lag** after the last weighing (registered-export): median 52 s, P95 117 s, P99 168 s.
- **T04, identification before the last weighing: 3 sessions.** `session2229` is instructive: identified at 11:04:53, but its last weighing (Lemon chicken, 1,057 g) is at 11:49:00. The tray was identified, then went back to the line.

## 5. Component-name normalisation stability

| Test | Result |
|---|---|
| Distinct raw names | 246 |
| After trim and whitespace collapse | 246 (**no change**) |
| After case-fold | 245 (one merge: `Chili Con Carne` / `Chili con carne`) |
| Rows with edge whitespace | 398 rows across 16 names, always the same names, so trimming merges nothing |
| Sessions where raw and normalised distinct counts differ | **0** |
| Names on more than one scale | 183 of 245; 143 after treating left/right twin scales as one |
| Scale-days with more than one normalised name (per population) | 44 of 1,637 (2.7%) |

**M4 sensitivity** (registered-export, median distinct components):

| Identity definition | Median | Sessions differing from chosen |
|---|---:|---:|
| Normalised names (chosen) | 5 | 0 |
| Raw names | 5 | 0 (0.00%) |
| Distinct scales | 5 | 45 (2.65%) |
| Weighing events | 5 | 254 (14.97%) |

**Cross-export stability. This is where the limitation is.** For the 682 scale-days that appear in both exports:

| Window | Scale-days | Identical name set | Disjoint name set |
|---|---:|---:|---:|
| 2020-10-05..16 (overlaps the +3h file) | 213 | **59.2%** | **40.4%** (86) |
| Every other day | 469 | 95.7% | **0%** |

In the Oct 5-16 window the two exports disagree about which dish was on which scale. The disagreements mix two kinds: language or label variants (`lohkoperunoita` vs `baked potato`, `kaali-porkkanaraaste` vs `grated cabbage`) **and genuinely different dishes** (`kalkkunaa bbq kastikkeessa` vs `kalkkunaa herkkusienikastikkeessa`, turkey in BBQ vs mushroom sauce). They do not match the same scale on adjacent days (0 hits for -4..+4 days), so it is not a simple day shift. `session3222` shows the same thing at event level (2 substantive name conflicts out of 6).

**Decision on normalisation.** The defensible normalisation is **trim + whitespace collapse + case-fold**, applied to the name string only. A Finnish-English alias table is **not defensible**: the source supplies none, and some cross-export differences are real dish differences. We therefore do not collapse names beyond that.

**Status.** M4 counts distinct names *within one session*, from one lookup, so it is unaffected (identical median under every definition tested). `distinct_component_count_status = READY_WITH_LIMITATION`, and component **identity** across exports or days in the Oct 5-16 window is marked **LIMITED**: no component-level or cross-day component comparison will be made from that window.

## 6. Weighing-event and session-span checks

- **Inter-event gap within a session:** median 16 s, P90 34 s, P99 67 s, P99.9 218 s, max 2,723 s.
- **Session span (registered-export):** median 71 s, P99 155 s. The largest values are `198, 269, 291, 305, 545, 1783, 1796, 2190, 2323, 2593, 2748, 2772`: **a clean gap between 545 s and 1,783 s.** Seven sessions sit above it.
- All seven long sessions contain one within-session gap of 1,647-2,723 s. That is consistent with a diner returning to the line after the tray was identified (`session2229` demonstrates it), so these sessions may merge two tray passes. We keep them and flag them.
- Non-registered-export spans never exceed 230 s.

## 7. Daily volume profile

Full table: `outputs/phase2/daily_volume_by_population.csv`.

**Registered-export volume is bimodal by weekday, not steady.**

| | Mon | Tue | Wed | Thu | Fri |
|---|---:|---:|---:|---:|---:|
| Weekday median, Oct 5-Nov 13 | 70.5 | 90.5 | 70.5 | 8 | 11 |

In the four baseline weeks (Oct 5-30) the separation is perfect: every Monday-Wednesday has at least **41** registered-export sessions, every Thursday-Friday at most **12**. The **non-registered-export** population is flat: 36-75 sessions every day, weekday means 47-65.

So a registered-export "low day" is normal on Thursdays and Fridays (16 of 35 days are under 30 sessions). Against that weekday pattern, **six days break the regime**:

| Date | Weekday | Registered-export sessions | Expected regime |
|---|---|---:|---|
| 2020-11-02 | Mon | 14 | high |
| 2020-11-06 | Fri | 83 | low |
| 2020-11-16 | Mon | 22 | high |
| 2020-11-17 | Tue | 19 | high |
| 2020-11-18 | Wed | 18 | high |
| 2020-11-20 | Fri | 96 | low |

## 8. Investigation: Nov 16-20

Retained in the analytical population, flagged `volume_irregularity`, **not labelled a data error**.

| Question | Answer |
|---|---|
| Do the sessions look degraded? | **No.** Single-event share 0-8% (baseline 1.3%), hot-food share 89-99% (baseline 97%), median derived weight 472-598 g (baseline 511 g), all 30 scales in use, hourly shape similar. |
| Is the week unique? | **No.** Nov 2 (Mon, 14) and Nov 6 (Fri, 83) also break the weekday regime. Nov 16-18 is the longest run: three consecutive high-regime weekdays at 18-22. |
| Is Nov 20 an artefact? | 96 sessions, 0% single-event, 99% with a hot dish: ordinary sessions in unusual quantity. |
| Can session IDs reveal gaps? | No (IDs are shuffled). |
| Missing companion export | No non-registered-export file exists for the week (C03). |

**What this means:** registered-export volume behaves like a **schedule or inclusion pattern**, not restaurant demand. M3 is therefore *observed sessions in the registered-export population*, and its description must say it is not a demand indicator. Cause: **unresolved** (Q5).

## 9. Investigation: the 2,097 g event

`session2104`, registered-export, `koti2-oikea-lammin2`, "Peppery meat stew", 2020-10-12 10:36 local (07:36 raw, in the +3h file). Earlier in the session the tray collected six small items (4, 13, 15, 43, 36, 99 g). Session total 2,307 g (99.65th percentile).

- On that scale: n = 425, median 153 g, P99 1,227 g; 2,097 is the **99.76th percentile**, not an isolated impossibility.
- Hot scales overall: P99 1,149 g, P99.9 1,449 g. Six events in the data are at least 1,500 g (3 per population).
- The same component name: n = 29, median 241 g, P95 1,376 g.
- Removing that session moves M1 by 0.0 g and M2 by -1.6 g.

**Disposition:** B02 WARN, kept in sums. Whether such readings are genuine bulk portions or tray/plate artefacts cannot be determined from the source (Q9).

## 10. Investigation: the two crossover sessions

| | `session2266` | `session3222` |
|---|---|---|
| Events | 5 in each export | 6 in each export |
| Scales and weights | identical | identical |
| Timestamps | identical | every one exactly 10,800 s apart |
| Component names | identical | 3 of 6 differ (2 substantive, 1 case-only) |
| Row order | reversed in the non-registered file | same |
| Disposition | exact cross-export duplicate | version conflict |

Both are **quarantined** (I01, ERROR) from primary metrics until the source-of-truth question is answered. Effect of including them: M1 +0.0 g, M2 +2.8 g.

## 11. Investigation: the 17 single-event registered-export sessions

Full list: `outputs/phase2/single_event_registered_export_sessions.csv`.

- 10 on hot scales, 7 on cold; weights 3-565 g (median 127 g).
- **10 exceed 100 g**, and several are soups or a single main (e.g. 565 g vegetable pea soup, 492 g chicken soup), which reads as a plausible single-item lunch. **6 are 50 g or less** (3, 3, 4, 4, 38, 46 g) and look like partial captures.
- No clustering: spread over 6 files, all five weekdays, and only 2 fall in Nov 16-20.

**Disposition:** B04 WARN, kept. Removing them all moves M1 by +2 g and M2 by +5 g.

## 12. FMI precipitation timestamp semantics

FMI's public pages reviewed for this project do not document the convention. We tested it empirically: 10-minute intensity (`ri_10min`) and `r_1h` for 2020-10-22 (a rainy day).

| Hypothesis | Mean absolute error vs `r_1h` |
|---|---:|
| `r_1h` at time t = rain in the **hour ending at t** | **0.021 mm** |
| `r_1h` at time t = rain in the hour starting at t | 0.378 mm |

**Result:** `r_1h` at time t is the accumulation over the hour ending at t. **Limitation:** one rainy day. The probe is preserved in `data/raw/weather/probe_fmi_100949_20201021_20201023_10min_r1h_semantics.xml`.

**Join rule change.** Because a session at 10:36 local (07:36 UTC) sits inside the hour 07:00-08:00, the observation covering it is stamped **08:00**. The rule is therefore *ceil to the next full UTC hour* (an event exactly on the hour maps to its own timestamp), not floor. Dry run on the primary population: **1,697 of 1,697** sessions match; `r_1h` is NULL for 67 sessions and `ri_10min` for 25 (three source NULLs on 2020-11-06). Local to UTC to local round-trips identically for every session; the DST change (2020-10-25) falls on a Sunday with no service. The station is Turku Artukainen, about 6 km from an approximate campus location (my coordinates for the restaurant are approximate, not verified).

## 13. KPI sensitivity preview

**PREVIEW ONLY. Not evidence outputs**; the pipeline will compute the real ones. `outputs/phase2/kpi_sensitivity_preview.csv`.

| Scenario | Sessions | M1 median (g) | M2 P90 (g) | M4 median |
|---|---:|---:|---:|---:|
| **Primary: registered-export, crossover quarantined** | 1,697 | 499 | 1,040 | 5 |
| Exclude any session with a WARN rule | 1,663 | 500 | 1,016 | 5 |
| Exclude the +3h-normalised file | 1,312 | 505 | 977 | 5 |
| Exclude volume-irregularity days | 1,445 | 505 | 1,066 | 5 |
| Exclude Nov 16-20 | 1,530 | 500 | 1,052 | 5 |
| Exclude single-event sessions | 1,680 | 501 | 1,044 | 5 |
| Exclude the 2,097 g session | 1,696 | 499 | 1,038 | 5 |
| Include the 2 crossover sessions | 1,699 | 499 | 1,042 | 5 |

M1 stays within 499-505 g and M4 is 5 in every scenario. M2 is the sensitive one: it moves by up to about 63 g (6%), mostly because the Oct 5-16 file describes a different period, **not** because of its timezone (weights are timezone-independent). M5 preview: `core_ready` = 1,697 of 1,699 registered-export session IDs (**99.88%**); warn-free = 1,663 of 1,699 (**97.88%**, session-level WARNs; the event-level variant is 1,660 of 1,699 = 97.70%; see `decision_log.md` D28).
