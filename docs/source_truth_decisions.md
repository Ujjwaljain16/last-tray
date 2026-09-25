# Source-of-truth decisions

Picking a source of truth is a business and system decision, not just "whichever value is newest". For every business fact below I state what truth I actually needed, which source supplies it, why I trust that source, what I rejected or kept only as secondary, and what uncertainty is still left over. The D-numbers point to `decision_log.md`, where I first made each call.

This is an FDE-style reconstruction using publicly available Flavoria research data and public weather data. It is not an analysis of Flavoria's live operational systems, which I have never had access to.

## Central boundary

```
component weighing event   OBSERVED     (a scale recorded a weight for a named component)
selected meal weight       DERIVED      (derived_selected_meal_weight_g: sum of observed events under my rule)
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

**What I needed to know.** The quantity a lunch-line scale recorded for one component at one moment.
**What I used.** FlavoriaFoodWeight1700, the CSV archive: 12,284 rows, 30 scales, 11 files, 2020-10-05 to 2020-11-20. It's authoritative for what the scales recorded.
**Why I trust it.** It's the only public source of component-level weights, published by the research team that produced the dataset, with a checksum-verified archive.
**What I rejected.** Weigh & Dine (the checkout scale) has no public sample and records a plate total, not components. I also don't trust row order, since it isn't chronological; the parsed timestamp orders events instead.
**What's still uncertain.** There's no total-weight column. Readings at or above 1,500 g (six events) are flagged and kept; the effect of the largest on M1 and M2 is at most 3.0 g.

## What is a dining session? (D1, D15)

**What I needed to know.** Which events belong to one tray pass.
**What I used.** Events sharing one `session_id` within one population. The source never says "this is a dining session"; I derived that myself. Key: `(session_id, population)`.
**Why I trust it.** 3,343 distinct IDs across 3,345 keys, and no session has more than one tray or more than one identification time.
**What I rejected.** `tray_id` is reused across days, so it can't be the session key. `session_id` alone isn't enough either: two IDs show up in both exports.
**What's still uncertain.** A session is not a person, and it isn't a meal actually eaten.

## Which population do the KPIs describe? (D5)

**What I needed to know.** Which records the headline numbers actually describe.
**What I used.** The **registered-export population**. The **non-registered-export population** is diagnostic only. Both labels are **inherited from source file names**; the public documentation never defines them, and I never read them as customer-registration status.
**Why I trust it.** The two exports differ sharply (1.0% versus 37.7% single-event sessions; median derived weight 499 g versus 192 g), so pooling them would just report the population mix, not a measurement.
**What I rejected.** Pooling, which I keep only as the forbidden guardrail G01 in the sensitivity analysis. I also considered dropping the non-registered-export population entirely, but rejected that too: it's the clearest evidence I have of a capture-behaviour difference, so I keep it, label it DIAGNOSTIC, and never mix it into a KPI.
**What's still uncertain.** What the labels actually mean is a question only the source owner can answer (Q1). Registered-export daily volume is weekday-patterned (Mon-Wed 41-107 sessions, Thu-Fri 2-18) in a way the other export isn't, so I read M3 as observed sessions, never as demand, diners, customers or traffic.

## What is a food component? (D18)

**What I needed to know.** What was actually weighed.
**What I used.** The stable unit is the **scale event** (`scale_identifier`). `component_name` is a menu-lookup label. For counting, I use `component_id_normalized` (trim, whitespace collapse, case-fold) **within one session**.
**Why I trust it.** Raw and normalised counts never differ within a session, and the M4 median is 5 under four different identity definitions.
**What I rejected.** An alias table across exports: names disagree for 86 of 213 scale-days in 2020-10-05..16 (0 of 469 elsewhere), mixing language variants with genuinely different dishes, so any alias I built would just be invented.
**What's still uncertain.** Component identity across days or exports stays LIMITED.

## Which clock is right? (D4)

**What I needed to know.** When each weighing actually happened.
**What I used.** Europe/Helsinki local time, with a file-specific override of +3h for `registered_2020_10_05-2020_10_18.csv`.
**Why I trust it.** The same session appears in that file exactly 10,800 s earlier than in the other export. After +3h, its hour-of-day profile matches the other registered-export files (distance 0.046 versus 1.994).
**What I rejected.** A global offset applied to every file. I tested +2h and +4h as sensitivity scenarios and got identical M1-M5, while +0h and +1h quarantine 303 and 103 sessions.
**What's still uncertain.** **+3h is an evidence-backed engineering decision on my part, not a source-confirmed timezone.** Weights and service dates don't depend on it; time of day, the service-hours rule, and the weather join do.

> A +3 hour normalization is the strongest-supported engineering decision based on cross-export temporal consistency checks; the original source does not explicitly confirm the timezone metadata.

**What depends on this decision, and what does not.** Unaffected: `derived_selected_meal_weight_g`, session volume per service day, component count, and core measurement readiness. Weights and calendar dates land on the same day either way the file is read. Affected: time-of-day patterns and the weather join, for the 385 registered-export sessions (about 23% of the primary population) inside the overridden file. That's exactly why I kept weather outside the core metric set: a timezone uncertainty should never be able to invalidate a weight.

**How I kept it file-specific.** The override applies only to `registered_2020_10_05-2020_10_18.csv`, stays disabled by default for every other file, and gets re-checked at ingestion time (rule T10): the named file, its validated date range, and the raw and post-shift hour bands must all still match, or the core lane fails outright instead of silently mis-applying the shift. Details: `decision_log.md` D4, D36.

## What is a weather observation? (D8, D21)

**What I needed to know.** Outdoor conditions in the hour of a meal, as context only.
**What I used.** FMI open data, Turku Artukainen (FMISID 100949), hourly, joined by the hour-ending observation (I tested empirically that `r_1h` is the hour ending at its timestamp). The values themselves are OBSERVED, by FMI; any category I build from them is DERIVED.
**Why I trust it.** It's the authoritative public source for weather, and it's complete for the period (1,129 of 1,129 hours, 3 NULL precipitation values kept as NULL, not filled in).
**What I rejected.** No on-site weather exists publicly, so there was nothing to reject in favour of. Weather never decides validity either way.
**What's still uncertain.** The station is regional, about 6 km away (approximate). It supports descriptive association only, never a causal statement.

## What counts as waste? (D7)

**What I needed to know.** The weight discarded per tray.
**What I used.** Flavoria Lunch Line Waste is **conceptually documented but not publicly accessible in the required usable form**: the catalogue's sample section reads "TODO, Ask!", the detail sits in a restricted repository, and there is no public download, API, schema or contact. **Therefore W1 remains BLOCKED / SOURCE GAP.**
**Why nothing substitutes for it.** `waste_weight_g` stays NULL and is never 0. I never estimate waste from selection, and I never produce a waste-reduction percentage. The sensitivity analysis confirms no scenario produces a waste estimate, band or proxy.
**What's still uncertain.** This is permanent unless an actual public raw waste dataset shows up.

## What counts as a valid observation? (D24)

- **Valid event:** parsable timestamp, positive numeric weight, non-empty identifiers, not an exact duplicate, no unresolved identity conflict.
- **Canonical (valid) session, `core_ready`:** registered-export population, at least one valid event, no ERROR-level violation, no identity conflict.
- Weather availability, precipitation NULLs, volume flags, timezone status, and WARN-level flags are **not** part of validity.
- **Quarantine, not delete:** excluded records stay in the model, flagged and listed, never dropped.

## Which record wins when two disagree? (D6)

No record "wins" by default in my model. Where the same `session_id` shows up in both exports (`session2266`, `session3222`), **both versions get quarantined**, and neither enters the canonical population until the source owner names which one is authoritative. I only report the effect of including them (M1 +0.0 g, M2 +2.8 g) inside the sensitivity analysis.

## What is a threshold, and a volume irregularity? (D19, D20, D23, D29)

Every threshold I use, B02 at or above 1,500 g, B07 outside [50, 2,200] g, T05 span above 600 s, T07 first-event hour outside [10, 11), C02 under 30 sessions, the weekday-regime comparison, is a **diagnostic validation threshold I derived from the observed structure of this data**. None of them claim physical impossibility. A flagged record stays in the KPI population unless it fails an ERROR-level rule. `low_observed_volume_day` and `volume_irregularity` describe days and never exclude a day or session; M3 is "Observed Valid Sessions — Registered-Export Population", a count of sessions, never a measure of how many people came.

## What I cannot claim

1. Any waste, consumption or waste-reduction number.
2. That a session is a person, or that M3 measures how many people came.
3. That registered-export results describe every session in the restaurant, or that "registered" means customer registration.
4. That the derived weight equals plate content.
5. Any causal effect of weather.
6. Anything about seasons or years beyond this window: 35 weekday lunches in autumn 2020, during the COVID period.
7. That the source's timezone is confirmed, or that any threshold marks a value as physically impossible.
8. That a high M5 proves the data is error-free.
