# Business Question (frozen after source inspection)

Work backwards from the decision, not forwards from the data. We do not ingest everything merely because it exists.

## Business problem

A self-service restaurant wants to reduce food waste without hurting the dining experience. Its operational data sits in separate systems (lunch-line scales, checkout scale, cash register, waste stations, menu, building sensors) with different owners, grains and access rules. Leadership believes that because food is weighed, waste is visible.

**Frozen question.** *Are the operational measurements available to us sufficient to support future food-waste decisions, what can we already trust about what was selected at the lunch line, and what exact data is missing?*

This is deliberately a question about **measurement**, not about waste. The initial review established that waste data is not publicly retrievable, so the honest deliverable is a dependable reconstruction of what *is* measured, plus a precise statement of what is not.

## Stakeholders

| Stakeholder | What they need to know | What they must not be told |
|---|---|---|
| Restaurant operations manager | What is selected at the line and how variable it is | That volume counts are demand |
| Kitchen manager | Whether the median tray load is stable enough to discuss | That derived weight equals consumption |
| Sustainability / waste lead | Which data to procure to link selection to waste | Any waste number |
| Data / engineering team | That results reproduce and how fragile they are | That an assumption was safe because it was convenient |

## Decision

**The decision the client can take now:** *Do not launch a waste-reduction measurement programme on this data. Use the derived selected-weight evidence for portioning conversations, for the registered-export population only, and commission the waste-extract integration named in the gap register.*

Two smaller decisions follow: (1) whether the lunch-line measurement chain is dependable enough to extend, and (2) which data request goes to the source owner first.

## Information required

Framing: **Problem → Information need → Field → Source → Owner → Freshness → Trust → Gap.** "Relevant does not mean authoritative."

| # | Information need | Field / event | Source | Owner | Freshness | Trust (profiling) | Gap |
|---|---|---|---|---|---|---|---|
| 1 | What was placed on a tray, and how much of each component | component weighing event: scale, name, grams, time | FlavoriaFoodWeight1700 lunch-line CSV | University of Turku / University of Helsinki | static snapshot, 2020-10-05..11-20, published 2022-06-10 | Medium: schema drift, one file on a different clock, unstable names in one window | No meal total; names are a lookup |
| 2 | Which events form one tray pass | `session_id`, `tray_id`, identification time | same | same | same | Medium-high: 0 multi-tray sessions; 2 crossover IDs | Session is not a person |
| 3 | Total selected weight of a meal | **derived** from 1 and 2 | LAST TRAY | us | at run | Only as good as capture | An independent checkout total is unavailable |
| 4 | External conditions at meal time | temperature, wind, precipitation | FMI observations | Finnish Meteorological Institute | historical | High (complete, 3 NULLs) | Regional station, not on site |
| 5 | Which record to trust when exports disagree | population and file provenance | filenames only | unknown | n/a | Low: labels undefined | Meaning of the labels |
| 6 | What was consumed | none | none | none | n/a | n/a | **UNKNOWN** |
| 7 | What was discarded | waste weight per tray | Flavoria Lunch Line Waste | Flavoria | live since 2019 | n/a | **SOURCE GAP** |

## Minimum viable data

Exactly what is needed to answer the frozen question, and nothing more:

1. The lunch-line weighing events (information needs 1 and 2).
2. Derivation rules and validation evidence (need 3).
3. Weather as context (need 4), kept outside the core KPIs.
4. Source documentation proving what is **not** available (needs 5-7).

## Non-required data

Images (2.4 GiB, feed no metric); the second-half workflow systems (Weigh & Dine, cash register, building data, MyFlavoria, surveys) which are documented but not retrievable; any machine-learning features; the 2025 forecasting paper's data.

## Known gaps

The complete register is `source_gap_register.md`. The three that decide the business question:

| Gap | Consequence | What closes it |
|---|---|---|
| Waste per tray (SOURCE GAP) | No waste KPI can exist | A raw extract: tray, time, grams, waste point, imputed flag |
| Consumption (UNKNOWN) | Cannot be measured at all | Selected minus waste, once waste is available |
| Meaning of the population labels | KPIs limited to one export | Confirmation from the source owner |

## What success looks like

A reviewer can clone the repository, run one command, and see: which numbers can be trusted, which cannot, how fragile each is, and what to ask for next.
