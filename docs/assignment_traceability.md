# Assignment Traceability

The assignment grades five areas at 20% each. This page maps each to concrete artifacts in the repository and says how to show it in three to five minutes. Every path below exists; a test checks that.

Project track: **C, own problem** (a research dining operation with lunch-line scales, waste stations and weather, reconstructed from public data).

The submission package also asks for a README, a source map and workflow/data-model diagram, runnable code, a final evidence table with a Known / Unknown / Assumption / Limitation section, and a demo. Those are listed at the end.

## 1. Source reasoning

| | |
|---|---|
| **Assignment expectation** | Map business questions to required information to source systems. Identify ownership, grain and important gaps. |
| **Repository evidence** | The business question is frozen before any data is used. Each source has an owner, authority, grain, licence and known gaps, and every business fact has a stated source of truth with the rejected alternative. The decisive gap (waste) is registered rather than hidden. |
| **Key artifacts** | `docs/source_map.md`, `docs/source_truth_decisions.md`, `diagrams/source-map.png`, `outputs/source_inventory.csv` |
| **Show in 3-5 minutes** | Open `docs/source_map.md` section 2 and read the five sources by class (primary measurement, weather enrichment, documentation, source-gap documentation). Then open the waste row of `docs/source_truth_decisions.md`: documented, not publicly accessible in the required usable form, therefore W1 BLOCKED / SOURCE GAP. |

## 2. Retrieval

| | |
|---|---|
| **Assignment expectation** | At least two retrieval modes; show how you know retrieval is complete; preserve raw inputs. |
| **Repository evidence** | Two modes: a file archive over HTTP (Zenodo CSV archive) and a REST-style API (FMI web feature service, XML). Every raw file is pinned by size, MD5 and SHA-256 with expected row counts; completeness is proven by row counts (12,284 events; 1,129 weather hours) and by checksum verification on every read. Raw files are preserved byte-for-byte and never modified. Normal runs are offline; retrieval is an explicit command that never overwrites a raw file or edits a pin. |
| **Key artifacts** | `src/pipeline/fetch.py`, `config/sources.yml`, `data/raw/`, `outputs/ingestion/raw_artifact_manifest.csv`, `outputs/ingestion/source_snapshot.csv`, `outputs/ingestion/weather_inventory.csv`, `outputs/ingestion/schema_fingerprints.csv`, `docs/data_provenance.md`, `tests/test_ingest_verify.py`, `tests/test_fetch.py`, `tests/test_raw_inputs_pinned.py` |
| **Show in 3-5 minutes** | `python -m src.pipeline.run --stages ingest`, then open `outputs/ingestion/raw_artifact_manifest.csv` (status VERIFIED, checksums, row counts). Point to `python -m src.pipeline.fetch --help` as the only network command. |

## 3. Profiling and validation

| | |
|---|---|
| **Assignment expectation** | Profile the data, identify meaningful quality issues, define business-oriented validation rules, record assumptions and limitations instead of silently fixing them. |
| **Repository evidence** | Profiling found schema drift (7 of 11 files lack a column), non-chronological row order, one file three hours off, two sessions present in both exports, and names that disagree across exports. Rules are defined with severities and treatments; quarantined records are listed, never deleted; reconciliation identities must hold or the stage fails. |
| **Key artifacts** | `research/exploration/` (with its own README), `docs/validation_rules.md`, `outputs/validation/validation_issues.csv`, `outputs/validation/validation_summary_by_rule.csv`, `outputs/validation/quarantine_manifest.csv`, `outputs/validation/reconciliation_summary.csv`, `docs/known_unknowns_assumptions_limitations.md`, `tests/test_validate_real.py` |
| **Show in 3-5 minutes** | Open `outputs/validation/quarantine_manifest.csv` (the two crossover sessions, kept and listed), then `docs/source_truth_decisions.md` for the one assumption that could not be confirmed, and its sensitivity in `outputs/evidence/uncertainty_register.csv`. |

## 4. Workflow and metrics

| | |
|---|---|
| **Assignment expectation** | Represent entities, events and outcomes; build a relational or event model; calculate 3-5 metrics linked to the project KPI. |
| **Repository evidence** | A three-level model (weighing event, derived session, session component) with weather and daily volume as context, and a validation-issue audit table. Five headline metrics (M1-M5), one supporting metric (S2), and W1 declared BLOCKED. Metrics name their population and grain, and are checked against an independent recomputation. A sensitivity analysis says which conclusions are stable, sensitive, conditional or blocked. The public data records no interventions, and the outcome that matters (food waste) is the documented source gap, so the model stops at measurement and states that limit. |
| **Key artifacts** | `docs/data_dictionary.md`, `diagrams/workflow.png`, `diagrams/data-model.png`, `outputs/model/model_manifest.json`, `outputs/model/model_control_summary.csv`, `docs/metric_contract.md`, `outputs/metrics/metrics.csv`, `outputs/metrics/metric_evidence.csv`, `docs/final_evidence.md`, `docs/sensitivity_analysis.md`, `outputs/evidence/evidence_matrix.csv`, `docs/judgement_call.md`, `tests/test_model_real.py`, `tests/test_metrics_real.py`, `tests/test_sensitivity_real.py` |
| **Show in 3-5 minutes** | Show `docs/final_evidence.md` (M1-M5, S2, W1), then `diagrams/weight-distribution.png`, then `outputs/evidence/evidence_matrix.csv` for what is STABLE, SENSITIVE, CONDITIONAL and BLOCKED. |

## 5. Dependable pipeline

| | |
|---|---|
| **Assignment expectation** | A repeatable pipeline: ingest, validate, transform/model, metric output, with logging and checks, rerun behaviour and failure handling. |
| **Repository evidence** | One command runs six gated stages offline. A failed stage blocks later ones and removes stale outputs; exit codes name the failed layer. Each stage re-verifies its upstream checksums; outputs are written atomically; two real runs are byte-identical, also across hash seeds and directories; a clean clone reproduced every output and passed the full test suite. Failure injection covers tampered and missing raw files, tampered staging, validation and canonical tables, a changed metric reference, an invalid registry, and a missing weather lane. |
| **Key artifacts** | `docs/pipeline.md`, `src/pipeline/run.py`, `outputs/pipeline/stage_summary.csv`, `outputs/pipeline/pipeline_controls.csv`, `tests/test_pipeline_real.py`, `tests/test_pipeline_orchestrator.py`, `docs/decision_log.md` (D64-D68) |
| **Show in 3-5 minutes** | Run `python -m src.pipeline.run` (about ten seconds), open `outputs/pipeline/pipeline_controls.csv`, then, in a scratch output directory (`--out`), edit one canonical file, run `python -m src.pipeline.run --out <dir> --resume-from metrics` and show exit code 8 with later stages blocked (script in `docs/demo_script.md`). |

## Submission package checklist

| Requirement | Artifact |
|---|---|
| README: problem, stakeholders, KPI, sources, setup and run, decision supported | `README.md` |
| Source map | `docs/source_map.md`, `diagrams/source-map.png` |
| Workflow and data model diagrams | `diagrams/workflow.png`, `diagrams/data-model.png` (editable source: `diagrams/build_diagrams.py`; vector copies as `.svg`) |
| Code showing retrieval, validation, modelling, metrics and a runnable pipeline that reproduces the output from raw inputs | `src/`, `python -m src.pipeline.run` |
| Final evidence table (3-5 metrics) | `docs/final_evidence.md`, `README.md` |
| Known / Unknown / Assumption / Limitation | `docs/known_unknowns_assumptions_limitations.md` |
| 3-5 minute demo and the one FDE judgement | `docs/demo_script.md`, `docs/judgement_call.md` |
