# Source Map

Sources are mapped in this order: **Problem → Questions → Information → Fields → Sources.** "Relevant does not mean authoritative."

**Problem.** Can we reconstruct a trustworthy operational view of dining measurements from the available source data, and is that evidence sufficient to support future food-waste decisions? (`business_question.md`)

This is an FDE-style reconstruction using publicly available Flavoria research data and public weather data. It is not an analysis of Flavoria's proprietary operational systems. Visual: `diagrams/source-map.png`. Source availability was re-verified against primary sources on 2026-09-18 and 2026-09-19.

## 1. Questions → information → fields

| Question the problem raises | Information needed | Fields | Source class |
|---|---|---|---|
| What was placed on the tray, and how much of each component? | one component weighing event | `component_name`, `weight_of_a_component`, `weighing_event_time`, `scale_identifier` | primary measurement |
| Which events belong to one tray pass? | a session grouping | `session_id`, `tray_id`, `user_identification_time` | primary measurement |
| What is the total selected weight of a meal? | a sum over one session | none in the source; derived as `derived_selected_meal_weight_g` | derived by us |
| What were the outdoor conditions at meal time? | hourly weather | `t2m`, `ws_10min`, `r_1h`, `ri_10min` | weather enrichment |
| What do the sources define, and where are the gaps? | source definitions and access status | catalogue pages | contextual documentation |
| What was thrown away? | waste weight per tray | waste weight, time, waste point | source gap |
| What was actually consumed? | none | none | not measured anywhere |

## 2. Sources

| Source | Class | Information needed | Key fields | Grain | Owner / publisher | Authority | Freshness / period | Retrieval | Licence / access | Reliability | Known gaps | Authoritative for the question? |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **FlavoriaFoodWeight1700** (Zenodo record 5850856, v1.0.0, CSV archive) | primary measurement data | component weights and session grouping | `session_id`, `tray_id`, `scale_identifier`, `component_name`, `weight_of_a_component`, event times | one component weighing event (12,284 rows in 11 files) | University of Turku and University of Helsinki researchers (Zenodo) | authoritative for what the scales recorded | static; 2020-10-05..2020-11-20 (35 weekday lunches); published 2022-06-10 | one explicit HTTP GET; MD5 matched Zenodo, SHA-256 pinned | CC BY 4.0, open access | medium: 7 of 11 files lack a column, row order not chronological, one file 3 h off, names disagree across exports in 2020-10-05..16 | no total weight; no waste; names are a menu lookup; the two export labels are undefined | **yes, for selected-meal measurement; no, for consumption or waste** |
| **FMI open data, weather API** (`fmi::observations::weather::simple`, Turku Artukainen, FMISID 100949) | weather enrichment | outdoor context by hour | `t2m`, `ws_10min`, `r_1h`, `ri_10min` | one station × one hour (1,129 hours) | Finnish Meteorological Institute | authoritative for weather; not a restaurant fact | historical, covering the study period | seven chunked HTTP GETs, no key | CC BY 4.0 (verified on the FMI licence page) | high: 1,129 of 1,129 hours, 3 NULL precipitation values; `r_1h` is hour-ending | regional station about 6 km away | **yes, for context only** |
| **Flavoria Data Catalog** | contextual documentation | what sources exist, how they are described, and their access status | catalogue pages | source level | Flavoria Research Infrastructure, University of Turku | authoritative for definitions; warns it is being reconstructed in 2026 and may be wrong or incomplete | pages last updated 2026-04-09 | HTTP GET, read only; no data is taken | no terms found on the pages; short quotations with links only | medium | access status unspecified for most sources | no (documentation, not data) |
| **Flavoria Weigh & Dine documentation** | contextual documentation; source-gap evidence | independent check of plate weight | checkout plate total (±5 g) | one checkout transaction | Flavoria | authoritative for checkout weight | n/a | documentation only; no sample | no data access | n/a | no sample; no component weights; a different system from the public CSV | no (no data) |
| **Flavoria Lunch Line Waste documentation** | source-gap documentation | waste weight per tray | waste weight, time, waste point | one tray total | Flavoria | authoritative for waste | live since 2019 according to the page | none: sample section reads "TODO, Ask!"; detail in a restricted repository; MQTT for authorised users | restricted; no public download, API, schema or contact | the page warns of imputed days and about 3 g napkin error | everything: there is no public data | **it would be authoritative for waste, but it is not accessible: SOURCE GAP** |

Other documented systems (Cash Register, Building Data, MyFlavoria, Surveys) are restricted or unspecified and were not attempted.

## 3. Reading the map

- **Retrieved:** FlavoriaFoodWeight1700 and FMI weather (plus catalogue pages read as documentation).
- **Derived by us:** the meal-level weight, always labelled `derived_selected_meal_weight_g`.
- **Labels only:** the population labels are filename prefixes, not business facts.
- **SOURCE GAP:** waste (decides the business question), checkout total, cash register, occupancy, person identity.
- **UNKNOWN:** consumption. It is not a missing file but a quantity nobody measures.

## 4. Authority conflicts and how they were resolved

| Conflict | Resolution |
|---|---|
| An early assumption was that the meal total came from Weigh & Dine | Wrong system. The public CSV is the lunch line: component weights, no total (D2, D3) |
| The same `session_id` appears in both exports (`session2266`, `session3222`) | No authority chosen; both quarantined (D6) |
| Same scale, same time, different component name across exports | The scale is the stable key; the name is a lookup. Component identity is LIMITED in 2020-10-05..16; no alias table (D18) |
| One file's clock differs by exactly 3 h from the other export's copy of the same session | +3h normalisation, evidence-backed, not source-confirmed (D4) |
| Row order disagrees with time order | Parsed time wins; row order is never trusted (D22) |

## 5. What each source may be used for

| Source | May support | Must not be used to claim |
|---|---|---|
| FlavoriaFoodWeight1700 | M1-M5, diagnostics, sensitivity | consumption, waste, unique people, how many people came |
| FMI | S1 context, descriptive association | causality, on-site conditions |
| Flavoria Data Catalog | source definitions, the gap register | data values |
| Weigh & Dine and Lunch Line Waste documentation | the source-gap register | any figure |

The complete gap register is `source_gap_register.md`; the machine-readable pins are `config/sources.yml`; provenance and licences are in `data_provenance.md` and `NOTICE`.
