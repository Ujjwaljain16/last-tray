# Implementation Overview

How the project is built: the components, what each guarantees, how it is tested, and where judgement lives. For behaviour and gates see `pipeline.md`; for reasoning behind choices see `decision_log.md`.

## Principles

1. Reproduce the reference values (`canonical_schema.md` section 4) first, then harden.
2. Judgement lives in `config/`, not in code paths: timezone override, population labels, thresholds, each with a rationale. The loader refuses configuration that would change an approved decision.
3. Every profiling finding becomes a test before the code that handles it.
4. The core lane (Flavoria measurements) and the context lane (weather) stay independent: a weather problem blocks weather outputs only.
5. Every stage verifies its upstream checksums, headers and row counts before it runs; nothing is trusted because a file exists.
6. Dependencies stay small: `pandas`, `requests`, `tzdata`, `PyYAML`, `matplotlib`, `pytest`.

## Layout

```text
config/        sources.yml  thresholds.yml  timezone_overrides.yml  populations.yml
data/raw/      flavoria/dataset_csv.tar   weather/*.xml        (immutable, committed, about 4.7 MB)
src/
  ingest/      discover, hash and verify raw files, schema fingerprints, timezone-override scope, snapshot identity, staging handoff; explicit retrieval client
  stage/       header-based parsing, per-column timestamp formats, timezone normalisation, component normalisation
  validate/    rule engine, reconciliation identities, quarantine manifest
  model/       canonical tables, session reconstruction, weather join, controls
  metrics/     metric contracts, populations, computation, controls
  sensitivity/ scenario registry, generic engine, robustness classification, evidence tables, figures
  pipeline/    stage registry, orchestrator, run manifest and controls, exit codes, CLI, explicit fetch command
tests/         unit, real-data, failure-injection and documentation tests
outputs/       ingestion  staging  validation  model  metrics  evidence  pipeline  (generated), exploration (research outputs)
research/      exploratory profiling scripts that produced the reference values (historical evidence, not the pipeline)
```

## Components

| Component | Output directory | Guarantees |
|---|---|---|
| Ingestion | `outputs/ingestion/` | every pinned raw file matches size, MD5, SHA-256 and row count; raw files are unchanged after the run; the handoff to staging names exactly what may be read |
| Staging | `outputs/staging/` | raw bytes are read only through the verified reader; 12,284 events and 4,516 weather observations staged; failed lanes remove their stale tables |
| Validation | `outputs/validation/` | findings carry stable rule ids and row lineage; quarantine is a flag plus a manifest and deletes nothing; reconciliation identities must hold |
| Canonical model | `outputs/model/` | independent reconstruction of the selected meal weight is compared with the validation value; nothing is published if a control fails |
| Metrics | `outputs/metrics/` | metrics name their population and grain; each is checked against its approved value and against an independent recomputation; W1 stays BLOCKED |
| Sensitivity | `outputs/evidence/` | the baseline is frozen; every reference scenario reproduces or the stage fails; no scenario yields a waste or consumption estimate |
| Pipeline | `outputs/pipeline/` | gated order, first-failure exit codes, stale-output removal, atomic writes, run manifest with provenance |

## Tests

| Area | What is protected |
|---|---|
| Schema drift, row order, timestamp formats | all files ingest; parsed time, not row order, decides sequence |
| Timezone | the file-specific override is applied only where approved; an unregistered shift is flagged, not silently converted |
| Duplicates and crossover sessions | exact duplicates leave the sums but stay in the event table; crossover sessions are quarantined in both populations |
| Sessions and components | one tray per session; additive repeats; components counted within a session only, no alias table |
| Weather join | hour-ending rule; a missing weather hour never changes core readiness |
| Denominator rule | M5 and the warn-free rate use 1,699 regardless of removals |
| Waste | W1 is BLOCKED with the required source; no waste or consumption column exists |
| Thresholds | boundary values at each approved threshold |
| Metrics and sensitivity | hand-built fixtures for the statistics; the sensitivity baseline equals the metric package; timezone offsets +2h to +4h equal the baseline |
| Reference values | every reference figure in the golden files is reproduced from raw data |
| Pipeline | order, gates, failure propagation, stale-output removal, resume, idempotence, offline behaviour, atomic writes, determinism across hash seeds and directories |
| Documentation | published numbers equal the generated artifacts; forbidden claims are absent; referenced paths exist |

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Exploration numbers drift from pipeline numbers | the golden-value tests fail loudly; differences are investigated, not tolerated |
| The weather API changes or is down | raw XML is committed and pinned; normal runs are offline |
| Zenodo is unavailable | the committed `dataset_csv.tar` is checksum-verified |
| Over-engineering | one package per stage, no containers, no framework beyond a small orchestrator |
| Definition drift between docs and code | documentation is the specification; a mismatch is a defect and is covered by tests |
