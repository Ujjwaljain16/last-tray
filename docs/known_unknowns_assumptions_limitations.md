# Known / Unknown / Assumptions / Limitations

I keep four buckets here, and I keep them separate on purpose: what I know for a fact, what nobody has ever measured, what I assumed and why, and where this whole project stops working. Every item below cites where the evidence actually lives, so nothing here is just my word for it. Sensitivity results come from `outputs/evidence/uncertainty_register.csv` and `docs/sensitivity_analysis.md`.

**Population labels** ("registered-export population", "non-registered-export population") are **inherited from source file names**. The public documentation I reviewed for this project never defines their business meaning, so I use them only as population labels, nothing more.

## KNOWN (things I verified from primary sources or the raw files myself)

| # | Statement | Evidence |
|---|---|---|
| K1 | Event-level weight exists: 12,284 component weighing events, 3,343 session IDs, 687 trays, 30 scales, 246 raw component names | `research/exploration/README.md`, `outputs/ingestion/` |
| K2 | Session reconstruction is possible: grouping by `session_id` within one population gives 3,345 session keys, none with more than one tray or more than one identification time | `docs/source_truth_decisions.md`, `outputs/model/fact_dining_session.csv` |
| K3 | A selected meal weight can be reconstructed as the sum of component events; 1,697 of 1,699 registered-export sessions are core-ready (M5 99.88%) | `outputs/metrics/metrics.csv` |
| K4 | Weather alignment is available for the core-ready registered-export sessions: all 1,697 core-ready sessions match an FMI hour (S1 99.88% of the 1,699 eligible) | `outputs/metrics/metrics.csv`, `outputs/model/fact_weather.csv` |
| K5 | Two session IDs, `session2266` and `session3222`, appear in both exports; both versions of each are quarantined | `outputs/validation/quarantine_manifest.csv` |
| K6 | The dataset is open, CC BY 4.0, v1.0.0, DOI 10.5281/zenodo.5850856; the CSV archive matches Zenodo's MD5 and the pinned SHA-256 | `docs/data_provenance.md` |
| K7 | Coverage is 35 weekday service days, 2020-10-05 to 2020-11-20 | profile |
| K8 | No total-meal-weight column and no waste column exists in any of the 11 files | headers, `outputs/ingestion/schema_fingerprints.csv` |
| K9 | The public waste sample is documented as `"TODO, Ask!"`; no download, API, schema or contact is published | Flavoria waste page, updated 2026-04-09 |
| K10 | Weigh & Dine records a checkout plate total (±5 g) and has no component weights; it is a different system from the public CSV | Flavoria Weigh & Dine page |
| K11 | FMI weather is retrievable with no key: 1,129 hourly rows for Turku Artukainen (FMISID 100949), 3 NULL precipitation values; `r_1h` is the hour ending at its timestamp (one-day test: error 0.021 mm versus 0.378 mm) | `data/raw/weather/`, `research/exploration/exploration_f_fmi_semantics.py` |
| K12 | One file's timestamps are offset by exactly 10,800 s from the same session in the other export; +3h makes its hour-of-day profile match the other registered-export files (distance 0.046 versus 1.994) | `docs/source_truth_decisions.md`, `decision_log.md` D4 |
| K13 | The populations differ: 1.0% versus 37.7% single-event sessions, 97% versus 75% with a hot dish, median derived weight 499 g versus 192 g | `docs/source_truth_decisions.md`, `decision_log.md` D5 |
| K14 | Schema drift: 7 of 11 files lack `weighting_type`; two timestamp formats; row order is not chronological | `research/exploration/exploration_a_schema_population_tz.py` |
| K15 | Repeated weighings on one scale in a session are additive scoops (100% same name, 93.8% within 30 s) | `research/exploration/exploration_b_sessions_components_volume.py` |
| K16 | The M4 median is 5 under raw names, normalised names, scales and event counts | `research/exploration/exploration_b_sessions_components_volume.py`, `outputs/evidence/` |
| K17 | Across the registered scenarios (the forbidden pooling guardrail G01 and the diagnostic population contrast are excluded from every range) M1 stays within 493-505 g and M4 is 5; M2 ranges 977-1,066 g | `docs/sensitivity_analysis.md` |

## UNKNOWN (nothing I have a source for)

| # | Statement | Consequence |
|---|---|---|
| U1 | How much food was **consumed**. It is never measured anywhere we can see | selected weight cannot be read as intake |
| U2 | How much food was left over | no leftover or plate-return data |
| U3 | **Actual food waste.** The waste source is documented but not publicly accessible in the required usable form | W1 is BLOCKED / SOURCE GAP |
| U4 | Whether a session is one person or a repeat visit | a session is not a person |
| U5 | What was taken outside a weighed station | selected weight may be a lower bound |
| U6 | Whether the lunch-line scales are tared for plates or trays | interpretation of the derived weight |
| U7 | Whether the public research capture reflects all operational behaviour; whether the 11 files are the complete export for those weeks | results describe this capture only |
| U8 | What the two population labels mean | KPIs limited to one export |

Here's what I'd actually ask the source owner, if I could:

| # | Question | Effect if unresolved |
|---|---|---|
| Q1 | What do the two filename labels mean? | KPIs limited to the registered-export population |
| Q2 | Why do 37.7% of non-registered-export sessions have one event and 28% weigh under 50 g? | that population stays diagnostic |
| Q3 | Is the source timezone of the dotted file UTC? | +3h remains strongest-supported, not confirmed |
| Q4 | Which record is authoritative for `session2266` and `session3222`? | both stay quarantined |
| Q5 | Why is registered-export daily volume weekday-patterned, and why does it break on Nov 2, 6, 16, 17, 18, 20? | M3 stays "observed sessions"; flagged days retained |
| Q6 | Why does the non-registered-export export end on 2020-11-13? | diagnostic coverage 30 of 35 days |
| Q9 | Are plates or trays tared? Are readings above 1,500 g genuine portions or artefacts? | six flagged events; effect on M1/M2 at most 3.0 g |
| Q11 | Why do the exports disagree on component names for 40.4% of shared scale-days in 2020-10-05..16 and 0% elsewhere? | component comparison for that window is LIMITED |
| Q12 | Do the 7 sessions over 600 s merge two tray passes? | 7 flagged sessions (0.4%) |
| Q13 | Are single-event registered-export sessions genuine or partial captures? | 17 flagged sessions (1.0%), effect on M1 +2 g |

## ASSUMPTION (each one isolated so I can change it in a single place)

| # | Assumption | Why it matters | Evidence supporting it | Sensitivity result | Where isolated |
|---|---|---|---|---|---|
| A1 | The filename labels identify two separable exports; no meaning is assumed beyond that | pooling changes every headline number | the exports differ in weight (median 499 g versus 192 g) and structure | the diagnostic non-registered-export profile is M1 192 g, M2 855.4 g, M4 2; the forbidden pooled comparison gives M1 413 g, a population-mix artifact | `config/populations.yml` |
| A2 | `registered_2020_10_05-2020_10_18.csv` is in UTC and is normalised by +3h; all other files are Europe/Helsinki local time. Strongest-supported, **not source-confirmed** | time of day, the service-hours rule, the weather join and readiness for 385 sessions | exact 10,800 s difference on the shared `session3222`; median first-event hour 7.54 h raw and 10.54 h after +3h against 10.53 h for the other files | +2h, +3h and +4h give identical M1-M5; +0h quarantines 303 sessions (M5 82.05%); +1h quarantines 103 (M5 93.82%) | `config/timezone_overrides.yml` |
| A3 | Events sharing a `session_id` within one population belong to one tray pass (session reconstruction rule) | session weights and counts | 0 sessions with more than one tray; 7 sessions over 10 minutes are flagged | the two crossover sessions change M2 by +2.8 g at most | rules T04, T05 |
| A4 | Summing component events approximates what was placed on the tray | the meaning of M1 and M2 | scales weigh each component as placed; repeats behave as additive scoops | not testable against a checkout total (unavailable); duplicates-included definition tested | naming (`derived_selected_meal_weight_g`), rule B05 |
| A5 | The normalised name (trim, whitespace, case-fold) identifies a component within a session; no alias table | M4 | raw and normalised counts never differ within a session | M4 is 5 with raw names, 5 counting scales and 5 counting events | `component_id_normalized` |
| A6 | FMI Turku Artukainen represents outdoor conditions well enough for a context flag | S1 and any weather comparison | nearest station returned for Turku, about 6 km away (approximate) | all 385 shifted-file sessions join a different weather hour under other timezone hypotheses (mean 1.231 C for +0h); core metrics unaffected | `fact_weather` |
| A7 | Weather for a session is the observation stamped at the end of the hour containing its first weighing | alignment | `r_1h` is hour-ending (K11) | up to one hour of misalignment | TRD 7.8 |
| A8 | The weekday volume pattern (Mon-Wed high, Thu-Fri low) describes the baseline weeks, not a rule | volume flags | 4 weeks, clean separation | excluding the six irregular days removes 252 sessions and moves M2 by +26.4 g (+2.5%), M1 by +6 g | TRD 7.9; flags never exclude |
| A9 | The diagnostic thresholds (B02, B07, T05, T07, C02) describe this data and are not physical limits | which records are flagged | derived from the observed distribution | applying B07 as an exclusion moves M2 by -19.1 g; any WARN as an exclusion by -24.6 g | `config/thresholds.yml` |
| A10 | The five study weeks represent the measurement profile | the width of M2's range | the only public window | excluding the first two weeks moves M2 by -62.6 g (-6.0%); M1 by +6 g | full window kept; M2 quoted with its range |

## LIMITATION

These are the boundaries of what this project can honestly say, no matter how the pipeline is run.

1. **Waste and consumption.** The public waste detail is unavailable, so no waste, consumption or waste-reduction figure appears anywhere in this project.
2. **Population.** KPIs describe the registered-export population only. The non-registered-export population has different capture characteristics (1.0% versus 37.7% single-event sessions) and is diagnostic, never pooled.
3. **Time.** Five weeks of weekday lunches in autumn 2020 (COVID period). No claims about seasons, trends, or today's restaurant.
4. **Research capture.** The public dataset is research-oriented; it is not a guaranteed live operational feed and may not reflect all operational behaviour.
5. **Size.** 1,697 core-ready sessions is a small slice of Flavoria's data since 2019.
6. **Derived weight.** `derived_selected_meal_weight_g` is a sum of component events under stated rules. It is not an observed meal weight, not consumption, and not waste.
7. **Component names.** Names vary across exports and languages. Within a session identity is stable (M4 median 5 under every definition); across exports in 2020-10-05..16 it is unstable (40.4% of shared scale-days disagree), so component comparison for that window is LIMITED and no alias table is used.
8. **M3.** "Observed Valid Sessions — Registered-Export Population" is a count of sessions. It does not measure how many people came. Registered-export volume follows a weekday pattern the other export lacks, and six days break it; those days are flagged and never excluded.
9. **M2 range.** P90 moves by up to about 63 g (6%) between scenarios, mostly with the period covered, not with the timezone.
10. **Weather** is regional, hourly and contextual. Descriptive comparison only, never a causal statement.
11. **Catalogue reliability.** Flavoria's own catalogue warns that data may be missing or incorrect during its 2026 reconstruction.
12. **Thresholds are diagnostic.** A flag is not a finding of error.
13. **M5 is high because few ERROR-level violations exist**, not because the data is proven error-free.
