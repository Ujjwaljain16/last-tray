# Source map

I mapped my sources in this order: **Problem → Questions → Information → Fields → Sources.** Something being relevant doesn't make it authoritative, so I kept those two ideas apart the whole way through.

**Problem.** Can I reconstruct a trustworthy operational view of dining measurements from the available source data, and is that evidence enough to support a future food-waste decision? This is deliberately a question about measurement, not about waste. My initial review established that waste data isn't publicly retrievable, so the honest thing I can actually deliver is a dependable reconstruction of what *is* measured, plus a precise statement of what isn't.

This is an FDE-style reconstruction using publicly available Flavoria research data and public weather data. It is not an analysis of Flavoria's proprietary operational systems. Visual: `diagrams/source-map.png`. I re-verified source availability against primary sources on 2026-09-18 and 2026-09-19.

**Stakeholders, and the decision this map supports.**

| Stakeholder | What they need to know | What they must not be told |
|---|---|---|
| Restaurant operations manager | What is selected at the line and how variable it is | That volume counts are demand |
| Kitchen manager | Whether the median tray load is stable enough to discuss | That derived weight equals consumption |
| Sustainability / waste lead | Which data to procure to link selection to waste | Any waste number |
| Data / engineering team | That results reproduce and how fragile they are | That an assumption was safe because it was convenient |

**The decision this can support right now:** don't launch a waste-reduction measurement programme on this data. Use the derived selected-weight evidence for portioning conversations, for the registered-export population only, and go request the waste extract named in section 6 below.

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

Other documented systems (Cash Register, Building Data, MyFlavoria, Surveys) are restricted or unspecified, and I didn't attempt them; the full register is section 6.

## 3. Reading the map

- **Retrieved:** FlavoriaFoodWeight1700 and FMI weather (plus catalogue pages, which I read as documentation only).
- **Derived by me:** the meal-level weight, always labelled `derived_selected_meal_weight_g`.
- **Labels only:** the population labels are filename prefixes, not business facts I get to interpret.
- **SOURCE GAP:** waste (this is the one that actually decides the business question), checkout total, cash register, occupancy, person identity.
- **UNKNOWN:** consumption. This isn't a missing file, it's a quantity nobody measures anywhere I can see.

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

The machine-readable pins live in `config/sources.yml`; provenance and licences are in `data_provenance.md` and `NOTICE`.

## 6. Full gap register

I verified this on 2026-09-18 against primary sources. "Not ingested" doesn't mean "forgotten", each row here is a real data gap I know about. Three of them are the ones that actually decide the business question: waste, consumption, and what the population labels mean.

| Required business fact | Expected source | Publicly accessible? | Actual access status (evidence) | Why it matters | Impact on this project | Future integration required |
|---|---|---|---|---|---|---|
| Plate waste per tray | Flavoria Lunch Line Waste | **No** | Doc page: sample section reads "TODO, Ask!"; detail in a restricted repository; MQTT feed for authorised users only. No public download, API, schema or contact address. | Waste = selected minus returned. Without it, no waste KPI can exist. | Waste KPI = `SOURCE GAP`; `waste_weight_g` stays NULL, never 0 | Request extract (tray_id, waste_time, waste_g, waste_point, imputed flag); join on tray_id + time window |
| Total plate weight at checkout | Weigh & Dine (cash register scale) | No sample | Doc describes it; no data link | Independent check on the sum of component weights | Not available; selected weight is derived by summing component events | Extract of Weigh & Dine transactions; reconcile against derived selected weight |
| Consumption | (none) | n/a | Never measured directly anywhere; only derivable as selected minus waste | The real business quantity | UNKNOWN | Needs waste plus a reconciliation rule |
| Transaction / cash register link | Cash Register | Restricted | Catalogue: restricted, operator approval | Confirms a tray became a paid meal | Not available | Operator approval |
| Building occupancy / footfall | Building Data | Unspecified | Not documented publicly | Denominator for demand | Not available | Request access |
| Person-level identity | MyFlavoria | Research-controlled | Registered-export files carry no user id | Repeat-visit behaviour | Not needed; a session is not a person | n/a |
| Weather | FMI open data | Yes | Retrieved, no API key | Context | Available | none |
| Images for meals | Zenodo image archive (2.4 GiB) | Yes | Not downloaded | Not needed for any core metric | Out of scope | optional |
| Menu / component metadata (diet, allergens) | Kitchen Menu | Unspecified | Not in the CSV archive | Component grouping, dietary breakdown | Component names only | Menu extract |
