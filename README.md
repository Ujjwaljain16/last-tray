# LAST TRAY — Flavoria DiningOps Truth

*A dependable measurement-reconstruction pipeline for meal measurement, dining behavior, and food-waste readiness.*

## 1. Problem

In the simulated scenario, a self-service restaurant wants to reduce food waste. Its data sits in separate systems (lunch-line scales, a checkout scale, waste stations, weather) with different owners, grains and access rules, and leadership assumes that because food is weighed, waste is visible.

**Question.** *Can we reconstruct a trustworthy operational view of dining measurements from the available source data, and determine whether that evidence is sufficient to support future food-waste decisions?*

| | |
|---|---|
| **Stakeholders** | operations manager (what is selected at the line), kitchen manager (is the typical load stable), sustainability lead (what data to obtain), data and engineering team (does it reproduce, how fragile is it) |
| **Project KPIs** | M1-M5 below: selected-meal measurement and its readiness. Not a waste KPI: no waste KPI can exist on the accessible data |
| **Decision the output supports** | Use the reconstructed selected-meal evidence to describe portions for the registered-export population, and obtain tray-linked waste evidence before committing to any food-waste measurement or reduction programme |

## 2. Scope and engagement framing

This is an **FDE-style reconstruction of a real dining-operations measurement problem using publicly available Flavoria research data and contextual public data**. It is not an engagement with Flavoria, it uses no proprietary system, it is not affiliated with or endorsed by the University of Turku, the University of Helsinki, Flavoria or the Finnish Meteorological Institute, and the public data does not represent all current dining operations. The scenario is simulated for an educational assignment; the data is real and public (see `NOTICE`).

## 3. Key finding

We can reconstruct a reproducible selected-meal measurement layer: 12,284 observed component weighing events become 1,697 measurement-ready sessions with a median derived selected meal weight of 499 g. But **selected meal weight is not consumption, and consumption is not food waste**. The waste source is documented but not publicly accessible in the required usable form, so waste is a **SOURCE GAP** and no waste figure is produced.

## 4. Source map

| Source | Class | Provides | Authority for this question |
|---|---|---|---|
| FlavoriaFoodWeight1700 (Zenodo, CC BY 4.0) | primary measurement data | one component weighing event per row, 11 CSV files, 2020-10-05 to 2020-11-20 | what the scales recorded; not consumption or waste |
| FMI open data weather API (CC BY 4.0) | weather enrichment | hourly observations, Turku Artukainen | outdoor context only |
| Flavoria Data Catalog | contextual documentation | source definitions and access status | definitions, not data |
| Flavoria Weigh & Dine documentation | source-gap documentation | describes a checkout plate total; no sample | none: no data |
| Flavoria Lunch Line Waste documentation | source-gap documentation | describes per-tray waste; sample reads "TODO, Ask!" | would be authoritative for waste; not accessible |

**What was retrieved, and how.** Two retrieval modes: the Zenodo CSV archive as a file download, and the FMI weather service as an API (XML). Completeness is checked by pinned size, MD5 and SHA-256 and by row counts (12,284 weighing events; 1,129 weather hours); raw files are preserved unmodified.

Full map: [`docs/source_map.md`](docs/source_map.md). Decisions per business fact: [`docs/source_truth_decisions.md`](docs/source_truth_decisions.md). Gap register: [`docs/source_gap_register.md`](docs/source_gap_register.md).

## 5. Evidence model

![Workflow](diagrams/workflow.png)

| Status | What | In this project |
|---|---|---|
| **OBSERVED** | recorded by an instrument | 12,284 component weighing events; FMI weather hours |
| **DERIVED** | computed by us under a stated rule | sessions, `derived_selected_meal_weight_g`, readiness |
| **UNKNOWN** | never measured | how much was consumed |
| **SOURCE GAP** | exists, not accessible | food waste (W1 BLOCKED) |

**What was modelled.** Three levels: the weighing event, the derived session (one per `(session_id, population)`), and the session component, with weather and daily volume as context and a validation-issue audit table (data model: [`diagrams/data-model.png`](diagrams/data-model.png); field definitions: [`docs/data_dictionary.md`](docs/data_dictionary.md)). `session_id` alone is not enough: two IDs occur in both exports.

## 6. Final evidence

Population for M1-M4: core-ready registered-export sessions (1,697). Population for M5 and S2: eligible registered-export sessions (1,699). Values come from `outputs/metrics/metrics.csv`.

| Metric | Value | What it tells us | What it does NOT tell us |
|---|---|---|---|
| M1 — Median Derived Selected Meal Weight | 499 g | the typical derived selected meal weight | intake; it is not consumption |
| M2 — P90 Derived Selected Meal Weight | 1,039.6 g | the upper end of the distribution | anything eaten; the most period-sensitive metric |
| M3 — Observed Valid Sessions — Registered-Export Population | 1,697 | how many registered-export sessions were observed and are valid | restaurant volume or how many people came |
| M4 — Median Distinct Normalized Components per Session | 5 | how many named components a typical session selected | dish identity across days or exports |
| M5 — Core Measurement Readiness | 99.88% (1,697 / 1,699) | the share of eligible sessions meeting the approved readiness criteria | that the data is error-free |
| S2 — Warn-Free Rate (supporting) | 97.88% | sessions with no session-level warning | a data-quality score |
| W1 — Direct Food Waste Measurement | BLOCKED / SOURCE GAP | that no waste figure can be produced | nothing about waste: no estimate, band or proxy |

![M1 and M2](diagrams/weight-distribution.png)

Details: [`docs/final_evidence.md`](docs/final_evidence.md).

## 7. What we can conclude

- A selected-meal weight distribution can be reconstructed reproducibly from the component weighing events.
- For the registered-export population, half of the measurement-ready sessions have a derived selected meal weight of 499 g or less and one in ten exceed 1,039.6 g.
- 99.88% of eligible registered-export sessions meet the approved readiness criteria, and every number traces to a checksummed raw file.
- Weather context joins to all 1,697 measurement-ready sessions.

## 8. What we cannot conclude

- How much was **consumed**, left over, or wasted. No source measures consumption; the waste source is not accessible.
- Any waste reduction, saving or impact.
- That a session is a person, or that M3 measures how many people came.
- Anything about other periods, other capture systems, or the non-registered population (diagnostic only, never pooled).
- Any causal effect of weather: it is context.

## 9. Data quality

Profiling found schema drift (7 of 11 files lack a column), non-chronological row order, one export whose timestamps are three hours off, two session IDs present in both exports, and component names that disagree across exports in 2020-10-05..16. Rules and treatments: [`docs/validation_rules.md`](docs/validation_rules.md). The two crossover sessions are **quarantined and listed, never deleted** (`outputs/validation/quarantine_manifest.csv`). The two export labels ("registered-export", "non-registered-export") come from file names only; their meaning is undefined by the source.

## 10. Sensitivity

26 scenarios tested against a frozen baseline ([`docs/sensitivity_analysis.md`](docs/sensitivity_analysis.md), `outputs/evidence/evidence_matrix.csv`). **Stable:** the median (493-505 g), the component count, the crossover sessions, the largest event. **Sensitive:** the upper end (M2 977-1,066 g), the study period, the irregular-volume days. **Conditional:** valid-session count and readiness, which depend on the timezone reading of one file (+3h is the strongest-supported reading, not source-confirmed; +2h, +3h and +4h agree). **Blocked:** consumption and waste.

## 11. Pipeline

```
python -m src.pipeline.run --stages all      # same as: python -m src.pipeline.run
```

Six gated stages (ingest, stage, validate, model, metrics, sensitivity) run in about ten seconds and exit 0 on success. The run is **offline**: it never downloads. A missing raw source fails with exit 4 and names the explicit retrieval command, `python -m src.pipeline.fetch --source <flavoria|weather>`. A failed stage blocks every later stage and removes its stale outputs; exit codes name the failed layer (4 source, 6 weather only, 7 validation, 8 model, 9 metrics, 10 sensitivity, 11 orchestration). Stages, gates, outputs and resume: [`docs/pipeline.md`](docs/pipeline.md).

Setup (Python 3.11; run every command from the repository root):

```
python -m venv .venv
.venv\Scripts\activate                 # Windows;  Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
python -m src.pipeline.run
python -m pytest
```

Diagrams: [source map](diagrams/source-map.png), [pipeline](diagrams/pipeline.png), [workflow](diagrams/workflow.png), [data model](diagrams/data-model.png).

## 12. Reproducibility

- Raw files are pinned by size, MD5 and SHA-256 and re-verified on every read; they are committed byte-exact (about 4 MB, CC BY 4.0) so a fresh clone runs offline.
- Outputs are deterministic: two real runs, different hash seeds and directories give byte-identical files. `outputs/pipeline/` records the run manifest, stage summary and 11 pipeline controls.
- A clean clone reproduced every output and passed the full test suite.

## 13. Repository structure

```
README.md            this file
config/              approved decisions: sources and pins, thresholds, timezone override, populations
data/raw/            preserved raw inputs (unmodified)
src/                 ingest, stage, validate, model, metrics, sensitivity, pipeline (orchestration)
tests/               unit, real-data, failure-injection and documentation tests
outputs/             generated evidence (ingestion, staging, validation, model, metrics, evidence, pipeline)
docs/                assignment artifacts and decision log (start with the list below)
diagrams/            source map, workflow, data model, pipeline, distribution (PNG, SVG, build script)
research/            the exploration scripts that produced the reference values
notebooks/           01 source exploration; 02 read-only pipeline walkthrough for evaluators (displays committed outputs only)
```

Start here: [`docs/assignment_traceability.md`](docs/assignment_traceability.md) (rubric to artifact), [`docs/source_map.md`](docs/source_map.md), [`docs/source_truth_decisions.md`](docs/source_truth_decisions.md), [`docs/final_evidence.md`](docs/final_evidence.md), [`docs/known_unknowns_assumptions_limitations.md`](docs/known_unknowns_assumptions_limitations.md), [`docs/judgement_call.md`](docs/judgement_call.md), [`docs/demo_script.md`](docs/demo_script.md), [`docs/pipeline.md`](docs/pipeline.md), [`docs/data_provenance.md`](docs/data_provenance.md), [`docs/data_dictionary.md`](docs/data_dictionary.md), [`docs/sensitivity_analysis.md`](docs/sensitivity_analysis.md), [`docs/decision_log.md`](docs/decision_log.md). Background: `docs/PRD.md` and `docs/TRD.md` (original requirements and design), `docs/implementation_overview.md` (how it is built), and `docs/profile_report.md`, `docs/validation_findings.md`, `docs/spec_changes.md` and `research/exploration/` (the exploratory profiling that informed the design: historical evidence, not the pipeline).

## 14. Known / Unknown / Assumptions / Limitations

| | Summary |
|---|---|
| **Known** | event-level weight exists; sessions can be reconstructed; weather aligns for every measurement-ready session; two crossover sessions exist; a selected meal weight can be derived |
| **Unknown** | actual consumption; leftovers; actual food waste; whether the public research capture reflects all operational behaviour |
| **Assumptions** | a file-specific +3h reading for one export; population labels taken from file names; session reconstruction rules; diagnostic thresholds |
| **Limitations** | public waste detail unavailable; component names vary across exports; five study weeks in 2020; a research dataset, not a live feed; the non-registered population has different capture characteristics |

Each assumption with its evidence and sensitivity result: [`docs/known_unknowns_assumptions_limitations.md`](docs/known_unknowns_assumptions_limitations.md).

## 15. FDE judgement

The evidence supports **measurement reconstruction and readiness assessment**, not a food-waste decision. Selected weight can be measured reproducibly; consumption is unknown and waste is blocked. So the next requirement is **tray-linked waste evidence, not a waste proxy**: accessible waste-point records with a tray identifier, time and weight. With them, selection and return could be compared as observations. Full reasoning: [`docs/judgement_call.md`](docs/judgement_call.md).

## 16. Demo

A 3-5 minute script: [`docs/demo_script.md`](docs/demo_script.md).

## Licence and attribution

- **This project's own code and documentation** are released under the [MIT Licence](LICENSE).
- **The MIT Licence does not cover third-party data.** FlavoriaFoodWeight1700 (Zenodo, DOI 10.5281/zenodo.5850856) and the FMI weather observations remain under CC BY 4.0 and are attributed in [`NOTICE`](NOTICE) and [`docs/data_provenance.md`](docs/data_provenance.md). The raw files under `data/raw/` are redistributed unmodified.
- This project is not affiliated with or endorsed by the data providers.
