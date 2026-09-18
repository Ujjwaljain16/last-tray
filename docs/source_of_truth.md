# Source-of-Truth Decisions (final)

Source-of-truth is a business and system decision, not "whichever value is newest". Each answer states the rule, the reason, the evidence, what we cannot claim, and the decision-log entry.

## Central boundary

```
component weighing event   OBSERVED
total selected meal weight DERIVED      (derived_selected_meal_weight_g; sum of observed events, our rule)
consumed quantity          UNKNOWN      (no source)
actual waste quantity      SOURCE GAP   (source exists, not retrievable)

selected weight  ≠  consumption  ≠  waste
```

## What is a dining session? (D1, D15)

**Decision.** A **derived** business entity: events sharing one `session_id` within one population. The source never states "this is a dining session".
**Key.** (`session_id`, `population`).
**Evidence.** 12,284 events, 3,343 IDs; 0 sessions with more than one tray; 0 with more than one identification time; `tray_id` is reused (687 trays, 87% used on more than one day), so it is not the session key.
**Cannot claim.** One person, one meal eaten, one purchase.

## What is the authoritative meal weight? (D2)

**Decision.** There is **no observed meal weight**. The authoritative observed quantity is `weight_of_a_component` (grams, one event). The meal-level number is `derived_selected_meal_weight_g = SUM(component_weight_g)` over non-duplicate events. It is always called that.
**Evidence.** No total column; repeats are additive scoops (100% same name, 93.8% within 30 s, second smaller than first 59.8%).
**Cannot claim.** That it equals plate content, what a checkout scale would read, or anything eaten.

## What is a food component? (D18)

**Decision.** The stable unit is the **scale event** (`scale_identifier`). `component_name` is a menu-lookup label. For counting we use `component_id_normalized` (trim, whitespace collapse, case-fold), **within one session**; **no alias table**.
**Evidence.** Raw and normalised counts never differ within a session; the M4 median is 5 under four identity definitions; across exports names disagree for 86 of 213 scale-days in 2020-10-05..16 (0 of 469 elsewhere), mixing language variants with genuinely different dishes.
**Cannot claim.** Stable dish identity across days or exports; Finnish-English equivalence.

## What counts as a valid observation? (D24)

- **Valid event:** parsable timestamp, positive numeric weight, non-empty identifiers, not an exact duplicate, no unresolved identity conflict.
- **Canonical (valid) session, `core_ready`:** registered-export population, at least one valid event, no ERROR-level violation, no identity conflict.
- Weather availability, precipitation NULLs, volume flags, timezone status and WARN-level flags are **not** part of validity.
- **Quarantine, not delete:** excluded records stay in the model, flagged and listed.

## Which population do the KPIs describe? (D5)

The **registered-export population**. The **non-registered-export population** is DIAGNOSTIC only. These labels are **inherited from source filenames**; the public documentation does not define them; we never read "registered" as customer-registration status.

## Which record wins when two disagree? (D6)

No record "wins" by default. Where the same `(session_id)` appears in both exports, **both versions are quarantined** and neither enters the canonical population, until the source owner names the authoritative record. Inclusion effects (M1 +0.0 g, M2 +2.8 g) are reported **only** as sensitivity analysis.

## Which clock is right? (D4)

Europe/Helsinki, with a per-file override for `registered_2020_10_05-2020_10_18.csv`. **+3h is an evidence-backed engineering decision based on cross-export consistency; the source's metadata does not explicitly confirm the timezone.** Weights and service dates do not depend on it.

## What is weather? (D8, D21)

External **context** from FMI Turku Artukainen, hourly, joined by the hour-ending observation. Values are OBSERVED (by FMI). Any category built from them is DERIVED. Weather never decides validity.
**Cannot claim.** On-site conditions; causal effects.

## What is a threshold? (D23, D29)

Every threshold (B02 ≥ 1,500 g; B07 outside [50, 2,200] g; T05 span > 600 s; T07 first-event hour outside [10, 11); C02 < 30 sessions; weekday-regime comparison) is a **diagnostic validation threshold derived from the observed structure of this data**. It is **not** a claim of physical impossibility or universal abnormality. A flagged record stays in the KPI population unless it fails an ERROR-level rule.

## What is a volume irregularity? (D19, D20)

A **flag only**: `low_observed_volume_day` and `volume_irregularity` describe days, never exclude a day or session, and are not called data errors. M3 is named "Observed Valid Sessions — Registered-Export Population" and is **not demand, diners, customers or traffic**.

## What counts as waste? (D7)

Nothing in the MVP. Waste is a **SOURCE GAP**: `waste_weight_g = NULL`, `BLOCKED`, permanently unless an actual public raw waste dataset is found.
**Never:** waste = 0; waste estimated from selection; a waste-reduction percentage.

## What can we not claim?

1. Any waste, consumption or waste-reduction number.
2. That a session is a person, or that M3 is demand, diners, customers or traffic.
3. That registered-export results describe all diners, or that "registered" means customer registration.
4. That the derived weight equals plate content.
5. Causal effects of weather.
6. Anything about seasons or years: 35 weekday lunches in autumn 2020, during the COVID period.
7. That the source's timezone is confirmed, or that any threshold marks a value as physically impossible.
8. That a high M5 proves the data is error-free.
