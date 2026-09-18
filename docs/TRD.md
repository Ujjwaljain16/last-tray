# LAST TRAY: Technical Requirements (v2, source-verified)

Companion to `docs/PRD.md`. Status: **specification frozen for review; no production code exists yet.**

## 1. Design principles

1. Simplest architecture that proves the assignment: Python + pandas + SQLite + pytest. No orchestrator, no containers, no cloud.
2. **Raw is immutable.** Nothing writes to `data/raw/`.
3. **Nothing is silently dropped.** Every excluded row has a reason in `validation_issues.csv`.
4. **Judgement lives in config, not in code paths**: timezone overrides, population labels, plausibility thresholds are declared in `config/*.yml`, each with a rationale.
5. **Core and context are independent.** A weather failure never blocks core metrics.
6. Deterministic: sorted keys, fixed seeds where relevant, no wall-clock values inside metric outputs (timestamps only in the manifest).

## 2. Stack (corrected)

Python **3.11+** (3.11.9 installed here; the earlier draft said 3.12), pandas 2.x, requests, `zoneinfo` + `tzdata`, SQLite (stdlib), PyYAML, matplotlib (diagrams and charts), pytest. PyArrow optional. DuckDB not used.

## 3. Sources and retrieval

| Source | Mode | Detail |
|---|---|---|
| Flavoria CSV archive | **File download** (HTTP GET, Zenodo API) | `dataset_csv.tar`, 1,277,440 bytes, MD5 `74410f922287ceffbd8092d7dd4e5530`, checked against Zenodo's record. |
| FMI weather | **API** (WFS 2.0.0, XML) | Stored query `fmi::observations::weather::simple`, `fmisid=100949`, `timestep=60`, parameters `t2m,ws_10min,r_1h,ri_10min`. Max 168 h per request, so the window is chunked in 7-day requests. No API key. Server limits 20,000/day, 600 per 5 min. |
| Flavoria catalogue pages | Reference only | Fetched as evidence, stored in `docs/`, not a pipeline input. |

Completeness evidence (assignment class 5): Flavoria = archive checksum equals Zenodo's, 11 of 11 members extracted, per-file row counts recorded, every weekday of the window present. FMI = expected hourly count (1,129) equals received, no gaps, no duplicate (time, parameter). Failures of these checks are logged, not swallowed.

## 4. Repository structure (trimmed from the draft)

```text
config/            timezone_overrides.yml, populations.yml, thresholds.yml
data/raw/          flavoria/dataset_csv.tar, weather/*.xml  (immutable, git-tracked, small)
data/staging/      parsed, typed, still un-filtered
data/model/        last_tray.db (SQLite), parquet copies (optional)
src/ingest/        flavoria.py, weather.py
src/profile/       profiler.py
src/validate/      rules.py, report.py
src/transform/     events.py, sessions.py, weather.py
src/model/         build_model.py
src/metrics/       kpis.py
src/pipeline/      run.py, manifest.py, statuses.py
outputs/           source_inventory.csv, validation/, reconciliation/, metrics/, evidence/, run_manifest.json
tests/             see section 12
logs/              one log per run
docs/  diagrams/  notebooks/   (notebooks/01_source_exploration.ipynb is a deliverable built from real outputs)
research/phase2/   historical Phase 2 investigation scripts + README (never imported by src/)
tests/golden/      golden_values.yml + frozen Phase 2 fixtures (regression authority)
```

## 5. Data layers

`raw` (bytes on disk, never edited) → `staging` (parsed and typed, every row kept, raw strings kept) → `model` (SQLite tables below) → `outputs` (metrics and evidence).

## 6. Data model

Corrected from the draft: the atomic table is the **weighing event**. Sessions are **derived**.

| Table | **Grain: one row = ...** | Key | Type |
|---|---|---|---|
| `fact_weighing_event` | one component weighing event, as recorded in one source file row | `event_id` (file + row number) | OBSERVED |
| `fact_dining_session` | one **derived** dining session: all weighing events sharing a `session_id`, within one population | (`session_id`, `population`) | DERIVED |
| `fact_session_component` | one distinct normalised component within one dining session | (`session_id`, `population`, `component_id_normalized`) | DERIVED |
| `fact_weather` | one FMI parameter row set for one station at one UTC hour (one column per parameter) | (`fmisid`, `obs_time_utc`) | OBSERVED (external) |
| `dim_scale` | one physical lunch-line scale | `scale_id` | reference |
| `dim_component_name` | one distinct raw component string and its normalised form | `component_name_raw` | reference, DERIVED mapping |
| `fact_daily_volume` | one service date within one population, with the volume flags | (`service_date`, `population`) | DERIVED |
| `dim_date` | one calendar date in the window | `date` | reference |
| `fact_validation_issue` | one rule violation on one record | `issue_id` | audit |
| `raw_file_manifest` | one raw file in one run | (`run_id`, `filename`) | audit |
| `pipeline_run` | one pipeline execution | `run_id` | audit |

Relationships: `fact_weighing_event.(session_id, population) → fact_dining_session`; `fact_session_component.(session_id, population) → fact_dining_session`; `fact_dining_session` joins `fact_weather` via `weather_hour_utc` (a join, not a foreign key: it may be NULL); `fact_weighing_event.scale_id → dim_scale`.

Idempotency: tables are **rebuilt** per run from raw inputs (`DROP` + `CREATE` inside one transaction), keyed by content, never appended. `pipeline_run` is the only table that grows; it is excluded from output comparisons.

### 6.1 `fact_weighing_event` columns
`event_id, source_file, source_row_number, population, session_id, tray_id, scale_id, station_family, component_name_raw, component_id_normalized, component_weight_g, source_time_raw, event_time_local, timezone_handling, identification_time_local, weighing_type, is_exact_duplicate, quality_status`

`component_weight_g` is the source's `weight_of_a_component`, unchanged. `population` takes `registered_export` or `non_registered_export`.

### 6.2 `fact_dining_session` columns
`session_id, population, is_primary_population, tray_id, service_date, first_weighing_at, last_weighing_at, identification_time_local, derived_selected_meal_weight_g, component_weighing_event_count, distinct_component_count, distinct_component_count_status, session_span_s, session_duration_minutes, identity_conflict, core_ready, quality_status, weather_hour_utc, weather_matched`

`component_weighing_event_count` is a diagnostic; `distinct_component_count` (distinct `component_id_normalized` within the session) feeds M4. `distinct_component_count_status` is `READY_WITH_LIMITATION`, or `LIMITED` for sessions on days where cross-export component identity is unstable (I07).

`derived_selected_meal_weight_g` = `SUM(component_weight_g)` over the session's events **after** exact-duplicate marking, NULL if any event weight is invalid. It is never called "total weight".

`quality_status`: `VALID | WARN | INVALID` per record. `core_ready` is derived **only** from core rules (section 8). Weather never enters it. `weather_matched` is a separate boolean.

### 6.3 `fact_daily_volume`
`service_date, population, sessions, events, low_observed_volume_day, volume_irregularity, expected_regime, observed_regime`. Flags only; **no day is excluded from any metric**.

### 6.4 `fact_weather`
`fmisid, obs_time_utc, t2m_c, ws_10min_ms, r_1h_mm, ri_10min_mmh, source_file, is_null_any`. Missing values stay NULL.

### 7.0 Staging contract (WP3)

Staging consumes only the ingestion handoff and reads raw bytes **only through the `VerifiedReader`**, which re-checks the SHA-256
recorded at ingestion on every read. No downstream stage opens `data/raw`, and a failed verification stops that source's staging path
(no partial table, and any stale one is deleted). Core (Flavoria) failure fails the run; weather failure blocks weather outputs only.
Timestamps keep `*_raw`, `*_canonical_utc` and `timezone_handling`; the file-specific +3h is applied only when the configuration and the
handoff both name that exact file. See `data_dictionary.md` section 10.

## 7. Transformation rules (exact)

1. **Parse** by header **name** (never position), with the dash or dot format decided **per column per file** (one file has dotted identification times and dashed weighing times); retain `event_time_raw`. **Sort events by parsed time; never rely on row order** (files are out of order; one lists each session newest-first).
2. **Timezone**: naive wall time interpreted as `Europe/Helsinki`, unless `config/timezone_overrides.yml` names the file (currently: `registered_2020_10_05-2020_10_18.csv: UTC`). Record `timezone_handling`. The +3h normalisation is the strongest-supported decision from cross-export evidence; the source does not confirm the timezone. Detail in `docs/timezone_decision.md`.
3. **Population** = `registered_export` or `non_registered_export` from the file name prefix (config-driven). These labels are inherited from filenames and are not interpreted as customer-registration status. Never pooled.
4. **Exact duplicates** (all source columns equal within one file): mark `is_exact_duplicate`, keep the first, exclude the rest from sums, log as `I02`.
5. **Identity conflict**: any `session_id` present in both populations gets `identity_conflict = true` and is excluded from primary metrics (`I01`).
6. **Component normalisation**: trim, collapse whitespace, case-fold. The result is `component_id_normalized`; the raw string is retained. **No alias table**: names are not collapsed beyond string normalisation because no defensible mapping exists (Phase 2: differences across exports mix language variants with real dish differences). Distinct components are counted **within one session**.
7. **Session build**: group events by `session_id` within population; compute counts, sums, first/last time, span.
8. **Weather join** (context only): `first_weighing_at` (Europe/Helsinki) → convert to UTC → **ceil to the next full hour** (an event exactly on the hour keeps its own hour) → left join `fact_weather`. Reason: FMI `r_1h` at time t is the accumulation over the **hour ending at t** (Phase 2 empirical test, one rainy day: mean error 0.021 mm vs 0.378 mm), so the observation stamped at the end of the hour containing the meal is the one that covers it. A session without weather stays valid.
9. **Volume flags**: per service date and population compute `observed_regime` (`high` if sessions >= 30, else `low`) and compare with the weekday's `expected_regime` (Mon-Wed high, Thu-Fri low, derived from the baseline weeks 2020-10-05..30). Set `low_observed_volume_day` and `volume_irregularity`. Days are **never** excluded.

## 8. Validation

Rule taxonomy and full definitions in `docs/validation_rules.md`. Severities: `INFO`, `WARN`, `ERROR`. Handling classes: `FLAG` (kept, counted), `QUARANTINE` (kept in model, excluded from primary metrics, listed), `BLOCK` (stops the affected stage; used for structural failures such as missing required columns).

`core_ready` = registered-export population, no `ERROR` on the session or any of its events, no identity conflict, all weights > 0, at least one event, timestamps parsed. Thresholds live in `config/thresholds.yml` (approved values and evidence: `docs/phase2_validation_findings.md`). M5 = `core_ready` sessions / all registered-export session IDs in the source (**1,699, fixed before any removal**); the warn-free rate (no session-level WARN, same denominator; baseline 1,663 / 1,699 = 97.88%) is reported beside it. All thresholds are **diagnostic validation thresholds derived from observed data structure, approved 2026-09-19, not claims of physical impossibility**. Volume flags are flag-only and appear in no metric filter.

## 9. Pipeline

`python -m src.pipeline.run [--stages ingest|all] [--out outputs]` : **always offline**. It never downloads. If a raw source is missing it fails and names the explicit retrieval command.

`python -m src.pipeline.fetch --source flavoria|weather [--refresh] [--dest data/raw] [--print-pins]` : the **only** network-using command. It never overwrites raw files and never edits pins; a refreshed source is a new snapshot, adopted only by an explicit, documented change to `config/sources.yml`.

| # | Stage | Output | On failure |
|---|---|---|---|
| 1 | Source discovery | expected inputs list | `FAILED` (core) / `BLOCKED` (weather) if a pinned file is absent; the message names the explicit fetch command; **never downloads** |
| 2 | Snapshot identity, checksum verification, schema fingerprint, timezone override scope (T10) | `outputs/ingestion/*` | mismatch = `FAILED` (Flavoria) / weather `BLOCKED`; pins never updated, nothing re-downloaded |
| 3 | Raw preservation check, ingestion manifest, staging handoff | raw tree byte/mtime identical; `source_snapshot.csv`, `raw_artifact_manifest.csv`, `staging_handoff.json` | `FAILED` if raw changed |
| 4 | Profiling | `profile_summary.csv` | `WARNING` |
| 5 | Validation | `validation_issues.csv` | records issues; structural = `BLOCKED` |
| 6 | Staging (WP3): verified raw to staging tables; canonical timestamps; field normalization | staging tables | `FAILED` |
| 7 | External enrichment | `fact_weather` | `RECOVERED` (retry) / `WARNING` (partial) / `BLOCKED` for weather-dependent outputs only |
| 8 | Reconciliation | `reconciliation_summary.csv` | `WARNING` |
| 9 | Model build | SQLite | `FAILED` |
| 10 | Metrics + sensitivity | `kpi_summary.csv`, `measurement_readiness.csv`, `sensitivity_analysis.csv` (baseline row must equal the headline KPIs) | per-metric `BLOCKED` |
| 11 | Evidence | `final_evidence.csv` | `FAILED` |
| 12 | Quality gate | pass/fail summary | see 9.2 |
| 13 | Run manifest + log | `run_manifest.json`, `logs/` | always written, even on failure |

### 9.1 Failure classification

| Class | Meaning |
|---|---|
| `RECOVERED` | A fault occurred and a retry or fallback succeeded (weather timeout, then success) |
| `WARNING` | Output produced with a documented limitation (weather gap, timezone-suspect file) |
| `FAILED` | A stage could not do its job; the run stops with a message |
| `BLOCKED` | A specific output cannot be produced because a prerequisite is unavailable (waste; weather metrics without weather) |

Handled cases: HTTP timeout, transient 5xx, rate limit (429/backoff), malformed XML, missing input, corrupted archive (checksum mismatch, raw copy retained), schema mismatch (missing required column = `BLOCKED`; unexpected column = `WARNING`), incomplete weather, validation failures.

### 9.2 Quality gate

Two independent gates, reported separately:
- **Core gate**: raw checksums match, all required columns present, ≥ 1 valid primary session, no unexplained event loss (`events_in = events_modelled + events_quarantined`).
- **Context gate**: weather retrieved and parsed. Failing it downgrades weather outputs to `BLOCKED` and never touches the core gate.

### 9.3 Idempotency and reproducibility

Rerun on identical inputs must give identical row counts, identical SHA-256 of every CSV in `outputs/` (excluding `run_manifest.json`), and identical metric values. A normal run is offline by construction (a test forbids every socket operation and makes `requests` unimportable), so the assignment is reproducible with no network.

## 10. Outputs

```text
outputs/source_inventory.csv
outputs/run_manifest.json
outputs/validation/profile_summary.csv, validation_issues.csv, validation_summary_by_rule.csv, **sensitivity_analysis.csv**
outputs/reconciliation/reconciliation_summary.csv
outputs/metrics/kpi_summary.csv, measurement_readiness.csv, population_diagnostics.csv
outputs/evidence/final_evidence.csv (+ final_evidence.md)
```

`final_evidence.csv` columns: `metric, value, population, definition, source, records_used, records_excluded, evidence_status, limitation`. Evidence statuses: `READY`, `READY_WITH_LIMITATION`, `BLOCKED`.

`run_manifest.json`: run id, per-source retrieval time, URL, filename, SHA-256, size, row count, version, per-stage status, gate results, counts.

## 11. Logging

Structured line log per run. Every decision that changes data (override applied, duplicate excluded, quarantine) is a log line **and** a row in `validation_issues.csv`.

## 12. Tests (business rules first, not syntax)

`tests/test_ingest.py` (checksum, 11 files, row counts), `test_schema.py` (drift: 7 of 11 files lack `weighting_type`, still ingest), `test_timezone.py` (override applied, T07 detects unregistered shift), `test_validation.py` (duplicates, zero weight, identification-before-weighing), `test_model.py` (grain: no duplicate keys; events reconcile to sessions), `test_metrics.py` (median, P90 on hand-built fixtures; NULL never becomes 0), `test_weather_join.py` (UTC ceil (hour-ending) and DST correctness; missing weather keeps session valid), `test_waste_blocked.py` (waste metric always `BLOCKED`, never numeric), `test_pipeline_idempotency.py` (run twice, hashes equal), `test_failure_modes.py` (empty input, corrupt archive, weather 500). Added after Phase 2: `test_row_order.py` (newest-first file gives identical sessions), `test_timestamp_formats.py` (dotted identification with dashed weighing), `test_weather_hour_ending.py` (ceil rule; `r_1h` maps to the hour containing the meal), `test_volume_flags.py` (irregular days flagged, never excluded), `test_component_counting.py` (M4 within-session; no alias collapse).

## 13. Known risks

| Risk | Handling |
|---|---|
| Unresolved semantics of the filename labels | Used only as population labels (registered-export / non-registered-export); primary claims limited to that population |
| Registered-export daily volume is a weekday-patterned schedule, not demand | M3 worded as observed sessions; irregular days flagged, retained |
| Component identity differs across exports in 2020-10-05..16 | M4 counted within a session; component-level comparison marked LIMITED; no alias table |
| Timezone normalisation is the strongest-supported decision, not source-confirmed | Config-driven, labelled per row, isolated to context and time-of-day outputs |
| FMI `r_1h` convention is undocumented on the pages reviewed | Tested empirically on one rainy day (hour ending); join rule uses it; precipitation used descriptively only |
| Zenodo/FMI availability | Raw files committed and pinned; normal runs never need the network; explicit `fetch` restores or refreshes |
