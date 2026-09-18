# Source Map (final)

Framework (Class 4): **Problem → Information need → Field → Source → Owner → Freshness → Trust → Gap.** "Relevant does not mean authoritative."

**Problem.** Are the available measurements sufficient to support future food-waste decisions? (`business_question.md`). Visual: `diagrams/source-map.png`. Source availability was re-verified on 2026-09-18/19 against primary sources.

## Information needs to sources

| # | Information need | Required field / event | Source | Owner | Format | Grain | Freshness | Authority | Retrieval | Reliability (after Phase 2) | Known gap |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | What was placed on the tray, and how much of each component | `component_name`, `weight_of_a_component`, `weighing_event_time`, `scale_identifier` | **FlavoriaFoodWeight1700** lunch-line scales | University of Turku / University of Helsinki | CSV in TAR (11 files) | one component weighing event | static, 2020-10-05..11-20, published 2022-06-10 | **Authoritative** for what the scales recorded | HTTP GET; MD5 verified against Zenodo | Medium: 7 of 11 files lack a column; row order not chronological; one file 3 h off; names disagree across exports in 2020-10-05..16 | No total weight; names are a menu lookup |
| 2 | Which events belong to one tray pass | `session_id`, `tray_id`, `user_identification_time` | same | same | same | session (derived by us from `session_id`) | same | Authoritative for grouping; the meaning of a session is ours | same | Medium-high: 0 multi-tray sessions, 0 with two identification times; 2 crossover IDs | A session is not a person |
| 3 | Total selected weight of a meal | (none in source) | **Derived** from 1 and 2 as `derived_selected_meal_weight_g` | LAST TRAY | model table | session | at run | **Ours; DERIVED**, never source-authoritative | computed | Additive: repeats are scoops, not cumulative readings | Checkout total (WnD) unavailable |
| 4 | Which export a session belongs to | filename prefix | file names | unknown | n/a | file | n/a | **Labels only**, undefined by the source | n/a | Low: meaning unknown; registered-export vs non-registered-export differ sharply | Meaning of the labels |
| 5 | External conditions | `t2m`, `ws_10min`, `r_1h`, `ri_10min` | **FMI observations** (fmi::observations::weather::simple) | Finnish Meteorological Institute | XML (WFS 2.0) | station × hour | historical | Authoritative for weather; **not a restaurant fact** | HTTP GET, 7 chunks, no key | High: 1,129 of 1,129 hours; 3 NULL precipitation values; `r_1h` is hour-ending | Regional station (about 6 km, approximate) |
| 6 | Source definitions and limits | catalogue pages | **Flavoria Data Catalog** | Flavoria | HTML | source level | reconstructed during 2026 | Authoritative for definitions; warns of gaps | HTTP GET | Medium | Access status unspecified for most sources |
| 7 | What was consumed | none anywhere | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | **UNKNOWN** |
| 8 | What was thrown away | waste weight per tray, time, waste point | **Flavoria Lunch Line Waste** | Flavoria | n/a (MQTT / restricted repository) | per tray total | live since 2019 | Authoritative for waste | **none** (`"TODO, Ask!"`) | Doc warns of imputed days, ~3 g napkin error, unattributable waste | **SOURCE GAP** |
| 9 | Independent check of plate weight | checkout plate total, ±5 g | **Weigh & Dine** | Flavoria | n/a | per transaction | n/a | Authoritative for checkout weight | docs only | n/a | No sample; **no component weights** (different system) |
| 10 | Did the tray become a paid meal | transaction | Cash Register | Restaurant operator | n/a | per transaction | n/a | Authoritative | restricted | n/a | Restricted |
| 11 | Occupancy / repeat-diner behaviour | occupancy; MyFlavoria identity | Building Data; MyFlavoria | Flavoria | n/a | n/a | n/a | n/a | not attempted | n/a | Unspecified / research-controlled |

## Reading the map

- **Retrieved:** rows 1, 2, 5, 6.
- **Derived by us:** row 3 (always labelled).
- **Labels only:** row 4 (a filename fact, not a business fact).
- **SOURCE GAP:** rows 8-11; row 8 decides the business question.
- **UNKNOWN:** row 7. Consumption is not a missing file; it is a quantity nobody measures.

## Authority conflicts and how they were resolved

| Conflict | Resolution |
|---|---|
| Plan said the meal total came from Weigh & Dine | Wrong system. The public CSV is the lunch line: component weights, no total (D2, D3) |
| Same `session_id` in both exports (`session2266`, `session3222`) | No authority chosen; both quarantined (D6) |
| Same scale, same time, different component name across exports | The scale is the stable key; the name is a lookup. Component identity is LIMITED in 2020-10-05..16; no alias table (D18) |
| One file's clock differs by exactly 3 h from the other export's copy of the same session | +3h normalisation, evidence-backed, not source-confirmed (D4) |
| Row order disagrees with time order | Parsed time wins; row order is never trusted (D22) |

## What each source may be used for

| Source | May support | Must not be used to claim |
|---|---|---|
| FlavoriaFoodWeight1700 | M1-M5, diagnostics, sensitivity | consumption, waste, unique diners, demand |
| FMI | S1 context, descriptive association | causality, on-site conditions |
| Flavoria Data Catalog | source definitions, gap register | data values |
