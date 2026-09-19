# Source-of-Truth Decisions

Source-of-truth is a business and system decision, not "whichever value is newest". For each business fact this document states what truth is needed, which source supplies it, why, what was rejected or is only secondary, and what uncertainty remains. Decision-log references (D-numbers) point to `decision_log.md`.

This is an FDE-style reconstruction using publicly available Flavoria research data and public weather data. It is not an analysis of Flavoria's live operational systems.

## Central boundary

```
component weighing event   OBSERVED     (a scale recorded a weight for a named component)
selected meal weight       DERIVED      (derived_selected_meal_weight_g: sum of observed events under our rule)
consumed quantity          UNKNOWN      (no source measures it)
food waste quantity        SOURCE GAP   (documented, not publicly accessible in the required usable form)

selected weight  ≠  consumption  ≠  waste
```

## Summary

| Business fact | Truth needed | Source used | Rejected or secondary | Uncertainty that remains |
|---|---|---|---|---|
| Weighing event | What a lunch-line scale recorded for one component | FlavoriaFoodWeight1700 CSV (one row per component weighing) | Weigh & Dine documentation (a different system, checkout total, no component weights) | Whether the 11 public files are the complete export for those weeks; how scales are tared |
| Session identity | Which events belong to one tray pass | `session_id` inside one population; key `(session_id, population)` | `tray_id` (reused: 687 trays, 87% used on more than one day) | A session is not a person; two crossover IDs appear in both exports |
| Population | Which export a record belongs to | the source file name prefix | any business meaning of the labels (not defined by the source) | What "registered" and "non-registered" mean |
| Component identity | What was weighed | `scale_identifier` is stable; `component_name` is a menu-lookup label, normalised within a session | an alias table across exports (would be invented) | Names disagree across exports in 2020-10-05..16 |
| Timestamp | When a weighing happened | the event timestamp, Europe/Helsinki, with a file-specific +3h normalisation for one file | a single global offset; row order | The +3h is strongest-supported, not source-confirmed |
| Weather observation | Outdoor conditions in the hour of the meal | FMI open data, Turku Artukainen (FMISID 100949), hour-ending | any on-site measurement (none exists in the public data) | Regional station about 6 km away; contextual only |
| Waste | What was thrown away per tray | Flavoria Lunch Line Waste (documented, not publicly accessible) | anything derived from selection | Source gap: no public data, so W1 is BLOCKED |

## What is a weighing event? (D2, D22)

**Truth needed.** The quantity a lunch-line scale recorded for one component at one moment.
**Source used.** FlavoriaFoodWeight1700, the CSV archive: 12,284 rows, 30 scales, 11 files, 2020-10-05 to 2020-11-20. It is authoritative for what the scales recorded.
**Why.** It is the only public source of component-level weights, published by the research team that produced the dataset, with a checksum-verified archive.
**Rejected or secondary.** Weigh & Dine (checkout scale) has no public sample and records a plate total, not components. Row order is not trusted (it is not chronological); the parsed timestamp orders events.
**Uncertainty.** There is no total-weight column. Readings at or above 1,500 g (six events) are flagged and kept; the effect of the largest on M1 and M2 is at most 3.0 g.

## What is a dining session? (D1, D15)

**Truth needed.** Which events belong to one tray pass.
**Source used.** Events sharing one `session_id` within one population. The source never states "this is a dining session"; the session is **derived**. Key: `(session_id, population)`.
**Why.** 3,343 distinct IDs across 3,345 keys; no session has more than one tray or more than one identification time.
**Rejected or secondary.** `tray_id` is reused across days, so it cannot be the session key. `session_id` alone is not enough: two IDs appear in both exports.
**Uncertainty.** A session is not a person and not a meal eaten.

## Which population do the KPIs describe? (D5)

**Truth needed.** Which records the headline numbers describe.
**Source used.** The **registered-export population**. The **non-registered-export population** is diagnostic only. The two labels are **inherited from source file names**; the public documentation does not define them, and they are never read as customer-registration status.
**Why.** The two exports differ sharply (1.0% versus 37.7% single-event sessions; median derived weight 499 g versus 192 g), so pooling would report the population mix, not a measurement.
**Rejected or secondary.** Pooling (kept only as the forbidden guardrail G01 in the sensitivity analysis).
**Uncertainty.** What the labels mean is a question for the source owner (Q1).

## What is a food component? (D18)

**Truth needed.** What was weighed.
**Source used.** The stable unit is the **scale event** (`scale_identifier`). `component_name` is a menu-lookup label. For counting we use `component_id_normalized` (trim, whitespace collapse, case-fold) **within one session**.
**Why.** Raw and normalised counts never differ within a session; the M4 median is 5 under four identity definitions.
**Rejected or secondary.** An alias table: across exports names disagree for 86 of 213 scale-days in 2020-10-05..16 (0 of 469 elsewhere), mixing language variants with genuinely different dishes, so any alias would be invented.
**Uncertainty.** Component identity across days or exports is LIMITED.

## Which clock is right? (D4)

**Truth needed.** When each weighing happened.
**Source used.** Europe/Helsinki local time, with a file-specific override of +3h for `registered_2020_10_05-2020_10_18.csv`.
**Why.** The same session appears in that file exactly 10,800 s earlier than in the other export; after +3h its hour-of-day profile matches the other registered-export files (distance 0.046 versus 1.994).
**Rejected or secondary.** A global offset; +2h and +4h are tested as sensitivity scenarios and give identical M1-M5, while +0h and +1h quarantine 303 and 103 sessions.
**Uncertainty.** **+3h is an evidence-backed engineering decision, not a source-confirmed timezone.** Weights and service dates do not depend on it; time of day, the service-hours rule and the weather join do.

## What is a weather observation? (D8, D21)

**Truth needed.** Outdoor conditions in the hour of a meal, as context.
**Source used.** FMI open data, Turku Artukainen (FMISID 100949), hourly, joined by the hour-ending observation (`r_1h` is the hour ending at its timestamp, tested empirically). Values are OBSERVED (by FMI); any category built from them is DERIVED.
**Why.** It is the authoritative public source for weather, complete for the period (1,129 of 1,129 hours; 3 NULL precipitation values kept as NULL).
**Rejected or secondary.** No on-site weather exists publicly. Weather never decides validity.
**Uncertainty.** A regional station about 6 km away (approximate). It supports descriptive association only, never a causal statement.

## What counts as waste? (D7)

**Truth needed.** The weight discarded per tray.
**Source.** Flavoria Lunch Line Waste is **conceptually documented but not publicly accessible in the required usable form**: the catalogue's sample section reads "TODO, Ask!", the detail is in a restricted repository, and there is no public download, API, schema or contact. **Therefore W1 remains BLOCKED / SOURCE GAP.**
**Why nothing substitutes.** `waste_weight_g` stays NULL and is never 0; waste is never estimated from selection, and no waste-reduction percentage is produced. The sensitivity analysis states that no scenario produces a waste estimate, band or proxy.
**Uncertainty.** Permanent unless an actual public raw waste dataset is found.

## What counts as a valid observation? (D24)

- **Valid event:** parsable timestamp, positive numeric weight, non-empty identifiers, not an exact duplicate, no unresolved identity conflict.
- **Canonical (valid) session, `core_ready`:** registered-export population, at least one valid event, no ERROR-level violation, no identity conflict.
- Weather availability, precipitation NULLs, volume flags, timezone status and WARN-level flags are **not** part of validity.
- **Quarantine, not delete:** excluded records stay in the model, flagged and listed.

## Which record wins when two disagree? (D6)

No record "wins" by default. Where the same `session_id` appears in both exports (`session2266`, `session3222`), **both versions are quarantined** and neither enters the canonical population until the source owner names the authoritative record. Inclusion effects (M1 +0.0 g, M2 +2.8 g) are reported only as sensitivity analysis.

## What is a threshold, and a volume irregularity? (D19, D20, D23, D29)

Every threshold (B02 at or above 1,500 g; B07 outside [50, 2,200] g; T05 span above 600 s; T07 first-event hour outside [10, 11); C02 under 30 sessions; the weekday-regime comparison) is a **diagnostic validation threshold derived from the observed structure of this data**. It is not a claim of physical impossibility. A flagged record stays in the KPI population unless it fails an ERROR-level rule. `low_observed_volume_day` and `volume_irregularity` describe days and never exclude a day or session; M3 is "Observed Valid Sessions — Registered-Export Population", a count of sessions, not a measure of how many people came.

## What can we not claim?

1. Any waste, consumption or waste-reduction number.
2. That a session is a person, or that M3 measures how many people came.
3. That registered-export results describe every session in the restaurant, or that "registered" means customer registration.
4. That the derived weight equals plate content.
5. Causal effects of weather.
6. Anything about seasons or years: 35 weekday lunches in autumn 2020, during the COVID period.
7. That the source's timezone is confirmed, or that any threshold marks a value as physically impossible.
8. That a high M5 proves the data is error-free.
