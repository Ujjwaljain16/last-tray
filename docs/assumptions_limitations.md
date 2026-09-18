# Known / Unknown / Assumptions / Limitations

Status: after Phase 2 profiling. Each item cites where the evidence lives.

**Population labels** ("registered-export population", "non-registered-export population") are **inherited from source filenames**. The public documentation reviewed for this project does not define their business meaning, so we use them only as population labels and do not interpret them as customer-registration status.

## KNOWN (verified from primary sources or the raw files)

| # | Statement | Evidence |
|---|---|---|
| K1 | The dataset is open, CC-BY-4.0, v1.0.0, DOI 10.5281/zenodo.5850856; the 1.28 MB CSV archive matches Zenodo's MD5 | Zenodo API record; local hash |
| K2 | Source grain is one component weighing event: 12,284 rows, 3,343 session IDs, 687 trays, 30 scales, 246 raw component names | `outputs/source_inventory.csv`, `docs/phase2_profile_report.md` |
| K3 | Coverage: 35 weekday service days, 2020-10-05 to 2020-11-20 | profile |
| K4 | No total-meal-weight column and no waste column exists in any of the 11 files | headers |
| K5 | The public waste sample is documented as `"TODO, Ask!"`; no download, API, schema or contact is published | Flavoria waste page, updated 2026-04-09 |
| K6 | Weigh & Dine records total plate weight at checkout (±5 g) and has **no component weights**; it is a different system from the public CSV | Flavoria WnD page |
| K7 | FMI weather is retrievable with no key: 1,129 hourly UTC rows for Turku Artukainen (FMISID 100949), 3 missing precipitation values | `data/raw/weather/` |
| K8 | `r_1h` at time t is the accumulation over the **hour ending at t** (one-day empirical test: error 0.021 mm vs 0.378 mm) | `docs/phase2_profile_report.md` section 12 |
| K9 | One file's timestamps are offset by exactly 10,800 s from the same session in the other export; +3h makes its hour-of-day profile match the other registered-export files (distance 0.046 vs 1.994) | `docs/timezone_decision.md` |
| K10 | The populations differ: 1.0% vs 37.7% single-event sessions, 97% vs 75% with a hot dish, median derived weight 499 g vs 192 g | `docs/population_decision.md` |
| K11 | Schema drift: 7 of 11 files lack `weighting_type`; two timestamp formats decided per column; **row order is not chronological**; one file lists events newest-first | Phase 2 section 1 |
| K12 | 2 sessions appear in both exports (`session2266` identical; `session3222` shifted 10,800 s with 2 substantive name conflicts); 2 exact duplicate rows | Phase 2 sections 3, 4, 10 |
| K13 | Registered-export daily volume is bimodal by weekday (Mon-Wed 41-107, Thu-Fri 2-18 in the four baseline weeks); the non-registered-export population is flat at 36-75 | Phase 2 section 7 |
| K14 | Repeated weighings on one scale in a session are additive scoops (100% same name, 93.8% within 30 s, second reading smaller than the first 59.8% of the time) | Phase 2 section 4 |
| K15 | M4's median is 5 under raw names, normalised names, scales and event counts; raw and normalised counts never differ within a session | Phase 2 section 5 |
| K16 | Across 25 tested scenarios M1 stays within 493-505 g and M4 is 5; M2 ranges 977-1,066 g; the crossover sessions and the 2,097 g event each move M2 by at most 3.0 g | `docs/sensitivity_analysis.md` |

## UNKNOWN (no source available to us)

| # | Statement |
|---|---|
| U1 | How much food was **consumed** by any diner. Never measured anywhere we can see |
| U2 | Whether a session is one person, or a tray pass by a repeat diner |
| U3 | What items were taken outside a weighed station |
| U4 | Whether the lunch-line scales are tared for plates or trays, and how |
| U5 | Whether the public 11 files are the complete Flavoria lunch-line export for those weeks |
| U6 | What the two population labels mean |

## SOURCE GAP (measured somewhere, not retrievable)

| # | Statement |
|---|---|
| G1 | **Food waste per tray** (Flavoria Lunch Line Waste). `BLOCKED / SOURCE GAP`, permanently, unless an actual public raw waste dataset is found |
| G2 | Checkout total plate weight (Weigh & Dine) |
| G3 | Cash-register linkage; building occupancy; MyFlavoria; menu diet and allergen data |

## ASSUMPTIONS (each isolated so it can change in one place)

| # | Assumption | Why | If wrong | Where isolated |
|---|---|---|---|---|
| A1 | The filename labels identify two separable exports; **no meaning is assumed** beyond that | file names only; nothing published | KPIs describe the registered-export population only | `config/populations.yml` |
| A2 | `registered_2020_10_05-2020_10_18.csv` is in UTC and is normalised by +3h; all other files are Europe/Helsinki local time. This is **the strongest-supported normalisation decision, not a source-confirmed timezone** | `docs/timezone_decision.md` | Weather join and time-of-day off by 3 h for about 23% of primary sessions; weights and dates unaffected | `config/timezone_overrides.yml` |
| A3 | Events sharing a `session_id` within one population belong to one tray pass | 0 sessions with more than one tray; 7 sessions over 10 minutes are flagged | Session weights inflated for those 7 | rules T04, T05 |
| A4 | Summing component events approximates what was placed on the tray | scales weigh each component as placed; repeats behave as additive scoops | Biased low if items are added elsewhere | naming (`derived_selected_meal_weight_g`), rule B05 |
| A5 | Normalised name (trim, whitespace, case-fold) identifies a component **within a session** | raw and normalised counts never differ within a session | Cross-export or cross-day component identity is not assumed | `component_id_normalized`, rule I07 |
| A6 | FMI Turku Artukainen represents outdoor conditions well enough for a context flag | nearest station returned by `place=Turku`, about 6 km away (approximate) | Weak weather association; core metrics unaffected | `fact_weather`, X05 |
| A7 | Weather for a session is the observation stamped at the end of the hour containing its first weighing | `r_1h` is hour-ending (K8) | Up to one hour of misalignment | TRD 7.8 |
| A8 | The weekday volume pattern (Mon-Wed high, Thu-Fri low) is a description of the baseline weeks, not a rule of nature | 4 weeks, perfect separation | More days would be flagged as irregular | TRD 7.9; flags never exclude data |

## LIMITATIONS

1. **Population.** KPIs describe the registered-export population only. The non-registered-export population is diagnostic.
2. **Time.** 5 weeks of weekday lunches in autumn 2020 (COVID period). No claims about seasons, trends, or today's restaurant.
3. **Size.** 1,697 candidate primary sessions is a small slice of Flavoria's data since 2019.
4. **Derived weight.** `derived_selected_meal_weight_g` is a sum of component events under stated rules. It is not an observed meal weight and not consumption.
5. **M3 is not demand.** M3, "Observed Valid Sessions — Registered-Export Population", is a count only: not demand, diners, customers or traffic. Registered-export daily volume follows a weekday pattern the other export lacks, and six days break it; those days are flagged and never excluded.
6. **Component identity.** Within a session it is stable (M4 median 5 under every definition). Across exports it is unstable in 2020-10-05..16 (40.4% of shared scale-days disagree), so component-level comparison for that window is `LIMITED`. No alias table is used.
7. **M2 sensitivity.** P90 moves by up to about 63 g (6%) between scenarios, mostly with the period covered, not with the timezone.
8. **Weather** is regional, hourly and contextual. Descriptive comparison only, never causal statements ("meal weights were lower on the observed rainy days").
9. **Catalogue reliability.** Flavoria's own catalogue warns that data may be missing or incorrect during its 2026 reconstruction.
10. **Session ≠ person.** No unique-diner metric.
11. **No waste.** No waste, consumption or waste-reduction figure appears anywhere in this project.
12. **Thresholds are diagnostic.** B02, B07, T05, T07 and C02 are validation thresholds derived from this dataset's structure, not claims of physical impossibility or universal abnormality; a flag is not a finding of error.
13. **M5 is high because few ERROR-level violations exist**, not because the data is proven error-free.

## Unresolved questions

| # | Question | Who can answer | Effect if unresolved | Status |
|---|---|---|---|---|
| Q1 | What do the two filename labels mean? | source owner | KPIs limited to the registered-export population | open |
| Q2 | Why do 37.7% of non-registered-export sessions have one event and 28% weigh under 50 g? | source owner | that population stays diagnostic | open |
| Q3 | Is the source timezone of the dotted file UTC? | source owner | +3h remains the strongest-supported normalisation, not a confirmed fact | open |
| Q4 | Which record is authoritative for `session2266` and `session3222`? | source owner | both stay quarantined | open |
| Q5 | Why is registered-export daily volume weekday-patterned (Mon-Wed high, Thu-Fri low), and why does it break on Nov 2, 6, 16, 17, 18, 20? | source owner | M3 stays "observed sessions"; flagged days retained | **narrowed in Phase 2**: not unique to Nov 16-20, sessions on those days look ordinary; cause open |
| Q6 | Why does the non-registered-export export end on 2020-11-13? | source owner | diagnostic coverage 30 of 35 days | open |
| Q7 | Do the images cover all 3,343 sessions? (Zenodo: "around 2,000 pictures") | image archive, 2.4 GiB, not downloaded | none: images feed no metric | open |
| Q8 | FMI `r_1h` timestamp convention | FMI docs | none now | **resolved empirically** (hour ending; one-day test); documentation statement not found |
| Q9 | Are plates or trays tared at the lunch-line scales? Are readings above 1,500 g genuine bulk portions or artefacts? | source owner | interpretation of derived weight and the 6 events at or above 1,500 g | open (Phase 2: 2,097 g is the 99.76th percentile on its scale, effect on M1/M2 negligible) |
| Q10 | What is the 2,097 g event? | source owner | flagged B02, kept | open (same evidence as Q9) |
| Q11 | Why do the two exports disagree on component names for 40.4% of shared scale-days in 2020-10-05..16 and 0% elsewhere? | source owner | component-level comparison for that window is LIMITED | **new** |
| Q12 | Do long sessions (7 above 600 s, one gap of 1,647-2,723 s each) merge two tray passes after identification? | source owner | 7 flagged sessions (0.4%) | **new** |
| Q13 | Are single-event registered-export sessions genuine (10 exceed 100 g, several are soups) or partial captures (6 are 50 g or less)? | source owner | 17 flagged sessions (1.0%), effect on M1 +2 g | **new** |
