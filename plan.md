Yes. I’ve now tightened this into a **real FDE-grade PRD + TRD**, with the public-data constraints treated as part of the design rather than something we hide.

One important change from the earlier idea: **we are not going to pretend that Flavoria’s restricted plate-waste data is publicly downloadable.** The official Flavoria catalogue says the waste system has historical data since 2019, but its public sample is currently listed as “TODO, Ask!”, while some related building data is restricted. ([Flavoria Data Catalog][1])

That actually makes the project stronger from an FDE perspective: **we build the MVP from sources we can really retrieve, and explicitly document the missing source needed to close the waste-measurement loop.**

# LAST TRAY

## Flavoria DiningOps Truth

### A dependable data pipeline for meal measurement, dining behavior, and food-waste readiness

---

# 1. Executive Definition

**LAST TRAY** is an FDE-style data product built around the real **Flavoria Research Restaurant** at the University of Turku.

Flavoria is a real research restaurant/living lab with intelligent lunch lines, weighing systems, bio-waste stations, customer research, environmental/building sensors and other operational data sources. Its purpose includes studying food choices, dining behaviour and food waste in a real restaurant environment. ([UTU][2])

Our project asks:

> **Can we build a trustworthy operational view of what diners select and how much they take, connect that behaviour to time and environmental context, and determine what additional data is required before the restaurant can confidently use the pipeline for food-waste decisions?**

The output is **not an ML model** and not a decorative dashboard.

It is:

```text
real source
    ↓
retrieval
    ↓
raw preservation
    ↓
profiling
    ↓
validation
    ↓
reconciliation
    ↓
business model
    ↓
metrics
    ↓
evidence
    ↓
decision
```

That is directly aligned with the course progression:

> Understand → Retrieve → Trust → Model → Pipeline. 

---

# PART A — PRD

# 2. Client Scenario

### Simulated client

**Flavoria Dining Operations**

This is a simulated FDE engagement using real public Flavoria research data.

We will state clearly in the repository:

> The client scenario and operational decision context are simulated for educational purposes. The underlying source data and source documentation are publicly published by the University of Turku and associated researchers.

We are **not** claiming to work for University of Turku, Flavoria, Sodexo, Dining Flow, or any of their partners.

Flavoria itself is a multidisciplinary research platform and real restaurant environment. Its intelligent lunch lines and bio-waste stations collect data about food choices and waste, and the Dining Flow project explicitly aimed to create data-driven decision support for self-service restaurants. ([UTU][2])

---

# 3. Business Problem

A self-service restaurant wants to reduce food waste without hurting the dining experience.

However, the operational picture is fragmented.

Different systems observe different pieces:

```text
Lunch line
    ↓
what was selected

Weighing
    ↓
how much food was taken

Cash register
    ↓
transaction / service event

Waste system
    ↓
what was discarded

Building / environmental systems
    ↓
visitor-flow and contextual signals

Weather
    ↓
external environmental context
```

Flavoria's own documentation describes these as separate data areas, including lunch-line weighing, cash-register records, kitchen/menu data, waste measurements, MyFlavoria, surveys, building data and other sensors. ([Flavoria Data Catalog][3])

The business problem is therefore not merely:

> “How much food is wasted?”

It is:

> **“Can we establish a trustworthy chain from diner behaviour to an operational waste decision?”**

---

# 4. Why this is an FDE problem

The FDE must answer:

### Where does the truth live?

### What does each source actually measure?

### What is the grain of each record?

### Can the sources be joined?

### Which measurements are authoritative?

### What data-quality issues exist?

### What can we calculate confidently?

### What can we not calculate?

### What source is missing?

That mirrors the Class 4 framework:

> **Problem → Questions → Information → Fields → Sources**

and the requirement to identify source ownership, freshness, trust and gaps before writing the pipeline.  

---

# 5. Primary Business Objective

Build a **dependable meal-session evidence layer** that allows restaurant operations to understand:

1. how much diners take,
2. which food combinations/meal compositions are selected,
3. how portion sizes vary,
4. how dining volume and meal characteristics change with environmental context,
5. whether the available data is sufficient to connect these observations to actual waste.

---

# 6. Product Scope

We divide the project into two explicit scopes.

## MVP — Guaranteed reproducible

Uses only data that we can publicly retrieve and place in the repository.

```text
FlavoriaFoodWeight1700
        +
Finnish Meteorological Institute weather
```

The open FlavoriaFoodWeight1700 dataset contains about 2,000 meal images plus measured meal contents, with the records linked through RFID tags on meal trays. A CSV-only archive is available, separate from the much larger image archive. ([Zenodo][4])

The Finnish Meteorological Institute provides machine-readable historical weather observations through its open-data WFS interfaces. ([Finnish Meteorological Institute][5])

---

## Phase 2 — Documented but not required for MVP

Flavoria's:

```text
Plate Waste
Kitchen Waste
Building / Occupancy
MyFlavoria
Surveys
```

are documented as potential operational sources, but we will **not fabricate records where public access is unavailable**.

The official catalogue currently says the plate-waste sample is “TODO, Ask!” and that some data are available only through restricted/internal access. ([Flavoria Data Catalog][1])

This becomes an explicit **source gap**.

---

# 7. Primary KPI

Since the public waste dataset is not guaranteed to be downloadable, we must not invent a waste KPI.

Therefore the MVP primary KPI is:

# **Median Plate Load per Dining Session**

```text
median(total meal weight in grams)
```

Population:

> valid meal-session records with a trustworthy measured total weight.

This is directly connected to the restaurant's portioning and consumption workflow.

Flavoria's Weigh & Dine documentation states that its weighing system records the weight of the total plate contents in grams. ([Flavoria Data Catalog][6])

---

# 8. Secondary KPIs

## KPI 2 — Meal Session Volume

```text
valid dining sessions per day
```

This provides operational demand context.

We will not call this:

> “number of diners”

unless the source actually supports that interpretation.

A tray/session record and a unique person are different grains.

That distinction is intentional.

---

## KPI 3 — Portion Variability

```text
P90 meal weight
−
P10 meal weight
```

or report:

```text
P50
P75
P90
IQR
```

Purpose:

> determine whether portion sizes are stable or highly variable.

---

## KPI 4 — Component Selection Breadth

For each meal session:

```text
number of distinct food components selected
```

Then aggregate:

```text
median components/session
distribution of component count
```

This uses the measured food-content side of the Flavoria dataset.

We will not assume the exact field structure until we inspect the downloaded CSV.

---

## KPI 5 — Measurement Readiness Rate

This is our deliberately FDE-style KPI.

```text
sessions with:
    valid timestamp
    valid meal content
    valid weight
    successful weather join
──────────────────────────────────
eligible meal sessions
```

This tells the operations team:

> **“How much of our observed meal activity is actually usable for cross-source analysis?”**

A dataset being present does not mean it is decision-ready.

---

# 9. Optional Waste KPI

If Flavoria later provides an accessible waste sample:

```text
Plate Waste per Dining Session
=
validated waste grams
──────────────────────
eligible dining sessions
```

and:

```text
Waste-to-Selected-Weight Ratio
=
waste grams
──────────────
selected meal grams
```

But these are **Phase 2 outputs**, not MVP claims.

The official waste documentation says Flavoria's system collects individual customer waste totals and links them to lunch-line/tray data, but also warns about hardware/connectivity gaps, manual imputing and incomplete attribution. ([Flavoria Data Catalog][1])

---

# 10. Stakeholders

## Restaurant Operations Manager

Needs:

> What are customers taking, and how variable are the portions?

## Kitchen Manager

Needs:

> Is the observed demand/portion pattern stable enough to inform preparation decisions?

## Sustainability / Waste Lead

Needs:

> Can meal-selection data actually be linked to measured waste?

## Data / Engineering Team

Needs:

> Are the metrics reproducible and trustworthy?

## Researchers / Analysts

Need:

> source lineage, grain, data-quality evidence, and explicit limitations.

---

# 11. The Core Business Questions

Our project will answer:

### Q1

How many valid meal sessions are represented in the public dataset?

### Q2

What does a typical selected meal weigh?

### Q3

How variable are meal weights?

### Q4

Which component-selection patterns are associated with larger or smaller meal loads?

### Q5

Does dining behaviour vary across days/time periods and external weather conditions?

### Q6

Which parts of the end-to-end waste workflow are directly observable?

### Q7

Which critical business events remain unmeasured?

This last question is extremely important.

---

# 12. Source Map

## Source 1 — FlavoriaFoodWeight1700

[FlavoriaFoodWeight1700 on Zenodo — official dataset record](https://zenodo.org/records/5850856?utm_source=chatgpt.com)

Provider:

> University of Turku + University of Helsinki researchers.

Format:

> TAR containing CSV; optional 2.6 GB image archive.

The record identifies the dataset as open and provides a 1.3 MB CSV-only archive alongside the much larger image package. ([Zenodo][4])

Purpose:

> primary meal-session observations.

Expected concepts:

```text
meal/session identifier
timestamp
meal contents
measured contents/weight
```

Exact field names will be frozen after first ingestion.

---

# 13. Source 2 — Finnish Meteorological Institute

[FMI Open Data](https://en.ilmatieteenlaitos.fi/open-data?utm_source=chatgpt.com)

[FMI time-series API documentation](https://en.ilmatieteenlaitos.fi/open-data-manual-time-series-data?utm_source=chatgpt.com)

Provider:

> Finnish Meteorological Institute.

Format:

> machine-readable WFS API.

Purpose:

> external environmental context.

We will retrieve:

```text
timestamp
temperature
precipitation
rain
wind
```

as appropriate to the observed date range.

The FMI officially provides downloadable historical observations and machine-readable WFS interfaces. ([Finnish Meteorological Institute][5])

---

# 14. Source 3 — Flavoria Data Catalog

[Flavoria Research Infrastructure Data Catalog](https://flavoriadatacatalog.tt.utu.fi/?utm_source=chatgpt.com)

This is primarily a **source-discovery / metadata source**, not a core fact table.

It establishes that Flavoria has:

```text
Cash Register
Kitchen / Menu
Kitchen Waste
Lunch Line
Lunch Line Waste
Weigh & Dine
MyFlavoria
Surveys
Building Data
Other sensors
ResQ
```

and documents their relationships and restrictions. ([Flavoria Data Catalog][3])

This source will support our:

```text
source map
ownership analysis
source-of-truth decisions
known/unknown section
```

---

# 15. Source 4 — Flavoria Waste Documentation

[Flavoria Plate Waste Data documentation](https://flavoriadatacatalog.tt.utu.fi/docs/lunch-line/lunch-line-waste/?utm_source=chatgpt.com)

We use this as **source-definition evidence**, not an MVP raw-data dependency.

It tells us:

* customer waste is collected through four waste points,
* tray RFID connects waste information to lunch-line selections,
* historical collection exists since 2019,
* measurements can be viewed near real-time,
* some days require manual imputing,
* daily waste totals are not fully accurate,
* waste cannot currently be attributed to all meals. ([Flavoria Data Catalog][1])

This is incredibly useful for our FDE assessment.

---

# 16. Source 5 — Published Flavoria Research

The 2025 *Applied Computing and Intelligence* paper describes a real Flavoria data collection effort using RFID/sensor data from 2019–2024, including food selections, customer-flow data, menu information, weather and public holidays. ([AIMS Press][7])

We use this paper for:

```text
provenance
domain validation
understanding the real collection workflow
sanity checks
```

We will **not reproduce the paper's ML model**, because the assignment explicitly prohibits training an ML model.

---

# 17. Why Weather Is in the Project

Weather is not being added because:

> “weather sounds cool.”

There is documented evidence that Flavoria research has combined dining behaviour with external weather data. The published 2025 study used local weather data as an external feature when analysing customer flow. ([AIMS Press][7])

So our weather integration is:

```text
meal behaviour
      +
external environment
```

rather than an arbitrary enrichment.

---

# 18. Source-of-Truth Decisions

## Meal session

Primary:

> Flavoria meal/tray record in the published dataset.

Not:

> weather record.

Not:

> research paper summary.

---

## Weight

Primary:

> measured plate/meal weight from the source record.

Flavoria's Weigh & Dine documentation specifically describes a trading-approved scale and total plate-content weight in grams. ([Flavoria Data Catalog][6])

---

## Meal component

Primary:

> source-provided component record.

No component-level weight will be invented.

The Flavoria WnD documentation explicitly says there is **no individual component weight** in that system. ([Flavoria Data Catalog][6])

---

## Weather

Primary:

> FMI observation.

Weather is contextual, not an operational meal fact.

---

## Waste

For MVP:

> **unknown / unavailable as raw public data**

We do not create waste measurements.

---

# 19. The Big FDE Judgment Call

This is the centerpiece.

## **“Selected food weight is not food waste.”**

We may observe:

```text
meal selected = 640g
```

That does **not** mean:

```text
consumed = 640g
```

and certainly doesn't mean:

```text
waste = Xg
```

without an appropriate waste observation.

The real Flavoria environment does have a separate waste system, and the official documentation explains how it connects waste observations with lunch-line/tray information. ([Flavoria Data Catalog][1])

Our pipeline will therefore maintain:

```text
selected_weight_g
```

and:

```text
waste_weight_g
```

as fundamentally different concepts.

If `waste_weight_g` is unavailable:

```text
waste_weight_g = NULL
```

not zero.

That distinction will be visible in the final report.

---

# 20. Workflow Model

The business workflow:

```text
                    DINING SESSION
                          │
                          ▼
                    Take tray
                          │
                          ▼
                 Select food items
                          │
                          ▼
                 Weigh selected meal
                          │
                          ▼
                  Cash register
                          │
                          ▼
                        Eat
                          │
                          ▼
                  Return tray/plate
                          │
                          ▼
                 Waste measurement
                          │
                          ▼
                     Waste data
```

The public MVP gives us strong evidence around:

```text
select
→ weigh
→ record
```

The waste stage is documented by Flavoria but not necessarily publicly downloadable.

That makes the missing link explicit rather than pretending it exists.

---

# 21. Entity Model

```text
                    Customer/Anonymous Session
                              │
                              │
                              ▼
                        Dining Session
                              │
                ┌─────────────┼──────────────┐
                │             │              │
                ▼             ▼              ▼
          Meal Component   Meal Weight    Timestamp
                │
                ▼
           Menu Metadata

                              │
                              ▼
                         Weather Context
```

Future:

```text
Dining Session
      │
      ▼
Waste Observation
```

but only when the required source is available.

---

# 22. Relational Model

```text
dim_date
--------
date
day_of_week
month
year

dim_meal_component
------------------
component_id
component_name
diet
allergens

fact_dining_session
-------------------
session_id
timestamp
date
meal_weight_g
component_count
source
data_quality_status

fact_session_component
----------------------
session_id
component_id

fact_weather
------------
timestamp
temperature_c
precipitation_mm
rain_mm
wind_speed
source

fact_validation_issue
---------------------
issue_id
source
record_id
rule_id
severity
message
```

---

# 23. Analytical Grain

This is very important.

## `fact_dining_session`

> **one dining-session observation**

## `fact_session_component`

> **one selected component within a dining session**

## `fact_weather`

> **one weather observation at the chosen time resolution**

We will not join tables until their grains are established.

This follows the course's explicit instruction to investigate **definition and data grain** when different systems disagree. 

---

# 24. Temporal Join

Weather is hourly.

Meal sessions may be timestamped more precisely.

We will map each meal session to:

```text
same local date/hour
```

rather than arbitrarily matching the nearest weather observation.

The join rule will be documented as:

```text
meal_timestamp
      ↓
local timezone normalization
      ↓
truncate to weather observation hour
      ↓
join weather
```

---

# 25. Data Quality Rules

## Structural

```text
required identifier is present
timestamp parses
weight is numeric
```

## Range

```text
meal_weight_g > 0
meal_weight_g < defined physical plausibility threshold
```

The threshold will be based on observed distribution and documented rather than chosen arbitrarily.

---

## Temporal

```text
timestamp is valid
timezone treatment explicit
```

---

## Uniqueness

```text
session_id uniqueness
```

---

## Component consistency

```text
session component count
=
number of distinct associated components
```

after accounting for source-specific representation.

---

## Weather join completeness

```text
meal sessions matched to weather
/
eligible meal sessions
```

---

# 26. We Will Investigate, Not Automatically Delete, Suspicious Data

Example:

```text
session weight = 0g
```

→ validation violation.

Example:

```text
session weight = 4,000g
```

→ suspicious.

Example:

```text
duplicate session identifier
```

→ investigate.

We will never simply:

```python
df = df.dropna()
```

and move on.

That would violate the spirit of Class 6 and the explicit course instruction to understand missing values, duplicates and validation rather than silently hiding them. 

---

# 27. Data Quality Status

Each record gets:

```text
VALID
WARN
INVALID
```

Example:

```text
VALID
  complete identifiers
  valid timestamp
  plausible weight

WARN
  missing weather
  unusual weight
  incomplete component metadata

INVALID
  impossible timestamp
  missing required identifier
  structurally corrupt record
```

---

# 28. Metric Definitions

## M1 — Median Plate Load

```text
median(meal_weight_g)
```

Population:

> valid dining sessions.

---

## M2 — P90 Plate Load

```text
P90(meal_weight_g)
```

Purpose:

> identify high-end portion loads.

---

## M3 — Portion Variability

```text
IQR(meal_weight_g)
```

or:

```text
P90 - P10
```

We will report one consistently.

---

## M4 — Meal Session Volume

```text
COUNT(valid session_id)
```

grouped by day/time.

---

## M5 — Measurement Readiness

```text
valid sessions with complete
cross-source context
────────────────────────────
eligible sessions
```

This is our data-product health KPI.

---

# 29. Optional Phase-2 Waste Metrics

Once waste data is legitimately accessible:

```text
M6 — Plate Waste per Session
M7 — Waste / Selected Weight
M8 — Waste by Meal Composition
M9 — Waste Measurement Coverage
M10 — Selection-to-Waste Reconciliation Rate
```

But these will remain **future-scope until raw data access is established**.

---

# 30. Analysis Dimensions

We will investigate:

```text
day of week
time of day
meal component
component count
meal weight band
weather condition
precipitation
season/date period
```

We will **not** claim causality.

For example:

> rainy days had lower median meal weight

is acceptable if supported.

> rain caused diners to select smaller meals

is not automatically established.

---

# 31. The "Measurement Truth" Layer

This is the distinctive feature of the project.

For every KPI:

```text
Metric
  │
  ├── Source
  ├── Grain
  ├── Definition
  ├── Population
  ├── Validation
  ├── Exclusions
  └── Limitations
```

The output isn't simply:

```text
Median meal weight = 642g
```

It becomes:

```text
Median meal weight
642g

Population:
valid meal sessions

Source:
FlavoriaFoodWeight1700

Weight source:
measured

Weather:
FMI

Quality:
X records excluded

Limitation:
does not measure plate waste
```

That's what makes it trustworthy.

---

# 32. Technical Requirements Document

# 33. Technology Stack

```text
Python 3.12+
Pandas
Requests
SQLite
PyArrow
pytest
Matplotlib
```

Optional:

```text
DuckDB
```

but not necessary.

---

# 34. Project Structure

```text
last-tray/
│
├── README.md
├── requirements.txt
├── LICENSE
├── .gitignore
│
├── docs/
│   ├── PRD.md
│   ├── TRD.md
│   ├── source_map.md
│   ├── data_dictionary.md
│   ├── metric_definitions.md
│   ├── validation_rules.md
│   ├── source_of_truth.md
│   ├── assumptions_limitations.md
│   └── judgement_call.md
│
├── diagrams/
│   ├── source-map.png
│   ├── workflow.png
│   ├── data-model.png
│   └── pipeline.png
│
├── data/
│   ├── raw/
│   │   ├── flavoria/
│   │   └── weather/
│   │
│   ├── staging/
│   └── processed/
│
├── src/
│   ├── config.py
│   │
│   ├── ingest/
│   │   ├── flavoria.py
│   │   └── weather.py
│   │
│   ├── profile/
│   │   └── profiler.py
│   │
│   ├── validate/
│   │   ├── schema.py
│   │   ├── business_rules.py
│   │   ├── completeness.py
│   │   └── report.py
│   │
│   ├── transform/
│   │   ├── sessions.py
│   │   ├── components.py
│   │   └── weather.py
│   │
│   ├── model/
│   │   └── build_model.py
│   │
│   ├── metrics/
│   │   └── kpis.py
│   │
│   └── pipeline/
│       ├── run.py
│       └── manifest.py
│
├── notebooks/
│   ├── 01_source_exploration.ipynb
│   ├── 02_profiling.ipynb
│   ├── 03_validation.ipynb
│   └── 04_metrics.ipynb
│
├── outputs/
│   ├── validation/
│   ├── metrics/
│   ├── reconciliation/
│   └── evidence/
│
├── logs/
│
└── tests/
    ├── test_ingest.py
    ├── test_validation.py
    ├── test_model.py
    ├── test_metrics.py
    └── test_pipeline.py
```

---

# 35. Retrieval Requirements

## Flavoria

Input:

```text
Zenodo TAR
   ↓
extract CSV
   ↓
preserve original
   ↓
validate file
   ↓
load staging
```

We should use the **1.3 MB CSV-only archive**, not the 2.6 GB image archive, for the MVP. The image archive remains an optional extension. ([Zenodo][4])

---

## FMI

```text
HTTP GET / WFS
        ↓
raw response
        ↓
persist
        ↓
parse
        ↓
normalize
```

---

# 36. Raw Data Preservation

```text
data/raw/flavoria/
    flavoriafoodweight1700.tar
```

or, after extraction:

```text
data/raw/flavoria/
    original/
        ...
```

Weather:

```text
data/raw/weather/
    turku_YYYY-MM-DD_YYYY-MM-DD.json
```

or the exact machine-readable FMI response format.

We retain the original retrieved artifact.

---

# 37. Source Manifest

Each run records:

```json
{
  "source": "flavoriafoodweight1700",
  "retrieved_at": "...",
  "source_url": "...",
  "file_hash": "...",
  "rows_read": 0,
  "status": "success"
}
```

Same for weather.

---

# 38. Pipeline Architecture

```text
               ┌─────────────────────────┐
               │ Flavoria FoodWeight1700 │
               └────────────┬────────────┘
                            │
                            ▼
                     RAW FLAVORIA
                            │
                            │
               ┌────────────┴────────────┐
               │                         │
               ▼                         ▼
          PROFILE                    VALIDATE
               │                         │
               └────────────┬────────────┘
                            ▼
                     STAGING DATA
                            │
                            │
              ┌─────────────┴─────────────┐
              │                           │
              ▼                           ▼
        WEATHER API                 MENU/COMPONENT
              │                           │
              └─────────────┬─────────────┘
                            ▼
                     RECONCILIATION
                            │
                            ▼
                      DATA MODEL
                            │
                            ▼
                         KPIs
                            │
                            ▼
                      EVIDENCE
```

---

# 39. Pipeline Command

One command should reproduce the output:

```bash
python -m src.pipeline.run
```

Optional arguments:

```bash
python -m src.pipeline.run \
    --start-date 2020-01-01 \
    --end-date 2020-12-31 \
    --refresh-weather
```

Exact date options will be determined once the dataset is inspected.

---

# 40. Pipeline Stages

### Stage 1 — Source discovery

```text
check expected source files
```

### Stage 2 — Raw retrieval

```text
download/copy source
```

### Stage 3 — Raw preservation

```text
hash
save
manifest
```

### Stage 4 — Profiling

```text
rows
columns
nulls
uniques
duplicates
ranges
```

### Stage 5 — Validation

```text
schema
business rules
temporal
identifier
```

### Stage 6 — Transformation

```text
normalize timestamps
normalize component names
derive session metrics
```

### Stage 7 — Weather retrieval

```text
FMI API
```

### Stage 8 — Cross-source join

```text
session timestamp
        ↓
weather timestamp
```

### Stage 9 — Analytical model

```text
SQLite / Parquet
```

### Stage 10 — Metrics

```text
KPIs
```

### Stage 11 — Evidence

```text
CSV + Markdown
```

---

# 41. SQLite Schema

We'll create:

```text
last_tray.db
```

with:

```text
dim_date
dim_component
fact_dining_session
fact_session_component
fact_weather
fact_validation_issue
pipeline_run
```

This gives us an explicit SQL layer even though the raw dataset originates as a file.

---

# 42. SQL Queries

Examples:

```sql
SELECT
    DATE(timestamp) AS service_date,
    COUNT(*) AS sessions,
    MEDIAN(meal_weight_g)
FROM fact_dining_session
WHERE data_quality_status = 'VALID'
GROUP BY DATE(timestamp);
```

And:

```sql
SELECT
    component_id,
    COUNT(DISTINCT session_id) AS sessions
FROM fact_session_component
GROUP BY component_id;
```

Exact SQL will depend on the final schema discovered from the actual file.

---

# 43. Idempotency

Running the pipeline twice with identical inputs should produce identical analytical outputs.

```text
run 1
 ↓
outputs

run 2
 ↓
same outputs
```

No blind append.

---

# 44. Error Handling

### Missing Flavoria source

```text
ERROR
pipeline stops
```

### Corrupt archive

```text
ERROR
raw artifact preserved
```

### Weather API timeout

```text
retry
backoff
```

### Weather API permanently unavailable

The meal metrics may still be generated **only if the metric does not depend on weather**, while weather-dependent metrics become:

```text
BLOCKED
```

This is better than failing the entire product unnecessarily.

---

# 45. Validation Severity

```text
INFO
WARN
ERROR
```

Examples:

```text
WARN:
missing weather observation

ERROR:
missing session identifier

ERROR:
invalid timestamp

WARN:
extreme meal weight
```

---

# 46. Reconciliation Report

We will generate:

```text
outputs/reconciliation/

weather_join_summary.csv
session_completeness.csv
component_join_summary.csv
```

Example:

| Check                    | Count | Percentage |
| ------------------------ | ----: | ---------: |
| Total source sessions    |     X |       100% |
| Valid sessions           |     X |         X% |
| Invalid sessions         |     X |         X% |
| Weather matched          |     X |         X% |
| Weather unmatched        |     X |         X% |
| Sessions with components |     X |         X% |

---

# 47. Evidence-Readiness

Every output metric should contain:

```text
metric_name
value
population
definition
source
records_used
records_excluded
status
limitation
```

Example:

```text
metric_name:
median_plate_load_g

value:
642.0

population:
valid_dining_sessions

source:
FlavoriaFoodWeight1700

status:
READY_WITH_LIMITATION

limitation:
does not measure plate waste
```

---

# 48. Tests

We don't need a giant test suite.

We need high-value tests.

### Ingestion

```text
archive exists
CSV extracted
row count > 0
```

### Validation

```text
missing IDs detected
invalid timestamps detected
negative/zero weight handled
```

### Weather

```text
API response parses
timezone normalization works
```

### Join

```text
session-to-weather mapping deterministic
```

### Metrics

```text
median correct
P90 correct
IQR correct
```

### Pipeline

```text
same input → same output
```

---

# 49. Dashboard / Evidence Output

We don't need React.

A generated Markdown/HTML evidence page is enough.

Something like:

```text
LAST TRAY — Dining Operations Evidence
──────────────────────────────────────

VALID DINING SESSIONS
12,384

MEDIAN PLATE LOAD
642 g

P90 PLATE LOAD
891 g

PORTION VARIABILITY
312 g

WEATHER JOIN COVERAGE
97.6%

MEASUREMENT READINESS
94.8%
```

Then charts:

```text
plate weight distribution
daily session volume
meal-weight trend
component frequency
weather comparison
```

---

# 50. What the Dashboard Must NOT Show

We will **not** show:

```text
"Food Waste = 0"
```

when waste data is unavailable.

We will also not show:

```text
"Waste reduction = 14%"
```

unless actual before/after waste data exists.

Instead:

```text
Waste measurement:
NOT AVAILABLE IN PUBLIC MVP DATA

Required source:
Flavoria Lunch Line Waste
```

That is much more trustworthy.

---

# 51. Known / Unknown / Assumptions / Limitations

## KNOWN

Flavoria is a real instrumented research restaurant with intelligent lunch lines and bio-waste stations. ([UTU][2])

The public FlavoriaFoodWeight1700 dataset contains approximately 2,000 meal images and measured meal-content data linked via RFID tray identifiers. ([Zenodo][4])

Flavoria's Weigh & Dine system records total plate-content weight and documents a ±5g plate-weight variance. ([Flavoria Data Catalog][6])

The official waste system records customer waste and has historical data, but public availability is currently limited. ([Flavoria Data Catalog][1])

---

## UNKNOWN

We cannot establish actual plate-waste amounts for the MVP unless the raw waste dataset becomes accessible.

We cannot infer exact food-component waste merely from selected-component data.

We cannot equate a dining session with a unique human unless the source explicitly provides that linkage.

---

## ASSUMPTIONS

A dataset row representing a meal/tray observation will be treated as one analytical dining-session observation only after confirming its actual grain.

Weather is contextual and not an operational restaurant measurement.

---

## LIMITATIONS

The public CSV dataset is relatively small compared with the broader Flavoria internal data estate.

Flavoria's current data catalogue is undergoing reconstruction in 2026, and the catalogue warns that some data may be missing or incorrect during this process. ([Flavoria Data Catalog][3])

The public WnD documentation says some components are not listed and there are no individual component weights. ([Flavoria Data Catalog][6])

Flavoria's waste documentation says daily waste data is not fully accurate and some waste cannot be attributed to individual meals. ([Flavoria Data Catalog][1])

---

# 52. The FDE "Missing Source" Register

This should be a visible artifact in the repository.

| Required business fact                 | Source                       |            Publicly available? | MVP? |
| -------------------------------------- | ---------------------------- | -----------------------------: | ---: |
| Selected meal contents                 | FlavoriaFoodWeight1700       |                            Yes |  Yes |
| Selected meal weight                   | FlavoriaFoodWeight1700 / WnD |   Yes for open dataset context |  Yes |
| Weather                                | FMI API                      |                            Yes |  Yes |
| Actual plate waste                     | Flavoria Waste System        | Not currently as public sample |   No |
| Building occupancy                     | Flavoria Building Data       |          Restricted/on request |   No |
| Individual long-term customer identity | MyFlavoria                   |            Research-controlled |   No |

The important thing is that **“not ingested” does not mean “forgotten.”**

It becomes an explicit client data gap.

---

# 53. The Final Source Architecture

```text
                     FLAVORIA
               REAL RESEARCH RESTAURANT
                          │
        ┌─────────────────┼─────────────────┐
        │                 │                 │
        ▼                 ▼                 ▼
  PUBLIC DATA         DOCUMENTED        RESTRICTED
        │                 │                 │
        ▼                 ▼                 ▼
FoodWeight1700       Waste system       Building
CSV                  documentation      occupancy
        │                 │              MyFlavoria
        │                 │              surveys
        │                 │
        └──────────┬──────┘
                   │
                   ▼
            OUR FDE PIPELINE
                   ▲
                   │
             FMI Weather API
                   │
                   ▼
              CONTEXT DATA
```

---

# 54. Why the Project Is Not Just "Analyse a Dataset"

Our pipeline explicitly reconstructs the business workflow:

```text
source discovery
      ↓
meal observation
      ↓
measurement
      ↓
environmental context
      ↓
validation
      ↓
cross-source reconciliation
      ↓
business metrics
      ↓
evidence readiness
      ↓
identify missing operational truth
```

The real Dining Flow project itself was created around combining diner activity/experience with data from restaurant stakeholders, equipment and surrounding environments to support operational decision-making. ([UTU][8])

So we're not forcing an FDE story onto an unrelated dataset.

---

# 55. Why the project is genuinely unique

The cool part isn't merely:

> “I used a food dataset.”

The project is:

> **“I investigated whether a real smart restaurant's data estate is sufficient to make food-waste decisions.”**

We're combining:

```text
RFID-linked dining data
+
weighing measurements
+
food component data
+
weather API
+
source documentation
+
data-quality validation
+
workflow modeling
+
source-gap analysis
```

and explicitly distinguishing:

```text
OBSERVED
INFERRED
UNKNOWN
```

That is a very strong FDE pattern.

---

# 56. Submission Mapping

| Assignment requirement         | LAST TRAY evidence                                           |
| ------------------------------ | ------------------------------------------------------------ |
| **Source reasoning 20%**       | source map, ownership, grain, authority, source gap register |
| **Retrieval 20%**              | Zenodo CSV + FMI API + raw preservation                      |
| **Validation 20%**             | profiling, schema checks, business rules, join checks        |
| **Workflow + metrics 20%**     | dining-session model + 5 KPIs                                |
| **Pipeline dependability 20%** | runnable pipeline, logs, retries, reruns, failures           |

The course itself emphasizes that an FDE should first determine **what information is required and where its truth lives**, rather than ingesting everything available. 

---

# 57. Repository Deliverables

At final submission:

```text
README.md
PRD.md
TRD.md

source_map.md
data_dictionary.md
metric_definitions.md
validation_rules.md
source_of_truth.md
assumptions_limitations.md
judgement_call.md

source-map.png
workflow.png
data-model.png
pipeline.png

src/
tests/
notebooks/

outputs/
    metrics/
    validation/
    reconciliation/
    evidence/
```

And:

```bash
python -m src.pipeline.run
```

must reproduce the final analytical output.

---

# 58. Three-Minute Demo Story

## 0:00–0:30

> “We were asked to understand whether a real smart restaurant's data could support food-waste decisions.”

## 0:30–1:00

Show:

```text
source map
```

and explain:

> “We found meal-selection and measurement data publicly available, but the actual waste sample is not currently public.”

## 1:00–1:30

Show:

```text
raw → validation → canonical model
```

## 1:30–2:00

Show:

```text
5 metrics
```

## 2:00–2:30

Show:

> **Selected weight ≠ food waste**

## 2:30–3:00

Run:

```bash
python -m src.pipeline.run
```

and finish:

> “Instead of manufacturing the missing waste number, our pipeline tells operations exactly what can be measured today and what source integration is required to close the business question.”

That's a very clean FDE demo.

---

# 59. Final Product Statement

### Product

**LAST TRAY — Flavoria DiningOps Truth**

### Business problem

> Understand whether fragmented dining measurements are trustworthy enough to support food-waste and portioning decisions.

### MVP

> Build a reproducible meal-session data product using real Flavoria meal/weight records and official Finnish weather observations.

### Core KPI

> Median plate load per valid dining session.

### Supporting KPIs

> Session volume, P90 plate load, portion variability, measurement-readiness rate.

### Critical limitation

> Public MVP data does not currently provide a directly retrievable plate-waste dataset, so the pipeline explicitly reports waste measurement as a source gap rather than inventing waste values.

### Key FDE judgement

> **Do not turn a selected-food measurement into an assumed waste measurement.**

### Decision supported

> Determine whether the existing public/available data is sufficient for portioning and dining-flow decisions, and identify the exact missing source/integration required for trustworthy waste reduction measurement.

---

## The dataset/source pack we will actually use

**1. FlavoriaFoodWeight1700 — primary dataset**
~2,000 real meal observations/images, measured meal contents, RFID linkage, open Zenodo record. ([Zenodo][4])
[Download / inspect the FlavoriaFoodWeight1700 dataset](https://zenodo.org/records/5850856?utm_source=chatgpt.com)

**2. Finnish Meteorological Institute — external API**
Official historical weather observations through machine-readable WFS interfaces. ([Finnish Meteorological Institute][5])
[FMI Open Data](https://en.ilmatieteenlaitos.fi/open-data?utm_source=chatgpt.com)

**3. Flavoria official Data Catalog — source/authority documentation**
Documents the actual restaurant data ecosystem and its restrictions. ([Flavoria Data Catalog][3])
[Flavoria Data Catalog](https://flavoriadatacatalog.tt.utu.fi/?utm_source=chatgpt.com)

**4. Flavoria Plate Waste documentation — downstream source-gap evidence**
Documents the real waste workflow, historical coverage and quality limitations, but its public sample is currently not downloadable. ([Flavoria Data Catalog][1])

**5. University of Turku / Dining Flow research — domain validation**
Confirms that the real Flavoria environment combines food-choice, waste, environmental and operational data for decision support. ([University of Turku][9])

---

This is the spec I would now **freeze as our baseline**.

The next move is not to start writing random Python. We should first do the **Source Validation Spike**: retrieve the Zenodo CSV, inspect its exact columns/grain/date range/license, inspect the FMI API response shape, and then freeze the actual `data_dictionary.md`, source map and relational schema against the real files. That keeps the implementation faithful to the FDE principle your Class 4 deck emphasizes: **decide what truth the pipeline must carry before building the pipeline.** 

[1]: https://flavoriadatacatalog.tt.utu.fi/docs/lunch-line/lunch-line-waste/?utm_source=chatgpt.com "Plate Waste Data 🥡 | Flavoria Research Infrastructure - Data Catalog"
[2]: https://sites.utu.fi/foodnutriutu/services-in-utu/sensory-and-consumer-research/flavoria/?utm_source=chatgpt.com "Flavoria® Research Platform | FOODNUTRI | UTU"
[3]: https://flavoriadatacatalog.tt.utu.fi/?utm_source=chatgpt.com "Flavoria Research Infrastructure - Data Catalog"
[4]: https://zenodo.org/records/5850856?utm_source=chatgpt.com "FlavoriaFoodWeight1700: Automated Lunch Line Meal Pictures with Automatic Measurement of Weight and Contents"
[5]: https://en.ilmatieteenlaitos.fi/open-data?utm_source=chatgpt.com "Open data - Finnish Meteorological Institute"
[6]: https://flavoriadatacatalog.tt.utu.fi/docs/lunch-line/lunch-line-wnd/?utm_source=chatgpt.com "Weigh & Dine ⚖️ | Flavoria Research Infrastructure - Data Catalog"
[7]: https://www.aimspress.com/article/doi/10.3934/aci.2025011?utm_source=chatgpt.com "Forecasting daily customer flow in restaurants: a multifactor machine learning approach"
[8]: https://sites.utu.fi/diningflow/?utm_source=chatgpt.com "Dining Flow | Dining Flow"
[9]: https://www.utu.fi/en/news/press-release/dining-flow-project-reduces-food-waste-and-enhances-diners-experience-in-self?utm_source=chatgpt.com "Dining Flow project reduces food waste and enhances diners’ experience in self-service restaurants | University of Turku"
