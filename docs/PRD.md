# LAST TRAY: Product Requirements (v3, historical: written before implementation)

> **Status.** This is the requirements document the implementation followed. The implemented behaviour, final metric wording and evidence are in `README.md`, `final_evidence.md` and `decision_log.md`; where they differ, those are authoritative.

**Flavoria DiningOps Truth.** Supersedes the original ChatGPT-drafted plan (an early working document, not included in this repository). Every change from that plan is in `docs/decision_log.md`.

> The client scenario is **simulated for educational purposes**. The data and documentation are real and public, published by the University of Turku and collaborators. We are not working for, and do not speak for, Flavoria, the University of Turku, or any partner.

## 1. Definition

**LAST TRAY is a dependable measurement-reconstruction pipeline.** It rebuilds tray-level selection records from raw lunch-line scale events, labels every number as observed, derived, unknown or source-gap, tests how sensitive its answers are to its own assumptions, and tells the client whether the available measurements can yet support food-waste decisions.

It is deliberately **not** a dining-analytics dashboard. The hard work is reconstruction: 12,284 component-level weighing events had to become sessions, two exports had to be kept apart, one file's clock had to be investigated, schema drift and unstable component names had to be handled, and each choice had to be tested rather than assumed.

## 2. Client problem

A self-service restaurant wants to reduce food waste without hurting the dining experience. Its data is fragmented across lunch-line scales, a checkout scale, a cash register, a waste-station system, menu data and building sensors. Leadership's instinct: "we weigh food, so we can see waste."

**We do not yet know that.** The MVP does not measure food waste. It answers a prior question:

> **Are the operational measurements available to us sufficient to support future food-waste decisions, what can we already trust about what was selected at the lunch line, and what exact data is missing?**

## 3. Why the obvious answer is insufficient

The lunch-line scales record grams of each component **as it is placed on the tray**: what was *selected*. Consumption and waste happen later and are recorded elsewhere. The waste system's public sample is documented as `"TODO, Ask!"`; the public data contains no waste value of any kind. Producing "waste" from these files would be manufacturing it.

## 4. Stakeholders and the decision each supports

| Stakeholder | Question | Decision supported |
|---|---|---|
| Restaurant operations manager | What is selected at the line, and how variable is it? | Whether derived selected-weight data is dependable enough to open a portioning conversation |
| Kitchen manager | Is the pattern stable enough to inform preparation? | Whether to use median tray load as an input, with named caveats |
| Sustainability / waste lead | Can selection be linked to measured waste? | **Which data must be procured first**: a raw waste extract keyed on tray |
| Data / engineering team | Can I rerun this and get the same answer, and do I know how fragile it is? | Whether the pipeline is dependable enough to extend |

**Decision the client can take now:** *Do not launch a waste-reduction measurement programme on this data. Use the derived selected-weight evidence for portioning conversations, for the registered-export population only, and commission the waste-extract integration listed in the gap register.*

## 5. Scope

**In the MVP (all retrievable today):** FlavoriaFoodWeight1700 CSV archive (Zenodo, CC-BY-4.0, 2020-10-05 to 2020-11-20); FMI hourly weather (WFS API, Turku Artukainen) as **context only**; Flavoria Data Catalog pages as source-definition evidence.

**Documented, not ingested:** Lunch Line Waste, Weigh & Dine, Cash Register, Building Data, MyFlavoria, Surveys (see `source_gap_register.md`).

**Out of scope:** machine learning, images, causal claims, any waste or consumption figure, unique-diner counting.

**Population labels.** "registered-export population" and "non-registered-export population" are **inherited from source filenames**. The public documentation reviewed for this project does not define them, so they are population labels only. We never read "registered" as customer-registration status.

## 6. Ground truth about the source

| Fact | Evidence |
|---|---|
| Atomic grain = **one component weighing event**; a dining session is a **derived** entity | 12,284 rows, 3,343 session IDs |
| No meal-total and no waste column exists | 8 raw columns, none is a total |
| Two populations, never pooled; session key `(session_id, population)` | `docs/population_decision.md` |
| One file appears to be on a different clock; +3h is an evidence-backed engineering decision, **not** source-confirmed timezone metadata | `docs/timezone_decision.md` |

## 7. Evidence vocabulary (used everywhere)

| Class | Meaning | Example |
|---|---|---|
| **OBSERVED** | Recorded by an instrument or external authority | one component weighing event; FMI temperature |
| **DERIVED** | Computed by us from observed facts under a stated rule | `derived_selected_meal_weight_g` (total selected meal weight); session; component count |
| **UNKNOWN** | Never measured by any source available to us | consumed quantity |
| **SOURCE GAP** | Measured somewhere, not retrievable | actual waste quantity |

UNKNOWN and SOURCE GAP are stored as NULL, **never zero**. A DERIVED value is never labelled OBSERVED, and never leaves the system without its rule beside it.

## 8. Metrics (final)

All core metrics describe the **registered-export population**. Formulas and full definitions: `docs/metric_definitions.md`.

| ID | Name | Formula | Denominator / population |
|---|---|---|---|
| M1 | **Median Derived Selected Meal Weight** (g) | `MEDIAN(derived_selected_meal_weight_g)` | canonical sessions (`core_ready`) |
| M2 | **P90 Derived Selected Meal Weight** (g) | `P90(derived_selected_meal_weight_g)` | canonical sessions |
| M3 | **Observed Valid Sessions — Registered-Export Population** | `COUNT(canonical sessions)`; also per service date | n/a. **Not demand, diners, customers or traffic.** |
| M4 | **Median Distinct Normalized Components per Session** | `MEDIAN(distinct_component_count)` | canonical sessions |
| M5 | **Core Measurement Readiness** | `core_ready sessions / eligible sessions` | eligible = **every registered-export session ID in the source (1,699), counted before any record is removed** |

Baseline values (Phase 2 preview, to be reproduced by the pipeline): M1 = 499 g, M2 = 1,039.6 g, M3 = 1,697, M4 = 5, **M5 = 1,697 / 1,699 = 99.88%**.

**Supporting metrics (not core KPIs):**
| ID | Name | Definition |
|---|---|---|
| S1 | **Weather Context Coverage** | sessions matched to a weather hour / the same eligible 1,699 sessions. Never affects M1-M5 |
| S2 | **Warn-free Rate** | eligible registered-export sessions with **no session-level WARN** (B04, B07, T04, T05, I06) / **the same fixed 1,699**. Baseline **1,663 / 1,699 = 97.88%**. The event-level variant (also counting B02 and I02) is 1,660 / 1,699 = 97.70%, a reconciled diagnostic: see `docs/metric_contract.md` |
| S3 | Portion spread (P90 − P10) | optional context |
| S4 | Population diagnostics | non-registered-export population, labelled DIAGNOSTIC |

**Denominator rule.** M5 and the warn-free rate both use the full eligible population fixed **before** any record is removed or quarantined. A metric never becomes 100% by shrinking its own denominator. File-level (T07) and day-level (C02) flags do not enter the warn-free rate because they are documented normalisations or flag-only descriptions.

**Diagnostic fields retained (not headline):** `component_weighing_event_count`, `session_span_s`, same-scale-repeat rate, `low_observed_volume_day`, `volume_irregularity`, the 2,097 g event, exact-duplicate rows, crossover sessions, weather-unmatched count, precipitation NULL count.

**Blocked:** **W1 plate waste per session / waste-to-selected ratio = `BLOCKED / SOURCE GAP`**, permanently, unless an actual public raw waste dataset is found. Required source: Flavoria Lunch Line Waste, keyed on tray.

## 9. Rules that shape the metrics

- **Core vs context.** M5 checks the meal record itself: parseable identity and time, valid positive weights, no ERROR-level violation, no identity conflict. Weather never enters it.
- **Component counting.** M4 counts distinct normalised names inside one session (trim, whitespace collapse, case-fold). No alias table: component identity across exports disagrees in 2020-10-05..16 (40.4% of shared scale-days) and the differences mix language variants with real dish differences. `component_weighing_event_count` is a diagnostic.
- **Thresholds are diagnostic, not physical.** B02 ≥ 1,500 g, B07 outside [50, 2,200] g, T05 span > 600 s, T07 median first-event hour outside [10, 11), C02 < 30 sessions and the weekday-regime rule are **validation thresholds derived from the observed structure of this data**. They are not claims of physical impossibility or universal abnormality, and a flagged record is not evidence of error.
- **Volume flags never exclude.** `low_observed_volume_day` and `volume_irregularity` are **flags only**. Nov 16-20 and every other flagged day stay in the KPI population.
- **Crossover sessions.** `session2266` and `session3222` stay quarantined and are not in the canonical population. Their effect (M1 +0.0 g, M2 +2.8 g if included) is reported **only** as sensitivity analysis.
- **Timezone.** +3h for `registered_2020_10_05-2020_10_18.csv` is the strongest-supported normalisation decision from cross-export consistency evidence; source metadata does not confirm the timezone.
- **Sensitivity is a product output.** `outputs/validation/sensitivity_analysis.csv` recomputes M1-M5 under alternative assumptions (baseline, crossover inclusion, 2,097 g removal, alternate timezone hypotheses, volume diagnostics, definitions) to show assumptions were tested rather than selected for favourable results.

## 10. Evidence statuses (deterministic, not confidence scores)

`READY`, `READY_WITH_LIMITATION`, `BLOCKED`. Expected: M1-M5 `READY_WITH_LIMITATION` (derived weight; one population; M4 component identity limited for 2020-10-05..16); S1 `READY_WITH_LIMITATION`; W1 `BLOCKED`.

## 11. The FDE judgement call

> **We refused to let three convenient shortcuts pass as facts.**
> 1. **Selected weight is not waste.** The scales record what went onto the tray. Waste is a separate, currently inaccessible measurement.
> 2. **A derived total is not an observed total.** No meal total exists in the source. We summed component events under a stated rule, named it `derived_selected_meal_weight_g`, and carry the rule wherever the number goes.
> 3. **Population, schema and timezone differences are findings, not clean-up.** One file appears three hours off (+3h is an evidence-backed decision, not confirmed metadata). Seven files lack a column. One export contains many partial-looking sessions. Component names disagree across exports in one window. We investigated each, recorded evidence, tested alternatives in `sensitivity_analysis.csv`, and kept affected data visible.

## 12. Non-goals and things we will not say

- No causality: "meal weights were lower on the observed rainy days", never "rain causes".
- A session is not a person; M3 is not demand, diners, customers or traffic.
- KPIs describe the registered-export population, not "the average diner".
- No waste, consumption or waste-reduction number.

## 13. Acceptance criteria

1. `python -m src.pipeline.run` reproduces every file in `outputs/` from the committed `data/raw/` with no manual step and **no network access**. Retrieval is a separate, explicit command.
2. Two consecutive runs give identical row counts, hashes and metric values.
3. Every metric row carries value, population, definition, source, records used, records excluded, evidence status, limitation.
4. Every violation appears in `validation_issues.csv`; nothing is dropped silently.
5. M5 and the warn-free rate use the eligible denominator fixed before removal.
6. `sensitivity_analysis.csv` is produced and its baseline row equals the headline KPIs.
7. The waste metric appears as `BLOCKED` with the required source.
8. A weather failure changes only weather-dependent outputs.
9. README, PRD, TRD and diagrams describe what the code does.

## 14. Open questions

`docs/known_unknowns_assumptions_limitations.md`, "Unresolved questions".
