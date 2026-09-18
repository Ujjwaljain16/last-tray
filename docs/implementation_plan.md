# Implementation Plan (proposed, awaiting review)

Nothing below has been built. The Phase 2 research scripts in `research/phase2/` are historical evidence and are **not** the pipeline; production code will be written fresh under `src/`, with the exploration numbers used as regression anchors.

## Principles

1. Build the **smallest thing that reproduces the golden values** (`canonical_schema.md` section 4), then harden it.
2. Judgement lives in `config/`, not in code paths: timezone overrides, population labels, thresholds, each with a rationale.
3. Every Phase 2 finding becomes a test before the code that handles it.
4. Core lane and context lane stay independent from the first commit.
5. No new dependencies beyond the approved stack (`pandas`, `requests`, `tzdata`, `PyYAML`, `matplotlib`, `pytest`).

## Final layout

```text
config/    timezone_overrides.yml   populations.yml   thresholds.yml   sources.yml
data/raw/  flavoria/dataset_csv.tar   weather/*.xml   (immutable, committed, ~4 MB)
src/
  ingest/    flavoria.py  weather.py  manifest.py
  stage/     parse_events.py          (header-based, per-column formats, tz, sort by time)
  validate/  rules.py  engine.py  report.py
  model/     build.py  schema.sql     (DDL from canonical_schema.md)
  metrics/   kpis.py  sensitivity.py  evidence.py
  pipeline/  run.py  statuses.py  gates.py  log.py
tests/       one file per invariant group (see below)
outputs/     validation/  reconciliation/  metrics/  evidence/  run_manifest.json
```

## Work packages (in dependency order)

| WP | Deliverable | Depends on | Size | Done when |
|---|---|---|---|---|
| **1** Scaffold | `requirements.txt`, `config/*.yml`, package skeleton, `pytest` runs green on an empty suite, `.gitignore` | none | S | `python -m src.pipeline.run --help` works |
| **2** Ingest | offline ingestion: discovery, snapshot identity, checksum verification, schema fingerprint, T10 scope, raw preservation check, manifest, staging handoff; separate explicit `fetch` command with bounded retry | 1 | M | manifest lists archive, 11 CSVs and 7 weather files with SHA-256, size, rows; corrupt archive and HTTP 429/500/timeout paths tested |
| **3** Stage | header-based parser, per-column timestamp formats, timezone override, `component_id_normalized`, exact-duplicate marking, sort by parsed time | 2 | M | 12,284 events; row-order and mixed-format tests pass |
| **4** Validate | rule engine for S/B/T/I/X/C rules, `fact_validation_issue`, `validation_issues.csv`, `validation_summary_by_rule.csv`, `profile_summary.csv` | 3 | L | issue counts by rule and population equal the Phase 2 golden table |
| **5** Model | SQLite build (drop and recreate in one transaction), sessions, session components, weather, daily volume, flags | 3, 4 | M | invariants I-1 to I-10 hold |
| **6** Metrics | M1-M5, S1-S4, W1 `BLOCKED`, `final_evidence.csv`, `kpi_summary.csv`, `measurement_readiness.csv`, `population_diagnostics.csv` | 5 | M | baseline values reproduced exactly |
| **7** Sensitivity | the 25 scenarios, baseline row equals headline KPIs | 6 | M | `sensitivity_analysis.csv` matches the exploration file |
| **8** Orchestration | `python -m src.pipeline.run`, stage statuses `RECOVERED/WARNING/FAILED/BLOCKED`, core and context gates, `run_manifest.json`, per-run log | 2-7 | M | two runs give identical hashes; weather outage blocks only weather outputs |
| **9** Docs and visuals | README, notebooks refreshed from real pipeline outputs, diagrams checked against the code, demo script and checklist | 8 | M | README matches implementation |
| **10** Self-audit | ruthless evaluator-style review against the five grading areas | 9 | S | `final_self_audit.md` written, gaps listed honestly |

## Tests (each finding becomes a regression test)

| Finding | Test |
|---|---|
| Schema drift (7 of 11 files lack `weighting_type`) | `test_schema_drift.py`: all files ingest; column absent becomes NULL |
| Row order not chronological; one file newest-first | `test_row_order.py`: shuffled and reversed input give identical sessions |
| Mixed timestamp formats across columns | `test_timestamp_formats.py` |
| Timezone: +3h override, T07 detects an unregistered shift | `test_timezone.py`: file without override is flagged, not silently converted |
| Duplicates | `test_duplicates.py`: 2 exact rows excluded from sums, still present in `fact_weighing_event` |
| Crossover sessions | `test_identity.py`: quarantined in both versions, `core_ready = 0`, M-values exclude them |
| Session derivation | `test_sessions.py`: I-10; additive repeats; one tray per session |
| Component counting | `test_components.py`: M4 within-session; no alias collapse; `component_weighing_event_count` retained |
| Weather join | `test_weather_join.py`: ceil rule; `r_1h` maps to the hour containing the meal; DST round trip; unmatched session stays valid |
| Core vs context | `test_separation.py`: weather NULL or outage never changes `core_ready`, M1-M5 |
| Volume flags | `test_volume_flags.py`: six irregular days flagged, appear in no metric filter (I-6) |
| Denominator rule | `test_readiness.py`: M5 and warn-free use 1,699 regardless of removals (I-7); canonical warn-free counts session-level WARNs (97.88%), the event-level variant (97.70%) is a reconciled diagnostic |
| Waste | `test_waste_blocked.py`: W1 is `BLOCKED` with the required source; no waste or consumption column exists (I-5) |
| Thresholds | `test_thresholds.py`: boundary values (1,499/1,500 g; 49/50 g; 2,200/2,201 g; 600/601 s; span and hour edges) |
| Metrics | `test_metrics.py`: median, P90 on hand-built fixtures; NULL never becomes 0 |
| Sensitivity | `test_sensitivity.py`: baseline row equals headline KPIs; TZ2-TZ4 equal baseline |
| Idempotency | `test_pipeline_idempotency.py`: run twice, identical row counts and SHA-256 of every output CSV |
| Failures | `test_failure_modes.py`: empty input, corrupt archive, malformed XML, missing column, weather 429/500/timeout |
| Golden values | `test_golden_values.py`: every figure in `canonical_schema.md` section 4 |

## Configuration contents

- `timezone_overrides.yml`: `registered_2020_10_05-2020_10_18.csv: {assume: UTC, target: Europe/Helsinki, status: NORMALISED_PLUS_3H_STRONGEST_SUPPORT, rationale: ...}`.
- `populations.yml`: filename prefix to label; a note that meaning is undefined by the source.
- `thresholds.yml`: the approved values with a one-line rationale each and the "diagnostic, not physical" statement.
- `sources.yml`: URLs, expected checksums, FMISID, parameters, request chunking.

## Risks

| Risk | Mitigation |
|---|---|
| Exploration numbers drift from pipeline numbers | golden-value test fails loudly; differences are investigated, not tolerated |
| Weather API changes or is down at review time | raw XML committed and pinned; normal runs are offline |
| Zenodo unavailable | committed `dataset_csv.tar` with checksum check |
| Over-engineering | no orchestrator, no containers, no abstractions beyond one module per stage |
| Definition drift between docs and code | docs are the spec; a doc/code mismatch is a defect |

## Review checkpoints

1. After WP4: validation counts equal the Phase 2 golden table.
2. After WP7: baseline KPIs and sensitivity file equal the exploration results.
3. After WP8: idempotency and failure-mode demonstration.
4. After WP10: final self-audit.

## Decisions resolved on review (2026-09-19)

1. Canonical schema and this plan: approved.
2. Warn-free rate: canonical **97.88%** (session-level), with the event-level 97.70% reconciled as a diagnostic (D28).
3. Phase 2 scripts: kept, moved to `research/phase2/` with a README (D32).

## Work package status

| WP | Status |
|---|---|
| 1 Scaffold | **done** (see checkpoint report): config, typed loader, vocabulary, CLI, golden values, 73 tests |
| 2 Ingest | **done** (see WP2 checkpoint report) |
| 3 Stage | **done** (see WP3 checkpoint report) |
| 4 Validate | **done** (see WP4 checkpoint report) |
| 5 Model | **done** (see WP5 checkpoint report) |
| 6-10 | not started |
