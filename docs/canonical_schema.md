# Canonical Schema (final)

The single source for table grains and columns. `data_dictionary.md` describes each field's meaning; this document fixes the structure. Nothing here is implemented yet.

**Semantic classes.** OBSERVED = recorded by an instrument or external authority. DERIVED = computed by us under a stated rule. UNKNOWN and SOURCE GAP are **never stored as zero**: consumed quantity has no column, and `waste_weight_g` does not exist in any fact table; the waste metric is a `BLOCKED` evidence row.

**Populations** are `registered_export` and `non_registered_export`, labels inherited from source filenames and not interpreted.

## 1. Table grains

| Table | **One row =** | Primary key | Class | Expected baseline rows |
|---|---|---|---|---:|
| `fact_weighing_event` | one component weighing event, exactly as recorded in one source row (duplicates kept, flagged) | `event_id` = `source_file#source_row_number` | OBSERVED | 12,284 |
| `fact_dining_session` | one **derived** dining session: events sharing a `session_id` within one population | (`session_id`, `population`) | DERIVED | 3,345 (1,699 registered-export + 1,646 non-registered-export) |
| `fact_session_component` | one distinct normalised component within one session | (`session_id`, `population`, `component_id_normalized`) | DERIVED | computed by pipeline |
| `fact_weather` | one FMI observation hour at one station, one column per parameter | (`fmisid`, `obs_time_utc`) | OBSERVED (external) | 1,129 |
| `fact_daily_volume` | one service date within one population | (`service_date`, `population`) | DERIVED | 65 (35 registered-export + 30 non-registered-export) |
| `fact_validation_issue` | one rule violation on one entity | `issue_id` | audit | see golden values |
| `dim_scale` | one physical lunch-line scale | `scale_id` | reference | 30 |
| `dim_component_name` | one distinct raw component string and its normalised form | `component_name_raw` | reference | 246 |
| `dim_date` | one calendar date in the study window | `service_date` | reference | 47 |
| `source_snapshot` | one **immutable, checksum-identified set of raw artifacts from one source** (identity derived from content, never from time) | `source_snapshot_id` | audit | 2 (Flavoria, FMI) |
| `raw_file_manifest` | one raw artifact (file, or member of a raw archive) inside one snapshot, verified against its pin | `artifact_id` | audit | 21 (archive, 11 members, 7 weather chunks, 2 evidence files) |
| `pipeline_run` | one pipeline execution | `run_id` | audit | grows per run; excluded from output comparison |

Every metric and sensitivity output is a CSV (`outputs/`), not a table, so it can be diffed between runs.

**Implementation note (WP2).** `source_snapshot` and `raw_file_manifest` are produced by ingestion as CSV under `outputs/ingestion/` (deterministic) and are loaded into SQLite by the model build (WP5). Only `source_snapshot_id` is deterministic content identity; the run record (`ingestion_run.json`) is the one time-dependent file.

## 2. DDL (SQLite)

```sql
CREATE TABLE fact_weighing_event (
  event_id                   TEXT PRIMARY KEY,           -- source_file || '#' || source_row_number
  source_snapshot_id         TEXT NOT NULL REFERENCES source_snapshot(source_snapshot_id),
  raw_artifact_id            TEXT NOT NULL REFERENCES raw_file_manifest(artifact_id),   -- the archive member this row came from
  source_file                TEXT NOT NULL,
  source_row_number          INTEGER NOT NULL,
  population                 TEXT NOT NULL CHECK (population IN ('registered_export','non_registered_export')),
  session_id                 TEXT NOT NULL,
  tray_id                    TEXT NOT NULL,
  scale_id                   TEXT NOT NULL REFERENCES dim_scale(scale_id),
  component_name_raw         TEXT NOT NULL,
  component_id_normalized    TEXT NOT NULL,              -- trim, collapse whitespace, casefold; no alias table
  component_weight_g         INTEGER NOT NULL,           -- OBSERVED, source weight_of_a_component, unchanged
  source_time_raw            TEXT NOT NULL,              -- verbatim
  event_time_local           TEXT NOT NULL,              -- Europe/Helsinki, ISO 8601
  timezone_normalization     TEXT NOT NULL CHECK (timezone_normalization IN
                             ('SOURCE_LOCAL_ASSUMED','NORMALISED_PLUS_3H_STRONGEST_SUPPORT')),
  identification_time_local  TEXT NOT NULL,
  weighing_type              TEXT,                       -- NULL where the column is absent (7 of 11 files)
  is_exact_duplicate         INTEGER NOT NULL DEFAULT 0,
  quality_status             TEXT NOT NULL CHECK (quality_status IN ('VALID','WARN','INVALID')),
  UNIQUE (source_file, source_row_number)
);

CREATE TABLE fact_dining_session (
  session_id                       TEXT NOT NULL,
  population                       TEXT NOT NULL,
  source_snapshot_id               TEXT NOT NULL REFERENCES source_snapshot(source_snapshot_id),
  is_primary_population            INTEGER NOT NULL,       -- population = registered_export
  tray_id                          TEXT NOT NULL,
  service_date                     TEXT NOT NULL,
  first_weighing_at                TEXT NOT NULL,
  last_weighing_at                 TEXT NOT NULL,
  identification_time_local        TEXT NOT NULL,
  derived_selected_meal_weight_g   INTEGER,                -- DERIVED: SUM of non-duplicate event weights; NULL if any invalid
  component_weighing_event_count   INTEGER NOT NULL,       -- diagnostic
  distinct_component_count         INTEGER NOT NULL,       -- distinct component_id_normalized within the session (feeds M4)
  distinct_component_count_status  TEXT NOT NULL CHECK (distinct_component_count_status IN ('READY_WITH_LIMITATION','LIMITED')),
  session_span_s                   INTEGER NOT NULL,
  session_duration_minutes         REAL NOT NULL,
  identity_conflict                INTEGER NOT NULL,       -- session_id present in both populations
  core_ready                       INTEGER NOT NULL,       -- primary population, no ERROR, no identity conflict (weather never enters)
  has_session_warn                 INTEGER NOT NULL,
  has_event_warn                   INTEGER NOT NULL,
  quality_status                   TEXT NOT NULL,
  weather_hour_utc                 TEXT,                   -- ceil to next full UTC hour (hour-ending rule)
  weather_matched                  INTEGER NOT NULL,       -- context only; never affects core_ready
  PRIMARY KEY (session_id, population)
);

CREATE TABLE fact_session_component (
  session_id                       TEXT NOT NULL,
  population                       TEXT NOT NULL,
  component_id_normalized          TEXT NOT NULL,
  component_weighing_event_count   INTEGER NOT NULL,
  scale_ids                        TEXT NOT NULL,          -- sorted, comma separated
  derived_component_weight_g       INTEGER NOT NULL,
  PRIMARY KEY (session_id, population, component_id_normalized),
  FOREIGN KEY (session_id, population) REFERENCES fact_dining_session(session_id, population)
);

CREATE TABLE fact_weather (
  fmisid            INTEGER NOT NULL,
  obs_time_utc      TEXT NOT NULL,
  t2m_c             REAL,                                  -- NULL stays NULL, never 0
  ws_10min_ms       REAL,
  r_1h_mm           REAL,                                  -- accumulation over the hour ENDING at obs_time_utc
  ri_10min_mmh      REAL,
  source_file       TEXT NOT NULL,
  source_snapshot_id TEXT NOT NULL REFERENCES source_snapshot(source_snapshot_id),
  raw_artifact_id   TEXT NOT NULL REFERENCES raw_file_manifest(artifact_id),
  PRIMARY KEY (fmisid, obs_time_utc)
);

CREATE TABLE fact_daily_volume (
  service_date               TEXT NOT NULL,
  population                 TEXT NOT NULL,
  sessions                   INTEGER NOT NULL,             -- crossover sessions excluded
  events                     INTEGER NOT NULL,
  observed_regime            TEXT NOT NULL CHECK (observed_regime IN ('high','low')),  -- high if sessions >= 30
  expected_regime            TEXT NOT NULL CHECK (expected_regime IN ('high','low')),  -- Mon-Wed high, Thu-Fri low (baseline 2020-10-05..30)
  low_observed_volume_day    INTEGER NOT NULL,             -- FLAG ONLY
  volume_irregularity        INTEGER NOT NULL,             -- FLAG ONLY; never excludes a day or session
  PRIMARY KEY (service_date, population)
);

CREATE TABLE fact_validation_issue (
  issue_id                   INTEGER PRIMARY KEY,
  run_id                     TEXT NOT NULL,
  rule_id                    TEXT NOT NULL,
  category                   TEXT NOT NULL CHECK (category IN
                             ('STRUCTURAL','BUSINESS','TEMPORAL','IDENTITY','CROSS-SOURCE','COMPLETENESS')),
  severity                   TEXT NOT NULL CHECK (severity IN ('INFO','WARN','ERROR')),
  entity_type                TEXT NOT NULL,                -- file | event | session | service_day | population
  entity_id                  TEXT NOT NULL,
  population                 TEXT,
  source_file                TEXT,
  message                    TEXT NOT NULL,
  handling                   TEXT NOT NULL,                -- FLAG | QUARANTINE | BLOCK | KEEP_FIRST
  business_consequence       TEXT NOT NULL
);

CREATE TABLE dim_scale (scale_id TEXT PRIMARY KEY, station_family TEXT NOT NULL, side TEXT, scale_kind TEXT NOT NULL, position INTEGER);
CREATE TABLE dim_component_name (component_name_raw TEXT PRIMARY KEY, component_id_normalized TEXT NOT NULL, has_edge_whitespace INTEGER NOT NULL);
CREATE TABLE dim_date (service_date TEXT PRIMARY KEY, weekday TEXT NOT NULL, is_weekday INTEGER NOT NULL, in_study_window INTEGER NOT NULL);
CREATE TABLE source_snapshot (
  source_snapshot_id   TEXT PRIMARY KEY,           -- '<source>-' + first 12 hex of snapshot_sha256; content-derived
  source_name          TEXT NOT NULL,              -- flavoria | fmi_weather
  lane                 TEXT NOT NULL,              -- core | context
  source_url           TEXT NOT NULL,
  version              TEXT NOT NULL,
  license              TEXT NOT NULL,
  retrieved_on         TEXT NOT NULL,              -- pinned retrieval date of the committed artifacts
  retrieval_method     TEXT NOT NULL,
  artifact_count       INTEGER NOT NULL,
  snapshot_sha256      TEXT NOT NULL,              -- sha256 of the sorted (kind|filename|sha256|size) lines
  status               TEXT NOT NULL               -- VERIFIED | FAILED | MISSING
);
CREATE TABLE raw_file_manifest (
  artifact_id          TEXT PRIMARY KEY,           -- '<snapshot_id>/<filename>' or '<snapshot_id>/<archive>::<member>'
  source_snapshot_id   TEXT NOT NULL REFERENCES source_snapshot(source_snapshot_id),
  kind                 TEXT NOT NULL,              -- archive | member | weather_chunk | evidence
  filename             TEXT NOT NULL,
  path                 TEXT NOT NULL,              -- repo-relative
  parent_artifact_id   TEXT,                       -- a member points to its archive
  source_url           TEXT NOT NULL,
  retrieved_on         TEXT NOT NULL,
  version              TEXT NOT NULL,
  in_snapshot_identity INTEGER NOT NULL,           -- evidence files are preserved but not part of identity
  size_bytes           INTEGER, md5 TEXT, sha256 TEXT,
  expected_size_bytes  INTEGER, expected_sha256 TEXT,
  row_count            INTEGER, expected_rows INTEGER,
  status               TEXT NOT NULL,              -- VERIFIED | MISSING | SIZE_MISMATCH | CHECKSUM_MISMATCH | ...
  message              TEXT
);
CREATE TABLE pipeline_run (run_id TEXT PRIMARY KEY, started_at TEXT NOT NULL, finished_at TEXT, status TEXT NOT NULL,
  core_gate TEXT, context_gate TEXT, code_version TEXT, input_fingerprint TEXT);
```

## 3. Invariants the pipeline must enforce (each becomes a test)

| # | Invariant | Reason |
|---|---|---|
| I-1 | `fact_weighing_event` row count = sum of raw file rows (12,284) | no silent loss |
| I-2 | events in = events modelled + duplicates excluded from sums + events quarantined (C04) | reconciliation |
| I-3 | (`session_id`, `population`) unique; a `session_id` with `identity_conflict = 1` has `core_ready = 0` in both versions | identity |
| I-4 | `weather_matched = 0` never changes `core_ready` | core vs context separation |
| I-5 | no column, view or metric named or computed as waste or consumption, other than the `BLOCKED` evidence row | semantic layers |
| I-6 | `volume_irregularity` and `low_observed_volume_day` appear in no WHERE clause of any metric query | flag-only rule |
| I-7 | M5 denominator = count of registered-export session IDs in the source, computed **before** any removal | denominator rule |
| I-8 | `timezone_normalization` is non-null on every event and is `NORMALISED_PLUS_3H_STRONGEST_SUPPORT` exactly for the override file | timezone honesty |
| I-9 | rerun on unchanged inputs: identical row counts and SHA-256 of every output CSV | idempotency |
| I-10 | `derived_selected_meal_weight_g` = sum of `component_weight_g` over non-duplicate events of the session | derivation rule |
| I-11 | every source-derived row carries a `source_snapshot_id` present in `source_snapshot`, and its `raw_artifact_id` exists in `raw_file_manifest` | provenance: snapshot, artifact, checksum, URL, retrieval metadata |
| I-12 | a run leaves `data/raw/` byte- and mtime-identical (`raw_unchanged_during_run = true`) | immutable raw preservation |
| I-13 | ingestion outputs contain no wall-clock value; two runs on identical inputs give identical SHA-256 for every deterministic ingestion file | determinism |

## 4. Baseline "golden values" (the pipeline must reproduce these)

| Quantity | Value |
|---|---:|
| Raw event rows | 12,284 |
| Session IDs / `(session_id, population)` rows | 3,343 / 3,345 |
| Registered-export session IDs (eligible, M5 denominator) | 1,699 |
| Canonical sessions (M3, M5 numerator) | 1,697 |
| Non-registered-export sessions excluding crossover | 1,644 |
| Exact duplicate rows | 2 |
| M1 / M2 / M4 | 499 g / 1,039.6 g / 5 |
| M5 / Warn-free rate | 99.88% (1,697/1,699) / 97.88% (1,663/1,699); event-level variant 97.70% (1,660/1,699), diagnostic |
| Weather hours / canonical sessions matched (dry run) | 1,129 / 1,697 |
| Validation issues (Phase 2 exploration) | 1,278 |
