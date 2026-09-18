# Decision Log

Every material decision has the same seven parts: **Decision, Evidence, Alternatives tested, Chosen approach, Why, Business impact, Residual uncertainty.** "vs plan" says whether the original `plan.md` was confirmed, changed, or silent. Sensitivity scenario IDs (S00, TZ0 ...) refer to `outputs/validation/sensitivity_analysis.csv`.

Population labels are inherited from source filenames and are not interpreted semantically. Diagnostic thresholds in this log are derived from observed data structure and are not claims of physical impossibility.

---

## D1. Atomic grain is the component weighing event; a session is derived
*vs plan: CHANGED (plan §22-23 assumed one row per session)* · 2026-09-18
- **Decision.** One source row = one component weighing event. A dining session is a derived entity.
- **Evidence.** 12,284 rows for 3,343 session IDs (3.7 per session); 8 raw columns, none session-level.
- **Alternatives tested.** (a) Row = session, as the plan assumed: median "session" 63 g, P90 277 g, meaningless as a meal. (b) Group by `tray_id`: 687 trays, median 2,013 g, because 87% of trays are reused across days. (c) Group by `session_id` (chosen).
- **Chosen approach.** Group events by (`session_id`, `population`).
- **Why.** Only key with 0 multi-tray sessions and 0 sessions with more than one identification time.
- **Business impact.** Every KPI is a DERIVED session-level quantity; the observed event table is preserved beneath it.
- **Residual uncertainty.** The session boundary is the source's own. Seven sessions with a 1,647-2,723 s internal gap may merge two tray passes (Q12).

## D2. The meal-level number is `derived_selected_meal_weight_g`, never "total weight"
*vs plan: CHANGED (plan §7 quoted a checkout-scale total)* · 2026-09-18
- **Decision.** Meal weight = SUM of component event weights per session, named as derived.
- **Evidence.** No total column in any file. The "total plate contents" statement belongs to Weigh & Dine, a different, unavailable system.
- **Alternatives tested.** Weigh & Dine total (unretrievable); MAX reading per session (median 195 g, implausible as a meal); sum (chosen). Repeats on one scale are additive scoops: 100% same name, 93.8% within 30 s, second reading smaller than the first 59.8% of the time, so readings are not cumulative.
- **Chosen approach.** Sum non-duplicate events; NULL if any weight is invalid; carry the rule beside the value.
- **Why.** Scales weigh each component as placed; the sum is the only reconstruction the source supports.
- **Business impact.** M1/M2 are labelled derived; no claim about plate content, consumption or waste.
- **Residual uncertainty.** Tare handling and items added outside weighed stations are unknown (Q9).

## D3. Component-level weights exist; "no component weights" applies to Weigh & Dine only
*vs plan: CHANGED (plan §18)* · 2026-09-18
- **Decision.** Component grams are OBSERVED in the public CSV.
- **Evidence.** `weight_of_a_component` on every row; the WnD page states "Weight: no individual components".
- **Alternatives tested.** Reading the plan's claim as applying to the CSV: contradicted by the data.
- **Chosen approach.** Treat the two systems as distinct sources in the source map.
- **Why.** Different scales, different documentation, different grain.
- **Business impact.** Component-level composition (M4) is possible; a checkout-total cross-check is not.
- **Residual uncertainty.** None on the fact; whether the two systems could be reconciled is unknowable without WnD data.

## D4. Timezone: +3h normalisation for one file, as an evidence-backed engineering decision
*vs plan: CHANGED (plan §24 single timezone)* · 2026-09-18
- **Decision.** `registered_2020_10_05-2020_10_18.csv` is normalised by +3h to Europe/Helsinki, per file, configurable, labelled on every row. It is **not** presented as source-confirmed timezone metadata.
- **Evidence.** Its first weighing of the day is 07:30 vs 10:31 in every other file; `session3222` differs by exactly 10,800 s across exports; hour-of-day distance to the other files is 1.994 at +0h and 0.046 at +3h.
- **Alternatives tested.** Offsets -6h to +6h (L1 scan: +2h 1.029, +4h 1.064, all others 1.5-2.0). Sensitivity: TZ0 (no shift) quarantines 303 sessions under T03, M5 82.05%, M2 -50.5 g; TZ1 quarantines 103, M5 93.82%; TZ2, TZ3, TZ4 leave M1-M5 unchanged. Weather hour changes for all 385 file sessions under every non-baseline hypothesis (mean |Δ temperature| 0.47-1.23 °C).
- **Chosen approach.** +3h, with T07 as a standing check.
- **Why.** Strongest cross-export consistency, and the only hypothesis under which every file passes T07.
- **Business impact.** KPIs are insensitive to +2h/+3h/+4h; the choice affects the weather join and time-of-day analysis only, for 385 sessions (23% of the canonical population).
- **Residual uncertainty.** The scan has 1-hour resolution; +2h and +4h are indistinguishable from +3h on KPI and T03 outcomes, so only the cross-export evidence separates them. The source owner has not confirmed (Q3).

## D5. Two populations, never pooled; registered-export is primary
*vs plan: NEW* · 2026-09-18
- **Decision.** Labels inherited from filenames; registered-export feeds the KPIs, non-registered-export is diagnostic only.
- **Evidence.** Single-event sessions 1.0% vs 37.7%; sessions with a hot-food scale 97% vs 75%; median derived weight 499 g vs 192 g; P10 314 g vs 4 g; service-day coverage 35 vs 30.
- **Alternatives tested.** Pool both: median 413 g, P90 950 g, a blend describing neither. Non-registered as primary: 28% of sessions under 50 g. Registered as primary (chosen).
- **Chosen approach.** Separate populations; session key (`session_id`, `population`).
- **Why.** Capture shape of the registered-export population matches a full lunch tray; the other is unexplained.
- **Business impact.** KPIs describe one export, not "the average diner"; pooling would have lowered M1 by 86 g.
- **Residual uncertainty.** The labels' meaning and the mechanism splitting the exports (Q1, Q2).

## D6. Crossover sessions are quarantined
*vs plan: NEW* · 2026-09-18, reaffirmed 2026-09-19
- **Decision.** `session2266` and `session3222` are excluded from the canonical population.
- **Evidence.** `session2266` is identical event-for-event across exports; `session3222` differs by exactly 10,800 s with 2 of 6 component names different.
- **Alternatives tested.** Keep the registered-export version (S03: M2 +3.0 g); keep only the exact duplicate (S02: -0.4 g); include both (S01: M2 +2.8 g, M5 becomes 100% only by lifting the quarantine); quarantine both (chosen).
- **Chosen approach.** Quarantine both versions; report inclusion effects **only** as sensitivity.
- **Why.** No authority exists to choose a version; choosing would be arbitrary.
- **Business impact.** M1 +0.0-0.5 g, M2 -0.4 to +3.0 g either way: the choice does not affect conclusions.
- **Residual uncertainty.** Which record is authoritative (Q4).

## D7. Waste is BLOCKED / SOURCE GAP
*vs plan: CONFIRMED* · 2026-09-18
- **Decision.** `waste_weight_g` is always NULL; the waste metric is `BLOCKED`.
- **Evidence.** The waste page lists its sample as `"TODO, Ask!"`, gives no API, schema or contact, and points to a restricted repository.
- **Alternatives tested.** Estimating waste from selected weight and an assumed eaten fraction (no source for the fraction); setting waste to 0 (falsely certain); NULL with a gap register entry (chosen).
- **Chosen approach.** NULL, `BLOCKED`, required source named.
- **Why.** Any number would be manufactured.
- **Business impact.** The client learns exactly which extract to request; no false waste KPI.
- **Residual uncertainty.** Permanent unless a public raw waste dataset appears.

## D8. Weather is context, fully separated from core measurement readiness
*vs plan: CHANGED (plan §25 put weather inside readiness)* · 2026-09-18
- **Decision.** Weather never changes `core_ready`; Weather Context Coverage (S1) is a supporting metric.
- **Evidence.** The timezone uncertainty affects only the weather join; weights are unaffected.
- **Alternatives tested.** Weather inside readiness (rejected: an FMI outage or a timezone doubt would invalidate valid weights).
- **Chosen approach.** Two independent gates, core and context.
- **Why.** Context must not be able to invalidate a measurement.
- **Business impact.** A weather failure blocks only weather outputs.
- **Residual uncertainty.** None.

## D9. Core KPI set
*vs plan: CHANGED* · 2026-09-18, locked 2026-09-19
- **Decision.** M1 Median Derived Selected Meal Weight, M2 P90 Derived Selected Meal Weight, M3 Observed Valid Sessions — Registered-Export Population (see D27), M4 Median Distinct Normalized Components per Session, M5 Core Measurement Readiness.
- **Evidence.** Sensitivity: M1 493-505 g and M4 = 5 in every scenario; M2 977-1,066 g.
- **Alternatives tested.** Portion variability as a KPI (kept as supporting S3); weather match rate as a KPI (kept as S1).
- **Chosen approach.** Five core metrics, one blocked metric, supporting and diagnostic fields.
- **Why.** Each answers one question the available evidence can defend.
- **Business impact.** A short, defensible executive set.
- **Residual uncertainty.** M2 is the most sensitive (period effect up to 63 g).

## D10. The problem statement no longer implies waste can be measured
*vs plan: CHANGED* · 2026-09-18
- **Decision.** The MVP establishes whether the measurements are sufficient for future waste decisions.
- **Evidence.** Waste unretrievable (D7).
- **Alternatives tested.** Framing around "reducing waste" (unsupported).
- **Chosen approach.** Sufficiency-of-measurement framing, later sharpened as a measurement-reconstruction pipeline (D31).
- **Why.** Claims must match evidence.
- **Business impact.** The recommendation is a data-procurement decision.
- **Residual uncertainty.** None.

## D11. The FDE judgement call has three parts
*vs plan: CHANGED (plan had part 1 only)* · 2026-09-18
- **Decision.** Selected weight is not waste; a derived total is not an observed total; population, schema and timezone differences are findings, not clean-up.
- **Evidence.** D1-D5.
- **Alternatives tested.** Presenting the simple version alone.
- **Chosen approach.** All three, with the sensitivity file as proof of testing.
- **Why.** The second and third are what Phase 0-2 actually discovered.
- **Business impact.** Explains why the client should trust the pipeline's caveats.
- **Residual uncertainty.** None.

## D12. Weather station and retrieval
*vs plan: NEW detail* · 2026-09-18
- **Decision.** FMI Turku Artukainen (FMISID 100949), hourly, seven 7-day requests.
- **Evidence.** The server rejects spans above 168 h; `place=Turku` resolves to this station; 1,129 of 1,129 hours received.
- **Alternatives tested.** Turku Rajakari (about 13 km from the campus area vs about 6 km; both distances approximate).
- **Chosen approach.** Artukainen.
- **Why.** Nearest returned Turku station.
- **Business impact.** Weather is regional context only.
- **Residual uncertainty.** The restaurant's exact coordinates were approximated, not verified.

## D13. The window is 35 weekday lunches; seasonality is out of scope
*vs plan: CHANGED (plan §30)* · 2026-09-18
- **Decision.** No seasonal or year-level claims.
- **Evidence.** 2020-10-05..2020-11-20, COVID period.
- **Alternatives tested.** None viable.
- **Chosen approach.** State the window on every output.
- **Why.** Five weeks cannot support seasonality.
- **Business impact.** Findings are a snapshot.
- **Residual uncertainty.** Representativeness of the snapshot.

## D14. Tooling
*vs plan: CHANGED* · 2026-09-18
- **Decision.** Python 3.11+, pandas, requests, zoneinfo/tzdata, SQLite, PyYAML, matplotlib, pytest. No DuckDB, parquet optional.
- **Evidence.** Installed environment (3.11.9).
- **Alternatives tested.** The plan's 3.12+ and DuckDB (unneeded).
- **Chosen approach.** Minimal standard stack.
- **Why.** Simplest architecture that proves the assignment.
- **Business impact.** Easy to reproduce.
- **Residual uncertainty.** None.

## D15. Session key is (`session_id`, `population`)
*vs plan: NEW* · 2026-09-18
- **Decision.** Composite key; component key adds `population`.
- **Evidence.** Two IDs occur in both exports.
- **Alternatives tested.** `session_id` alone (collides).
- **Chosen approach.** Composite.
- **Why.** Business identity is not always the source's apparent identifier.
- **Business impact.** Crossovers are visible instead of silently merged.
- **Residual uncertainty.** None.

## D16. Placeholder numbers from `plan.md` are not used
*vs plan: CONFIRMED as illustrative only* · 2026-09-18
- **Decision.** "12,384 sessions / 642 g / 97.6%" never appear.
- **Evidence.** Actual: 3,343 IDs, M1 499 g.
- **Alternatives tested.** n/a. **Chosen approach.** Real numbers only. **Why.** No fabricated figures.
- **Business impact.** None. **Residual uncertainty.** None.

## D17. Core KPI names and field names locked
*vs plan: CHANGED* · 2026-09-19
- **Decision.** Field names: `component_id_normalized`, `timezone_normalization`, `quality_status`, `first_weighing_at`, `last_weighing_at`, `component_weighing_event_count`, `distinct_component_count`, `session_duration_minutes`; new `fact_daily_volume`.
- **Evidence.** Review decision.
- **Alternatives tested.** Earlier draft names (`component_name_norm`, `tz_treatment`, `dq_status`).
- **Chosen approach.** As listed.
- **Why.** Names state what the field is.
- **Business impact.** Consistent vocabulary across docs and code.
- **Residual uncertainty.** None.

## D18. Component counting is within a session; no alias table
*vs plan: NEW* · 2026-09-19
- **Decision.** M4 = median distinct `component_id_normalized` per session; `component_weighing_event_count` is a diagnostic.
- **Evidence.** M4 median 5 under raw names, normalised names, distinct scales and event counts; raw and normalised counts never differ within a session. Across exports, names disagree for 86 of 213 scale-days in 2020-10-05..16 and 0 of 469 elsewhere, mixing language variants with genuinely different dishes.
- **Alternatives tested.** Four identity definitions (S30-S32: all identical to baseline); an alias table (rejected: the source supplies none and some differences are real dish differences).
- **Chosen approach.** Trim, whitespace collapse, case-fold; count within one session; mark cross-export component identity LIMITED for the window.
- **Why.** Normalisation beyond the string would be invented.
- **Business impact.** M4 is robust; component-level cross-day comparisons in Oct 5-16 are not offered.
- **Residual uncertainty.** Why the exports disagree in that window (Q11).

## D19. Volume irregularity is a flag, never an exclusion
*vs plan: CHANGED* · 2026-09-19
- **Decision.** `low_observed_volume_day` and `volume_irregularity` describe days and **never** remove a day or session from the KPI population. Not labelled a data error.
- **Evidence.** Registered-export days are bimodal by weekday (Mon-Wed 41-107, Thu-Fri 2-18 in baseline weeks); six days break the pattern (Nov 2, 6, 16, 17, 18, 20). Sessions on those days look ordinary.
- **Alternatives tested.** Exclude irregular days (S20: M2 +26.4 g, material); exclude Nov 16-20 (S21: +12.5 g); exclude low-volume days (S22: M1 -6 g); retain and flag (chosen). A median/MAD rule was rejected because the distribution is bimodal.
- **Chosen approach.** Fixed threshold (< 30) and weekday-regime comparison, as flags.
- **Why.** Removing days before the cause is known would hide the finding.
- **Business impact.** KPIs use the full population; the irregularity is reported openly.
- **Residual uncertainty.** The cause (Q5). The weekday baseline is four weeks of data.

## D20. Registered-export volume is not a demand signal
*vs plan: NEW* · 2026-09-19
- **Decision.** M3 makes no demand, diner, customer or traffic claim.
- **Evidence.** The non-registered export is flat at 36-75 per day; the registered export is weekday-patterned.
- **Alternatives tested.** Reading M3 as demand (rejected).
- **Chosen approach.** Counting metric only; named per D27.
- **Why.** The volume pattern reflects inclusion or scheduling we cannot explain.
- **Business impact.** Prevents an unsupported staffing or preparation inference.
- **Residual uncertainty.** Q5.

## D21. Weather join uses the hour-ending observation
*vs plan: CHANGED (Phase 0 used floor)* · 2026-09-19
- **Decision.** Ceil the session's UTC time to the next full hour.
- **Evidence.** `r_1h` error against 10-minute data: 0.021 mm (hour ending) vs 0.378 mm (hour starting), one rainy day.
- **Alternatives tested.** Floor (precipitation NULL for 58 sessions, `ri_10min` 42); ceil (67 and 25). Both match 1,697 of 1,697.
- **Chosen approach.** Ceil.
- **Why.** The observation stamped at the end of the hour covers the meal.
- **Business impact.** Weather context aligned with the meal; precipitation descriptive only.
- **Residual uncertainty.** One-day test; FMI's pages reviewed did not state the convention.

## D22. Parsing rules
*vs plan: NEW* · 2026-09-19
- **Decision.** Parse by header name; decide timestamp format per column; sort by parsed time, never row order.
- **Evidence.** 78-464 order inversions per file; one file newest-first (154 of 155 sessions); one file mixes dashed and dotted formats across columns; 7 of 11 files lack `weighting_type`.
- **Alternatives tested.** Positional parsing (breaks on the missing column); per-file format (breaks on the mixed file).
- **Chosen approach.** As stated.
- **Why.** Each failure was observed in the real files.
- **Business impact.** Sessions reconstruct identically regardless of file layout.
- **Residual uncertainty.** Future files may drift further; S08 warns on unexpected columns.

## D23. Diagnostic thresholds approved
*vs plan: NEW* · 2026-09-19
- **Decision.** B02 event ≥ 1,500 g; B07 session outside [50, 2,200] g; T05 span > 600 s; T07 median first-event hour outside [10, 11); C02 low volume < 30 sessions; C02 irregularity = weekday regime differs from the baseline regime. They are **diagnostic validation thresholds derived from observed data structure, not claims of physical impossibility or universal abnormality.**
- **Evidence.** B02 sits just above hot-scale P99.9 (1,449 g); B07 bounds are P0.5 = 56 g and P99.5 = 2,156 g; T05 falls in the gap between 545 s and 1,783 s; T07 files sit at 10.48-10.58 h vs 7.54 h; C02 daily counts gap 22 → 41.
- **Alternatives tested.** B02 at P99.9 (1,252 g; ordinary tail); B07 percentile bounds (S06 vs fixed S07: M2 -22.6 vs -19.1 g); T05 at 300 s (adds 1 session); median/MAD volume rule (mislabels Thursdays).
- **Chosen approach.** The approved values; every flag keeps the record.
- **Why.** Each sits at a natural gap or defined tail, and every result was tested in the sensitivity file.
- **Business impact.** Flags direct attention; none changes the KPI population.
- **Residual uncertainty.** Thresholds describe this five-week snapshot.

## D24. M5 uses a fixed eligible denominator
*vs plan: CHANGED* · 2026-09-19
- **Decision.** M5 = `core_ready` sessions / all registered-export session IDs in the source (**1,699**), fixed before any record is removed. Baseline 1,697 / 1,699 = **99.88%**.
- **Evidence.** The two removed sessions are the crossovers (I01).
- **Alternatives tested.** Denominator after removal (would yield 100% by construction; rejected); readiness counting WARN as failure (that is the warn-free rate, D28); crossover inclusion (S01: 100%, invalid).
- **Chosen approach.** Fixed eligible denominator; warn-free rate reported beside it with the same denominator.
- **Why.** A metric cannot be improved by shrinking its own denominator.
- **Business impact.** Readiness is honest: 2 of 1,699 sessions are excluded.
- **Residual uncertainty.** M5 is high because the registered export has few ERROR-level violations, not because it is proven perfect.

## D25. Weather-independent core, model fields and tables
See D8 and D17. *vs plan: CHANGED.* Recorded here to preserve numbering; no separate decision.

## D26. Phase 0 corrections
*vs plan: n/a* · 2026-09-19
- **Decision.** Correct earlier figures: sessions with more than one identification value = 0 (was 2); sessions over 10 minutes = 7 (was 8); same-scale repeats = 512 events in 222 sessions (was 538); `session2266` is an exact cross-export duplicate.
- **Evidence.** Phase 0 pooled the crossover pairs across populations.
- **Alternatives tested.** Leaving the figures. **Chosen approach.** Re-profile per (`session_id`, `population`). **Why.** Accuracy.
- **Business impact.** None on KPIs. **Residual uncertainty.** None.

## D27. M3 is named "Observed Valid Sessions — Registered-Export Population"
*vs plan: CHANGED* · 2026-09-19
- **Decision.** M3 (formerly "Valid Dining Session Volume") uses this name and is never described as demand, diners, customers or traffic.
- **Evidence.** D20.
- **Alternatives tested.** "Valid Dining Session Volume" (implies demand).
- **Chosen approach.** New name; baseline 1,697.
- **Why.** The name should carry the limitation.
- **Business impact.** Avoids over-reading a count.
- **Residual uncertainty.** Q5.

## D28. Warn-free rate: the canonical figure is session-level 97.88%; the event-level 97.70% is a reconciled diagnostic
*vs plan: NEW* · 2026-09-19, revised on review 2026-09-19
- **Decision.** Canonical Warn-free Rate = eligible registered-export sessions with **no session-level WARN** (B04, B07, T04, T05, I06) / fixed 1,699 = **1,663 / 1,699 = 97.88%**. The event-level variant (also counting B02 and I02) = 1,660 / 1,699 = 97.70% is reported as a diagnostic and **does not replace** the canonical figure.
- **Evidence.** Three sessions carry an event-level WARN and no session-level WARN: `session320` and `session1116` (B02, events at or above 1,500 g) and `session1274` (I02 duplicate row).
- **Alternatives tested.** Session-level only (97.88%, chosen, as approved); session plus event level (97.70%). I proposed the latter as the headline because my documented definition was "no WARN rule" and B02/I02 are WARN rules. Review kept 97.88% and required an explicit reconciliation before any replacement.
- **Chosen approach.** 97.88% canonical. Reconciliation: population = registered-export; denominator = 1,699 (fixed, before removal); 1,699 = 1,663 (no session-level WARN) + 34 (session-level WARN) + 2 (quarantined crossover); rule = session-level WARN rules; 1,663 - 3 event-level-only sessions = 1,660 (97.70%).
- **Why.** The approved figure has a precise, testable definition and the variant is fully disclosed, so nothing is hidden in either direction.
- **Business impact.** The two figures differ by 0.18 percentage points (three sessions); neither changes a conclusion.
- **Residual uncertainty.** Which WARN rules belong in "warn-free" is a definition. It is now stated in `metric_contract.md`; changing it requires a decision-log entry and a golden-value update.

## D29. Thresholds are diagnostic, not physical
See D23. *vs plan: NEW* · 2026-09-19. Recorded separately so the wording is not lost: no output describes a flagged value as impossible, erroneous or abnormal in general; it is "flagged by a threshold derived from this dataset".

## D30. Sensitivity analysis is a pipeline output
*vs plan: NEW* · 2026-09-19
- **Decision.** `outputs/validation/sensitivity_analysis.csv` recomputes M1-M5 under alternative assumptions on every run.
- **Evidence.** 25 scenarios run in Phase 2: baseline (1); crossover inclusion (3); outlier and threshold exclusions including the 2,097 g removal (7); timezone hypotheses (5); volume diagnostics (4); definition tests (4); the diagnostic population (1).
- **Alternatives tested.** Reporting only the baseline (rejected: cannot show assumptions were not selected for favourable results).
- **Chosen approach.** One CSV, baseline row equal to headline KPIs, a diagnostic materiality convention (|ΔM1| ≥ 10 g, |ΔM2| ≥ 25 g, or ΔM4 ≠ 0).
- **Why.** Testing is the evidence.
- **Business impact.** Findings: M1 493-505 g and M4 = 5 everywhere; M2 977-1,066 g; the timezone choice cannot be distinguished among +2h/+3h/+4h by KPIs.
- **Residual uncertainty.** The materiality convention is a display aid, not a significance test.

## D31. The product is a measurement-reconstruction pipeline
*vs plan: CHANGED (plan called it a data product / evidence pipeline)* · 2026-09-19
- **Decision.** The PRD defines LAST TRAY as "a dependable measurement-reconstruction pipeline", not a dining-analytics pipeline.
- **Evidence.** Most of the work was reconstruction, not analysis: events into sessions, populations apart, a clock investigated, schema and names reconciled, assumptions tested.
- **Alternatives tested.** "Dining analytics pipeline" (overstates what the data supports).
- **Chosen approach.** New definition in PRD §1.
- **Why.** It describes what the system does.
- **Business impact.** Sets the right expectation: this tells the client what it can trust, not how much food is wasted.
- **Residual uncertainty.** None.

## D32. Repository structure for implementation: research/phase2, config/, golden fixtures
*vs plan: NEW* · 2026-09-19
- **Decision.** The Phase 2 investigation scripts move to `research/phase2/` (historical evidence, README, never imported by `src/`); production code lives in `src/`; judgement lives in `config/*.yml`; the Phase 2 outputs are frozen as regression fixtures in `tests/golden/`.
- **Evidence.** Moving the scripts exposed two reproducibility defects that were fixed and recorded: one script read weather from a scratch pickle in a temp folder, and one output serialised Python `set` values whose order depends on the hash seed. After the fix, two runs under different `PYTHONHASHSEED` values gave byte-identical outputs.
- **Alternatives tested.** Leaving scripts in `notebooks/` (blurs research and product); deleting them after the pipeline exists (loses the evidence trail).
- **Chosen approach.** Keep them, move them, prove they still reproduce (hash comparison before and after; the only differences were three intended ones, listed in `research/phase2/README.md`).
- **Why.** The production pipeline must be checkable against an independent investigation.
- **Business impact.** A reviewer can see how each design decision was reached and re-run it.
- **Residual uncertainty.** Phase 0 source discovery was interactive and has no script; it is documented in `source_inventory.md` and the committed raw artefacts.

## D33. The project lives in its own git repository, outside the home-directory repository
*vs plan: NEW* · 2026-09-19
- **Decision.** The project was copied to a dedicated directory outside that repository, initialised with `git init` and `git branch -M main`. No public repository exists yet.
- **Evidence.** `git rev-parse --show-toplevel` from the original folder returned the user's home directory: the project sat inside an unrelated home-directory repository whose status listed thousands of untracked personal files.
- **Alternatives tested.** `git init` inside the original folder (would nest a repository inside the home one); working in place (would expose personal files to any `git add`).
- **Chosen approach.** Copy (not move) to a directory outside the home repository; leave `MOVED.txt` in the old folder; do not create a public GitHub repository until the licence, secrets and raw-data audit.
- **Why.** The submission needs a clean, self-contained repository, and personal files must never be one careless command from publication.
- **Business impact.** A reviewer clones exactly the project and nothing else.
- **Residual uncertainty.** The original folder remains as a frozen backup and should be deleted by its owner once the new location is accepted.

## D34. Normal execution is offline; retrieval is an explicit, separate command
*vs plan: CHANGED (plan §35 had retrieval inside the pipeline)* · 2026-09-19
- **Decision.** `python -m src.pipeline.run` never downloads. A missing raw source fails clearly and names `python -m src.pipeline.fetch --source <flavoria|weather>`.
- **Evidence.** Reproducibility must not depend on Zenodo or FMI being reachable; raw files are small (about 4 MB) and committed.
- **Alternatives tested.** Implicit download of missing files (rejected: hides a changed input); an `--offline` flag on a network-by-default run (rejected: reproducibility would depend on a flag being remembered).
- **Chosen approach.** Offline by construction. Enforced three ways: every socket operation forbidden in tests; `requests` made unimportable in a subprocess run; a static import walk proving the run path reaches no network module.
- **Why.** A reproducibility run should not have a reason to touch the network, so it cannot.
- **Business impact.** The assignment reproduces on an aeroplane.
- **Residual uncertainty.** None.

## D35. Pins are governance: mismatches FAIL, and a refreshed source is a new snapshot
*vs plan: NEW* · 2026-09-19
- **Decision.** Size, checksum and row-count mismatches are FAILED. The pipeline never re-downloads and never edits a pin. A refreshed source is retrieved explicitly into its own `refresh-<time>/` directory with a `snapshot.json`; adopting it is a human edit of `config/sources.yml` plus a decision-log entry.
- **Evidence.** A real retrieval on 2026-09-18 returned byte-identical Flavoria data but FMI responses whose bytes differ every time (each embeds its generation time) while their parsed content is identical.
- **Alternatives tested.** Pinning FMI by bytes only (a re-fetch could never be verified); pinning by content only (would ignore tampering with committed bytes); both (chosen).
- **Chosen approach.** Pin bytes (SHA-256) and, for weather, a content signature. Weather retrieval always yields a new snapshot and reports whether the content is identical to the pin.
- **Why.** A pin that can be silently refreshed is not a pin.
- **Business impact.** Any change to an input is visible, deliberate and recorded.
- **Residual uncertainty.** The Zenodo record is versioned and static; FMI may in principle revise historical observations, which a content-signature mismatch would reveal.

## D36. The +3h normalization is file-specific and scope-checked (rule T10)
*vs plan: CHANGED* · 2026-09-19
- **Decision.** Model the normalization as file-specific, evidence-backed and not source-confirmed, with a validity scope: the named file, event dates 2020-10-05..16, raw median first-event hour in [7.0, 8.5], and a post-normalization median inside the T07 band. Ingestion FAILS the core lane if any of these does not hold. No documentation describes Helsinki generally as UTC+3.
- **Evidence.** The offset scan, the exact 10,800 s on `session3222`, and the observed raw 7.54 h and normalised 10.54 h medians.
- **Alternatives tested.** A registry key alone (a corrected file under the same name would be silently shifted by 3 h to about 13:30); a DST-aware UTC-to-Helsinki conversion (implies knowledge of the file's true zone that we do not have).
- **Chosen approach.** Fixed +3h for one file, with a scope check.
- **Why.** An assumption that cannot detect its own invalidity is a trap.
- **Business impact.** KPIs are unaffected (weights and dates are timezone-independent); time-of-day and weather-join outputs are protected from a silent error.
- **Residual uncertainty.** The source owner has not confirmed the timezone (Q3).

## D37. Provenance and attribution: snapshot identifiers, NOTICE, data_provenance.md
*vs plan: NEW* · 2026-09-19
- **Decision.** Every source-derived record carries a `source_snapshot_id`; `NOTICE` and `docs/data_provenance.md` state provider, URL, version, licence, retrieval date and attribution.
- **Evidence.** Zenodo record: CC BY 4.0, open access. FMI: the official licence page https://en.ilmatieteenlaitos.fi/open-data-licence, read 2026-09-19, states "Creative Commons Attribution 4.0 International license (CC BY 4.0)" and prescribes no attribution wording. The Flavoria catalogue pages state no terms.
- **Alternatives tested.** Recording "Creative Commons" without a version (rejected: guessing); assuming the catalogue is freely reusable (rejected: no terms found).
- **Chosen approach.** Verified facts only; where a fact is not established (FMI wording, catalogue terms, code licence) the document says so. A test compares the documents with the pins and with a real run.
- **Why.** Attribution errors are the easiest way to undermine an otherwise honest submission.
- **Business impact.** The public repository can be created after the final audit without a licence surprise.
- **Residual uncertainty.** Code licence undecided; Flavoria catalogue terms unknown (only short quotations are used).

## D38. Golden tests separate structural invariants from floating-point values
*vs plan: NEW* · 2026-09-19
- **Decision.** Structure (counts, partitions, reconciliations, identities) is asserted exactly with integers in `test_golden_invariants.py`; metric values are asserted with explicit tolerances in `test_golden_metrics.py`. A floating-point representation issue is never a business rule.
- **Evidence.** Values such as 1039.6 and 97.88 are rounded publications of quotients; exact float equality would fail for representation reasons unrelated to any business rule.
- **Alternatives tested.** Exact equality everywhere (brittle, and would tempt rounding hacks); tolerances everywhere (would blur exact structural facts such as 1,699 = 1,697 + 2).
- **Chosen approach.** Two files. Tolerances are published (`tolerances:` in `golden_values.yml`): M2 0.05 g, percent 0.005.
- **Why.** A failing test should mean a business fact changed.
- **Business impact.** Fewer false alarms and no rounding workarounds.
- **Residual uncertainty.** None.

## D39. All staging reads go through the verified reader
*vs plan: NEW* · 2026-09-19
- **Decision.** Staging obtains raw bytes only from `VerifiedReader`, which re-checks the SHA-256 recorded at ingestion on every read. No downstream stage opens `data/raw`. A failed verification stops that source's staging path.
- **Evidence.** A raw file can change between ingestion and staging; without a re-check, staging would consume unverified bytes.
- **Alternatives tested.** Staging reading raw by path after an upfront check (a time-of-check to time-of-use gap); trusting the handoff alone (a forged or stale handoff could not be detected).
- **Chosen approach.** One reader interface; static tests forbid file-access and network imports in the staging package; a fake reader proves it is the only input; failure removes stale outputs and reads no further members.
- **Why.** Verified data should be the only data that can reach a table.
- **Business impact.** A tampered or corrupted source can never silently produce a staging table that looks current.
- **Residual uncertainty.** The reader trusts the handoff's recorded hashes; the handoff file itself is not signed.

## D40. Timestamps keep raw text, a canonical UTC instant, and how the zone was handled
*vs plan: CHANGED (Phase 2 stored only a normalised local time)* · 2026-09-19
- **Decision.** Every staged timestamp carries `*_raw`, `*_local`, `*_canonical_utc`, a status, and `timezone_handling` with a `timezone_transformation_reason`. Source-local files are converted with Europe/Helsinki zoneinfo rules; ambiguous and nonexistent local times are NULL, never guessed. The +3h is file-specific and `NORMALISED_PLUS_3H_STRONGEST_SUPPORT`; UTC+3 is never a general Helsinki assumption. Renamed `timezone_normalization` to `timezone_handling`.
- **Evidence.** The study crosses the 2020-10-25 clock change: the same wall time maps to a different UTC hour before and after (offsets +3 h then +2 h). All 12,284 canonical timestamps equal an independent pandas computation; zero events fall in an ambiguous or nonexistent hour.
- **Alternatives tested.** A fixed +3h for all files (wrong after the change); dropping the raw text (unrecoverable normalization); guessing the fold for the repeated hour (fabricates a fact).
- **Chosen approach.** As stated.
- **Why.** Raw text preserves evidence; canonical UTC makes files and FMI comparable; the handling label keeps the assumption visible.
- **Business impact.** Weather joins and time-of-day analysis rest on explicit, reproducible instants.
- **Residual uncertainty.** The source-local zone remains an assumption; the override is not source-confirmed (Q3).

## D41. Staging preserves and normalises; it does not judge
*vs plan: NEW* · 2026-09-19
- **Decision.** Every source row is staged: duplicates, zero or huge weights, unparseable timestamps and ragged rows are kept as found and marked with statuses. Deduplication, quarantine and thresholds belong to validation (WP4).
- **Evidence.** The 2,097 g event, the two exact duplicate rows and 398 edge-whitespace names are all present and counted in staging; a `weighting_type` defect (0 rows read instead of 5,294) was caught by reading the summary, not by an assumption.
- **Alternatives tested.** Filtering at staging (would hide evidence and make validation counts unreproducible).
- **Chosen approach.** Keep everything; typed columns sit beside raw text.
- **Why.** Validation is evidence, not cleaning.
- **Business impact.** The Phase 2 issue counts can be reproduced from staging.
- **Residual uncertainty.** None.

## D42. The first commit is validated from a clean checkout, and raw data is stored byte-exact
*vs plan: NEW* · 2026-09-19
- **Decision.** The baseline was committed only after a secrets, privacy and scratch-file audit. A `.gitattributes` marks `data/raw/**` as binary and stores other text with LF.
- **Evidence.** The audit found two pickles, a scratch log, one personal path and two `.gitignore` inline comments that silently matched nothing. A fresh clone with `core.autocrlf` on then grew every weather XML by 6-8 KB, and the pipeline correctly reported SIZE_MISMATCH and blocked the weather lane; after the fix a clean clone verified all 21 artifacts with the identical input fingerprint and 216 tests passed.
- **Alternatives tested.** Trusting the working tree; normalising line endings in raw files (would invalidate the pins).
- **Chosen approach.** Fix in a new commit rather than rewrite history.
- **Why.** Reproducibility must survive a checkout on another machine.
- **Business impact.** A reviewer on Windows gets the same result as on any other system.
- **Residual uncertainty.** The original backup folder still exists and should be deleted by its owner.

## D43. Output tracking policy for staging
*vs plan: NEW* · 2026-09-19
- **Decision.** The large regenerable staging tables (`outputs/staging/stg_*.csv`, about 10 MB) are ignored by git; `staging_summary.json` and `staging_file_reconciliation.csv` are tracked. The summary records output checksums, so a reviewer can verify a regenerated table against it.
- **Evidence.** The events table is about 9 MB and fully reproducible from committed raw data.
- **Alternatives tested.** Committing the tables (repository bloat); committing nothing (no reviewable evidence).
- **Chosen approach.** Track the small, reviewable artefacts; ignore the large regenerable ones.
- **Why.** The repository should hold evidence, not build products.
- **Business impact.** A small, reviewable repository.
- **Residual uncertainty.** None.

## D44. Validation reads only staging tables it can verify
*vs plan: NEW* · 2026-09-19
- **Decision.** `src/validate` consumes the staging tables through one loader that first checks the staging summary (core lane OK), then each table's SHA-256, header and row count against what staging recorded. A missing, altered or truncated table stops the core lane (exit 4) and deletes the validation outputs from any earlier run. A damaged weather table blocks the weather checks only. No validation module imports a raw reader, an archive or a network library, and none names `data/raw`.
- **Evidence.** Tests alter one byte, truncate the table, drop the last row and re-sign the summary, delete the summary, and mark staging FAILED; every case stops validation. An AST test bans the imports and a spy test shows every file opened is under `staging/`.
- **Alternatives tested.** Re-reading raw bytes through the verified reader (breaks the stage boundary); trusting the CSVs without a checksum (a stale or edited table would validate silently).
- **Chosen approach.** Verify, then load typed rows; never repair.
- **Why.** Validation is evidence about staging. Evidence built on an unverified table is not evidence.
- **Business impact.** A reviewer can trust that a finding describes the staged data that was checksummed.
- **Residual uncertainty.** The checksum proves the table is what staging wrote, not that staging was right; WP3 tests cover that.

## D45. Quarantine is a list and a flag at session-key grain; nothing is deleted
*vs plan: NEW* · 2026-09-19
- **Decision.** Only ERROR rules whose handling is QUARANTINE (S05, S06, S07, B01, T01, T03, I01, I04) quarantine. The unit is the `(session_id, population)` key, because `core_ready` is defined per session: an ERROR on any event quarantines its whole session key. Every staged event receives exactly one disposition (`QUARANTINED`, `DUPLICATE_EXCLUDED`, `MODELLABLE`), quarantined rows are listed one by one in `quarantine_manifest.csv`, and `events_in = modelled + duplicates_excluded + quarantined` is checked (rule C04, ERROR, BLOCK).
- **Evidence.** The real data has four ERROR findings (I01 on `session2266` and `session3222`, both populations), 22 quarantined events, 2 excluded repeats and 12,260 modellable events, which sum to 12,284. A test breaks the partition and confirms C04 and a BLOCKED core lane.
- **Alternatives tested.** Quarantining single events (a session with one bad weight would still be summed into a wrong meal weight); dropping quarantined rows from the tables (violates "never silently delete").
- **Chosen approach.** Flag, list, exclude from the primary population later, keep everywhere.
- **Why.** The approved decision keeps both crossover versions and picks neither.
- **Business impact.** M5's numerator can exclude exactly the quarantined keys, and a reviewer can find every row involved.
- **Residual uncertainty.** Event-level quarantine rules never fired on real data, so their session-level effect is proven on synthetic rows only.

## D46. The rule catalogue takes severity and handling from configuration; new rule ids are additive
*vs plan: NEW* · 2026-09-19
- **Decision.** `src/validate/model.py` holds one catalogue. For rules configured in `config/thresholds.yml` (B02, B03, B07, T03, T05, T07, C02a, C02b) severity and handling come from the configuration. Approved rule ids are unchanged. Added ids: C04 (already specified), X07 (weather station-hour-parameter grain, ERROR, BLOCK the weather lane), X08 (a weather hour lacks a parameter, WARN). One rule, I06, legitimately has two severities (identical versions are INFO, disagreement is WARN), so an issue may carry a severity override; no other rule does.
- **Evidence.** A test changes B02 to ERROR/QUARANTINE in a copy of the configuration and the output follows; another proves only ERROR rules ever quarantine and B06 does not exist.
- **Alternatives tested.** Hard-coding severities in the rules (configuration and code could drift); renaming the Phase 2 rule C02 (the specification already splits it into C02a and C02b).
- **Chosen approach.** Configuration is the single source; the catalogue adds only the consequence text.
- **Why.** Thresholds are diagnostic and approved as configuration, so they must stay reviewable there.
- **Business impact.** No threshold can be silently changed in code.
- **Residual uncertainty.** None.

## D47. Reconciliation has four statuses, and partial weather coverage warns rather than blocks
*vs plan: NEW* · 2026-09-19
- **Decision.** `reconciliation_summary.csv` rows are PASS (expectation held), WARN (a documented shortfall that does not block, e.g. weather hours missing), FAIL (an expectation broke; the affected lane blocks) or INFO (a fact, no expectation). Expectations come from the pins in `config/sources.yml` or from identities that hold by construction; the golden values are compared by tests only.
- **Evidence.** 46 checks on the real data: 35 PASS, 0 WARN, 0 FAIL, 11 INFO. A weather table missing one hour produces X01 and WARN; an empty one FAILS.
- **Alternatives tested.** Treating any weather shortfall as a block (contradicts X01, "weather outputs BLOCKED if empty").
- **Chosen approach.** Match the approved severity of each rule.
- **Why.** Weather is context, never a reason to stop the core lane.
- **Business impact.** A weather gap cannot hide a core result or stop it.
- **Residual uncertainty.** None.

## D48. Output tracking and identity for validation
*vs plan: NEW* · 2026-09-19
- **Decision.** Issue ids are content-derived (`vi-` plus a hash of rule, entity type and entity id) and must be unique; `run_id` is derived from the staging fingerprint, the table checksums and the rule catalogue, so outputs contain no wall-clock time and are byte-identical across runs, hash seeds and working directories. The 1.8 MB `event_validation_status.csv` is ignored by git; the issues, summaries, manifests and day/session tables are tracked. The Phase 2 exploration `validation_issues.csv` and `validation_summary_by_rule.csv` are replaced by the production files; their frozen copies stay in `tests/golden/`.
- **Evidence.** Two processes with different `PYTHONHASHSEED` values and directories write identical bytes for all nine files.
- **Alternatives tested.** Sequential issue numbers (an added finding renumbers all later ones); a wall-clock run time (breaks byte-identical reruns).
- **Chosen approach.** Identity from content.
- **Why.** Reproducibility and stable references in reviews.
- **Business impact.** A finding can be cited by id across runs.
- **Residual uncertainty.** None.

## D49. The model consumes only verified inputs; WP4 outputs now record their checksums
*vs plan: NEW* · 2026-09-19
- **Decision.** `src/model` reads the verified staging tables and the WP4 validation outputs, nothing else, and never opens `data/raw`. It refuses to build unless each WP4 file matches the SHA-256 recorded in `validation_summary.json`, that summary records the same staging checksums as the tables present, the disposition file lists exactly the staged events, and the quarantine manifest agrees with the summary. To make this possible WP4 now writes `output_sha256` into its summary (an additive change: no rule, threshold or output value changed).
- **Evidence.** Tests alter one byte of each WP4 file, delete the summary, point it at other staging checksums, drop an event from the dispositions, add an unknown disposition and remove a quarantine row; every case stops the model and removes stale canonical tables.
- **Alternatives tested.** Trusting the WP4 files without a checksum (a stale or edited file would be modelled silently); recomputing WP4's decisions inside the model (would duplicate and could contradict the validation layer).
- **Chosen approach.** Verify, then consume.
- **Why.** The model must be a faithful consequence of what was validated.
- **Business impact.** A number in the canonical model can be traced to a checksummed validation decision.
- **Residual uncertainty.** A consistent forgery of a WP4 file and its recorded checksum is caught only if it changes a figure the model recomputes independently (weights, spans, counts, dispositions); tests cover that.

## D50. The selected meal weight is reconstructed independently; WP4's value is only a control
*vs plan: NEW* · 2026-09-19
- **Decision.** `derived_selected_meal_weight_g` is the sum of `component_weight_g` over the session's MODELLABLE events, computed from `fact_weighing_event` rows; it is NULL (never 0) if there is no modellable event or any modellable weight is invalid. It is compared with WP4's `rule_weight_sum_g` for every session. Any difference blocks the model, publishes no canonical rows, and is listed by session in `session_weight_control.csv`. A quarantined session has no canonical weight (its events stay, with their observed weights, marked QUARANTINED). The Phase 4 wording "sum over non-duplicate events" is refined to MODELLABLE events, which is the same set for every non-quarantined session.
- **Evidence.** All 3,341 non-quarantined sessions match WP4 exactly and match an independent pandas recomputation; the four quarantined keys are EXCLUDED_QUARANTINED; a forged WP4 weight blocks the model and names exactly that session.
- **Alternatives tested.** Copying `rule_weight_sum_g` (would make the control meaningless); summing quarantined sessions and relying on `core_ready` to filter (contradicts "quarantined data must not be treated as core-ready selected weight").
- **Chosen approach.** Two independent computations that must agree.
- **Why.** The central business figure should not depend on one code path.
- **Business impact.** M1 and M2 can be computed in WP6 from a value that has already been cross-checked.
- **Residual uncertainty.** The crossover-inclusion sensitivity scenario (WP7) must rebuild those weights from the QUARANTINED event rows, which are all preserved.

## D51. Two event sets, on purpose
*vs plan: NEW* · 2026-09-19
- **Decision.** Business fields (weight, distinct component counts, component rows, modellable count) use MODELLABLE events only. Timing and identity fields (first and last weighing, span, service date, tray, identification time) use every event that is not an exact repeat, so a quarantined session remains traceable in time but yields no weight and no component count. `fact_session_component` therefore holds only modellable events and has 11,925 rows.
- **Evidence.** For all 3,341 non-quarantined sessions the two sets are identical; the difference exists only for the four quarantined keys.
- **Alternatives tested.** Nulling all fields of a quarantined session (loses traceability); populating everything (invites use of quarantined values).
- **Chosen approach.** Traceable, but not usable for business figures.
- **Why.** Quarantine is a list and a flag, not a deletion, and not a licence to use the data.
- **Business impact.** None for the headline figures.
- **Residual uncertainty.** None.

## D52. The weather join lives in the model and follows the approved hour-ending convention
*vs plan: was deferred from WP4* · 2026-09-19
- **Decision.** `fact_weather` is one row per station and UTC hour (1,129 rows), with each parameter's text exactly as FMI states it, NULL where FMI reports NaN, and a per-parameter status (OK, NAN_SOURCE_NULL, MISSING). A session joins the observation stamped at the next full UTC hour after its first weighing (an exact hour keeps itself), because `r_1h` covers the hour ending at its timestamp. Quarantined sessions are `NOT_ATTEMPTED_QUARANTINED`; an unmatched session stays valid; a weather grain violation or an unavailable weather table blocks `fact_weather` only (status `WEATHER_BLOCKED`), never the core model. Weather never enters `core_ready`.
- **Evidence.** 1,697 of 1,697 core-ready sessions match; the matched hours carry NULL `r_1h` for 67 sessions and NULL `ri_10min` for 25, as in Phase 2; the join hour equals an independent pandas ceiling of the first weighing.
- **Alternatives tested.** Flooring to the hour (Phase 2 showed it mis-assigns `r_1h`); interpolating or backfilling NaN (invents data).
- **Chosen approach.** Join, flag, never fill.
- **Why.** Weather is context; a weather gap must not change a business figure.
- **Business impact.** None yet; no weather conclusion is drawn in WP5.
- **Residual uncertainty.** The hour-ending reading of `r_1h` was verified empirically on one rainy day, not documented by FMI.

## D53. The schema is code; readiness is prepared, not computed
*vs plan: NEW* · 2026-09-19
- **Decision.** `src/model/schema.py` declares every table, grain, column, type, class, nullability, lineage rule and downstream use. CSV headers, the manifest and data-dictionary section 12 come from it, and a test fails on drift. Names changed from the Phase 4 plan are recorded: `component_weighing_event_count` is `modellable_event_count`; `first_weighing_at` and `last_weighing_at` are split into local and UTC columns; `session_key`, dispositions, weather join status, quarantine and severity fields were added. `core_ready` follows the approved contract (primary population, not quarantined, at least one modellable event, no ERROR finding, valid weights, parsed times; weather, WARN rules and volume flags never enter it) and equals 1,697 of 1,699 eligible sessions. The metrics M1-M5 and the warn-free rate are not computed here.
- **Evidence.** The readiness numerator and denominator are reported as an INFO control only; `has_session_warn` and `has_event_warn` reproduce the golden 34 / 1,663 accounting.
- **Alternatives tested.** A hand-written data dictionary (drifts); computing M5 in the model (a metric belongs to WP6).
- **Chosen approach.** Declare once, generate the rest.
- **Why.** Documentation that cannot drift from the code.
- **Business impact.** A reviewer can read one table and trust it.
- **Residual uncertainty.** None.
