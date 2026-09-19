# Data Dictionary (final)

Structure and grains are fixed in `canonical_schema.md`; this document gives every field's meaning, origin and transformation. Population labels (`registered_export`, `non_registered_export`) are inherited from source filenames and are not interpreted. Thresholds cited here are diagnostic, not physical.

Written after inspecting the real files. Columns in the raw section are exactly what the archive contains. Nothing is renamed or reinterpreted without a row in the "Transformation" column. Classes: OBSERVED / DERIVED / UNKNOWN / SOURCE GAP.

## 1. Raw source: FlavoriaFoodWeight1700 CSV (grain: one component weighing event)

11 files, UTF-8 with BOM, CRLF line endings, 12,284 data rows. Each file has 4 trailing blank columns from trailing commas (always empty; rule S04).

| Field | Description | Source | Original meaning | Type | Nullable? | Grain | Allowed values | Quality concerns | Transformation | Final model field |
|---|---|---|---|---|---|---|---|---|---|---|
| `session_id` | Identifier grouping events of one tray pass | CSV | `session<N>`, N = 0..3342, contiguous | string | No (0 empty) | event → session | `session\d+` | Appears in both exports for 2 IDs (`session2266`, `session3222`) | none; kept verbatim | `fact_weighing_event.session_id` |
| `weighing_event_time` | When the scale recorded this component | CSV | wall-clock time, **no timezone stated** | string | No | event | `YYYY-MM-DD HH:MM:SS` (10,353 rows) or `YYYY.MM.DD HH:MM:SS` (1,931 rows) | One file (the dotted one) is 3 h behind the others (+3h is the strongest-supported normalisation, not source-confirmed); row order is not chronological in any file; 7 sessions span more than 10 min | raw kept as `event_time_raw`; parsed; converted to Europe/Helsinki using per-file registry | `event_time_local`, `event_time_raw`, `timezone_handling` |
| `weighting_type` (sic) | Kind of weighing | CSV | only value observed: `line` | string | **Column absent in 7 of 11 files**; 6,990 rows have no such column | event | `line` | Schema drift; spelling in source is `weighting_type` | if absent, NULL and INFO issue S03 | `weighing_type` |
| `scale_identifier` | Physical scale at a serving station | CSV | `<line>-<side>-<kind><n>`, e.g. `koti2-vasen-salaatti3` | string | No | event | 30 distinct values; lines `koti2`, `vege2`; kinds `salaatti` (cold) / `lammin` (hot) | Stable key; parsing structure inferred from names | split into parts | `scale_id`, `dim_scale.{station_family, side, kind, position}` |
| `weight_of_a_component` | Grams of one component when placed | CSV | grams, integer | integer | No (0 non-numeric) | event | 1..2097 observed; 0 and negative: none | 139 events = 1 g, 513 ≤ 3 g; 6 events ≥ 1,500 g; one 2,097 g | cast to integer; **no clipping** | `component_weight_g` (OBSERVED) |
| `component_name` | Label of the food at that scale | CSV | menu label, Finnish or English, mixed case | string | No | event | 246 distinct raw strings | 398 rows with edge whitespace on 16 names (trimming merges nothing); case-fold merges one pair; the same scale and day is labelled differently across the two exports in 2020-10-05..16 (86 of 213 scale-days with disjoint name sets, mixing language variants and different dishes); 183 names appear on more than one scale | raw kept; trim + whitespace collapse + case-fold; **no alias table** | `component_name_raw`, `component_id_normalized` |
| `tray_id` | RFID tray | CSV | `tray<N>`, 687 distinct | string | No | session → tray | `tray\d+` | Trays reused across days (87% used on more than one day); tray ≠ session ≠ person | none | `tray_id` |
| `user_identification_time` | When the tray was identified (the source does not define the step further) | CSV | wall-clock, no timezone; median 52 s after last weighing | string | No | session (one value per session and population) | same two formats, decided per column | 3 sessions where it precedes the last weighing (the tray returned to the line); `non_registered_2020-11-09_2020-11-15.csv` has dotted format here and dashed format in `weighing_event_time` | parsed with the same tz rule as the event | `identification_time_local` |
| *(4 blank columns)* | none | CSV | trailing-comma artefact | n/a | always empty | n/a | empty | Rule S04 flags any non-empty value | dropped **after** verifying empty | none |
| *(file name)* | Population and period | file | `registered_*` / `non_registered_*` plus a date range | string | No | file | 2 population prefixes | Two date-format spellings; date ranges overlap on paper (`10-25`) | parsed | `population`, `source_file` |

## 2. Raw source: FMI observations (grain: one parameter value at one station and hour)

XML `wfs:FeatureCollection`, one `BsWfs:BsWfsElement` per (time, parameter). Time is UTC (`Z`). Station is Turku Artukainen, FMISID 100949 (60.4544 N, 22.1787 E).

| Field | Description | Source | Original meaning | Type | Nullable? | Grain | Allowed values | Quality concerns | Transformation | Final model field |
|---|---|---|---|---|---|---|---|---|---|---|
| `BsWfs:Time` | Observation time | FMI | UTC instant | ISO 8601 | No | hour | hourly, 2020-10-05T00Z..2020-11-21T00Z | Complete: 1,129 hours | parse as UTC | `obs_time_utc` |
| `ParameterName` = `t2m` | Air temperature at 2 m | FMI | °C | float | No (0 NaN) | station × hour | -2.6..16.5 observed | none found | pivot | `t2m_c` |
| `ParameterName` = `ws_10min` | Wind speed, 10-min mean | FMI | m/s | float | No (0 NaN) | station × hour | 0..10.5 | none found | pivot | `ws_10min_ms` |
| `ParameterName` = `r_1h` | Precipitation amount, 1 h | FMI | mm | float | **Yes** (2 NaN) | station × hour | 0..6.6 | Convention tested empirically (one rainy day): the value at time t is the **hour ending at t** (mean error 0.021 mm vs 0.378 mm) | pivot; NaN stays NULL | `r_1h_mm` |
| `ParameterName` = `ri_10min` | Precipitation intensity, 10 min | FMI | mm/h | float | **Yes** (1 NaN) | station × hour | 0..6.7 | same | pivot; NaN stays NULL | `ri_10min_mmh` |
| `gml:pos` | Station position | FMI | lat lon | string | No | station | one value | Point resolved from `fmisid` | store | `dim_station` (implicit, one row) |

## 3. Model: `fact_weighing_event` (one row per component weighing event; OBSERVED)

| Field | Type | Nullable? | Definition | Class |
|---|---|---|---|---|
| `event_id` | text | No | `source_file` + `#` + `source_row_number`; stable across runs | key |
| `source_file`, `source_row_number` | text, int | No | Raw provenance | OBSERVED |
| `population` | text | No | `registered_export` or `non_registered_export`, inherited from the file name; **not** interpreted as customer-registration status | DERIVED (label) |
| `session_id`, `tray_id`, `scale_id` | text | No | verbatim from source | OBSERVED |
| `station_family` | text | No | `koti2` or `vege2` from `scale_id` | DERIVED |
| `component_name_raw` | text | No | verbatim | OBSERVED |
| `component_id_normalized` | text | No | trimmed, whitespace-collapsed, case-folded | DERIVED |
| `component_weight_g` | integer | No | grams recorded by the scale | **OBSERVED** |
| `event_time_raw` | text | No | verbatim source text; never overwritten | OBSERVED |
| `event_time_local` | text | Yes | wall time after any file-specific normalization (naive ISO 8601); NULL if unparseable | DERIVED |
| `event_time_canonical_utc` | text | Yes | canonical instant (ISO 8601 `Z`); NULL when the local time is ambiguous, nonexistent or unparseable | DERIVED |
| `event_time_status` | text | No | `OK`, `AMBIGUOUS`, `NONEXISTENT`, `UNPARSEABLE` | DERIVED |
| `timezone_handling` | text | No | `SOURCE_LOCAL_ASSUMED`, or `NORMALISED_PLUS_3H_STRONGEST_SUPPORT` for the one file-specific override (not source-confirmed) | DERIVED |
| `timezone_offset_hours_applied` | int | No | 0, or 3 for the override file | DERIVED |
| `timezone_transformation_reason` | text | No | why the treatment was applied, e.g. `cross-export temporal alignment (file-specific, evidence-backed; not source-confirmed)` | DERIVED |
| `identification_time_raw`, `identification_time_local`, `identification_time_canonical_utc`, `identification_time_status` | text | as above | the same three-part treatment for the identification time | DERIVED |
| `weighing_type` | text | Yes | `line` or NULL | OBSERVED |
| `is_exact_duplicate` | bool | No | identical repeat of an earlier row in the same file | DERIVED |
| `quality_status` | text | No | `VALID`, `WARN`, `INVALID` | DERIVED |

> **Original model design.** The implemented canonical tables are specified in section 12, which governs where names or rules differ (for example `component_weighing_event_count` is now `modellable_event_count`, and the selected weight sums MODELLABLE events).

## 4. Model: `fact_dining_session` (one **derived** session per `session_id` × population; DERIVED)

| Field | Type | Nullable? | Definition | Class |
|---|---|---|---|---|
| `session_id` | text | No | key with `population` | OBSERVED grouping key |
| `population` | text | No | see above | DERIVED |
| `is_primary_population` | bool | No | population = `registered_export` | DERIVED |
| `tray_id` | text | No | the one tray of the session | OBSERVED |
| `service_date` | date | No | local date of first event | DERIVED |
| `first_weighing_at`, `last_weighing_at`, `identification_time_local` | timestamp | No | min/max over events; identification time | DERIVED |
| `component_weighing_event_count` | int | No | non-duplicate events | DERIVED |
| `distinct_component_count` | int | No | distinct `component_id_normalized` within the session (feeds M4) | DERIVED (name-dependent) |
| `distinct_component_count_status` | text | No | `READY_WITH_LIMITATION`, or `LIMITED` where cross-export component identity is unstable (rule I07) | DERIVED |
| `session_duration_minutes` | real | No | `session_span_s / 60` | DERIVED |
| **`derived_selected_meal_weight_g`** | integer | Yes | `SUM(component_weight_g)` over non-duplicate events; NULL if an event weight is invalid | **DERIVED. Not an observed meal weight.** |
| `session_span_s` | int | No | last event − first event, seconds | DERIVED |
| `identity_conflict` | bool | No | `session_id` present in both populations | DERIVED |
| `core_ready` | bool | No | primary population, no ERROR-level violation, no identity conflict; **excludes weather, WARN rules and volume flags** | DERIVED |
| `has_session_warn` | bool | No | any session-level WARN (B04, B07, T04, T05, I06) | DERIVED |
| `has_event_warn` | bool | No | any event-level WARN (B02, I02) on the session's events; used only by the diagnostic event-level warn-free variant | DERIVED |
| `quality_status` | text | No | worst status among its events and session rules | DERIVED |
| `weather_hour_utc` | timestamp | Yes | first weighing converted to UTC, ceiled to the next full hour (hour-ending rule) | DERIVED |
| `weather_matched` | bool | No | a `fact_weather` row exists for `weather_hour_utc` | DERIVED |
| `consumed_weight_g` | n/a | not modelled | food actually eaten | **UNKNOWN**, no column, no value |
| `waste_weight_g` | real | **Always NULL** | food discarded | **SOURCE GAP**, never 0 |

## 5. Model: `fact_session_component` (one distinct normalised component within a session; DERIVED)

| Field | Type | Nullable? | Definition |
|---|---|---|---|
| `session_id`, `population`, `component_id_normalized` | text | No | composite key |
| `component_weighing_event_count` | int | No | events for that component in the session (>1 means repeat weighing or same name on two scales) |
| `scale_ids` | text | No | sorted list of scales used |
| `derived_component_weight_g` | integer | No | sum of that component's event weights |

## 5b. Model: `fact_daily_volume` (one service date within one population; DERIVED)

`service_date, population, sessions, events, observed_regime (high if sessions >= 30 else low), expected_regime (Mon-Wed high, Thu-Fri low; baseline 2020-10-05..30), low_observed_volume_day, volume_irregularity`. Flags describe; no day is excluded. Cause of irregularity: **unresolved**.

## 6. Model: `fact_weather` (one station × UTC hour; OBSERVED external)

`fmisid, obs_time_utc, t2m_c, ws_10min_ms, r_1h_mm, ri_10min_mmh, source_file, is_null_any`. Missing values are NULL, never 0.

## 7. Audit tables

- `fact_validation_issue`: `issue_id, run_id, rule_id, severity, entity_type, entity_id, message, handling, business_consequence`.
- `source_snapshot`: `source_snapshot_id, source_name, lane, source_url, version, license, retrieved_on, retrieval_method, artifact_count, snapshot_sha256, status`. One immutable, checksum-identified set of raw artifacts from one source. The identifier is derived from content, never from time.
- `raw_file_manifest`: `artifact_id, source_snapshot_id, kind, filename, path, parent_artifact_id, source_url, retrieved_on, version, in_snapshot_identity, size_bytes, md5, sha256, expected_size_bytes, expected_sha256, row_count, expected_rows, status, message`. One raw artifact inside one snapshot, verified against its pin.
- Ingestion also writes `schema_fingerprints.csv` (one CSV header, its fingerprint and known-variant classification), `weather_inventory.csv` (per weather chunk completeness evidence), `staging_handoff.json` and `ingestion_summary.json`.
- Every fact table row carries `source_snapshot_id` (`fact_weighing_event` and `fact_weather` also carry `raw_artifact_id`), so any value traces to a snapshot, a raw artifact, a checksum, a source URL and retrieval metadata.
- `pipeline_run`: `run_id, started_at, finished_at, status, core_gate, context_gate`.

## 8. Metric-facing fields

| Metric | Fields it reads | Filter |
|---|---|---|
| M1, M2 | `derived_selected_meal_weight_g` | `core_ready = 1` |
| M3 | session count | `core_ready = 1` |
| M4 | `distinct_component_count` | `core_ready = 1` |
| M5 | `core_ready` / count of registered-export IDs | eligible denominator fixed first |
| S1 | `weather_matched` | eligible denominator |
| S2 | `has_session_warn` (canonical); `has_event_warn` (diagnostic variant) | eligible denominator |
| W1 | none | `BLOCKED` |

## 9. Enumerations

| Field | Values |
|---|---|
| `population` | `registered_export`, `non_registered_export` |
| `timezone_handling` | `SOURCE_LOCAL_ASSUMED`, `NORMALISED_PLUS_3H_STRONGEST_SUPPORT`, `SOURCE_UTC_STATED` |
| `local_time_status` | `OK`, `AMBIGUOUS`, `NONEXISTENT`, `UNPARSEABLE` |
| `weight_parse_status` | `OK`, `NOT_INTEGER`, `EMPTY` |
| `row_parse_status` | `OK`, `SHORT_ROW`, `EXTRA_CELLS` |
| `value_status` | `OK`, `NAN_SOURCE_NULL`, `UNPARSEABLE` |
| `quality_status` | `VALID`, `WARN`, `INVALID` |
| `distinct_component_count_status` | `READY_WITH_LIMITATION`, `LIMITED` |
| `severity` | `INFO`, `WARN`, `ERROR` |
| `handling` | `FLAG`, `QUARANTINE`, `BLOCK`, `KEEP_FIRST` |
| evidence status | `READY`, `READY_WITH_LIMITATION`, `BLOCKED` |
| pipeline outcome | `RECOVERED`, `WARNING`, `FAILED`, `BLOCKED` |

## 10. Staging tables

Staging sits between the verified raw files and the canonical model. It **preserves and normalises; it does not judge**: every source
row is kept (duplicates, odd weights, odd timestamps), raw text is stored beside every normalised value, and every row carries its
lineage. Written to `outputs/staging/` (tables are regenerable and ignored by git; the summary and reconciliation are tracked).

### 10.1 `stg_weighing_event` (grain: one source data row = one component weighing event)

| Field group | Fields | Notes |
|---|---|---|
| Identity and lineage | `event_id` (`source_file#source_row_number`), `source_snapshot_id`, `raw_artifact_id`, `source_file`, `source_row_number`, `raw_row_sha256`, `schema_variant`, `schema_fingerprint` | row number counts non-blank data rows, 1-based; `raw_row_sha256` is over the raw cells |
| Population | `population`, `session_id`, `session_key` (`session_id\|population`) | the two populations are never merged |
| Keys | `tray_id`, `scale_id` | verbatim |
| Scale structure | `scale_line`, `scale_side`, `scale_kind`, `scale_position` | inferred from the name; NULL where unparseable |
| Component | `component_name_raw`, `component_id_normalized`, `component_name_had_edge_whitespace` | trim, collapse whitespace, casefold; **no alias table** |
| Weight | `weight_raw`, `component_weight_g`, `weight_parse_status`, `weighing_type` | `weighing_type` is read from the source column `weighting_type` (sic); NULL where the column is absent |
| Event time | `event_time_raw`, `event_time_source_format`, `event_time_local`, `event_time_canonical_utc`, `event_time_status` | see below |
| Identification time | `identification_time_raw`, `identification_time_source_format`, `identification_time_local`, `identification_time_canonical_utc`, `identification_time_status` | same treatment |
| Zone handling | `timezone_handling`, `timezone_offset_hours_applied`, `timezone_transformation_reason` | |
| Drift | `row_parse_status`, `unmapped_cells` | extra columns and cells beyond the header are preserved as JSON |

**Timestamp model.** `*_raw` is the text exactly as written and is never overwritten. `*_canonical_utc` is a UTC instant. For
`SOURCE_LOCAL_ASSUMED` rows the wall time is read as Europe/Helsinki local time using real zoneinfo rules (the study period crosses the
2020-10-25 clock change, so the offset is +3 h before it and +2 h after). A wall time that occurs twice or never is `AMBIGUOUS` or
`NONEXISTENT`, and its canonical UTC is NULL: it is never guessed. For the one override file the raw time is first shifted by +3 h
(`cross-export temporal alignment`, file-specific, not source-confirmed) and then converted by the same path; within the validated
date range that reproduces the raw time read as UTC.

### 10.2 `stg_weather_observation` (grain: one FMI observation element = one (time, parameter) in one response file)

`observation_id`, `source_snapshot_id`, `raw_artifact_id`, `source_file`, `element_index`, `fmisid`, `obs_time_raw`, `obs_time_canonical_utc`,
`timezone_handling` (`SOURCE_UTC_STATED`), `parameter`, `value_raw`, `value`, `value_status`. NaN is stored as NULL with status
`NAN_SOURCE_NULL`, never zero.

### 10.3 Other staging outputs

`staging_file_reconciliation.csv` (per member: rows verified at ingestion vs staged, population, zone handling, status counts) and
`staging_summary.json` (counts, statuses, declared transformations, output checksums).


## 11. Validation tables

Written to `outputs/validation/` from the verified staging tables. They are evidence about staging: they add findings, dispositions and
reconciliation, and they change no staged value. Field meanings for the issue table, the severity / handling / quarantine distinction
and the lineage bases are in `validation_rules.md` ("validation implementation").

| Table | Grain | Key fields |
|---|---|---|
| `validation_issues` | one finding on one entity | `validation_issue_id` (content-derived), `run_id`, `rule_id`, `severity`, `handling`, `quarantine`, `entity_type`, `entity_id`, `session_key`, `event_id`, `lineage_basis`, `source_row_lineage` |
| `event_validation_status` | one staged event | `event_id`, `disposition` (`MODELLABLE`, `DUPLICATE_EXCLUDED`, `QUARANTINED`), rule ids by severity |
| `session_validation_status` | one `(session_id, population)` key | counts, `service_date`, `span_s`, `rule_weight_sum_g` (validation working value; the canonical `derived_selected_meal_weight_g` is produced in model), `quarantined`, `session_level_warn`, `event_level_warn`, day flags |
| `quarantine_manifest` | one quarantined session key or event | `quarantine_entity_type`, `entity_id`, `quarantine_rule_ids` |
| `reconciliation_summary` | one check | `check_id`, `status` (PASS, WARN, FAIL, INFO), `expected`, `observed`, `basis` |
| `service_day_volume` | one population and service date | `sessions`, `observed_regime`, `expected_regime`, `low_observed_volume_day`, `volume_irregularity_day` (registered-export only) |
| `field_completeness` | one field | `empty_rows` (true missingness), `not_applicable_rows` (column absent from the source file), `malformed_rows` |

Dispositions: `QUARANTINED` (session key quarantined; wins over repeat), `DUPLICATE_EXCLUDED` (an exact repeat of an earlier row of
the same file, left out of sums), `MODELLABLE` (available to the model layer). Every staged event has exactly one.

## 12. Canonical model

The canonical business-facing model, built from the verified staging tables and the verified validation outputs, and written to
`outputs/model/`. This section is **generated from `src/model/schema.py`** (`python -m src.model.schema`) and a test fails if it drifts.
It governs where it differs from the original model in sections 4-6, which record the original design.

**Semantic classes.** OBSERVED: written by a source system and carried through unchanged. DERIVED: computed by this pipeline by a stated
rule. VALIDATION: consumed unchanged from validation (dispositions, rule ids). PROVENANCE: says where a value came from. Two things have
**no column anywhere**: the amount actually consumed (UNKNOWN) and food waste (SOURCE GAP).

**`derived_selected_meal_weight_g` is DERIVED.** It is the sum of the weights a session's MODELLABLE weighing events recorded at the
lunch line. It is NOT consumed quantity, NOT food waste, NOT actual intake, and nothing in the model infers waste from it. It is
reconstructed from `fact_weighing_event` and then compared with validation's `rule_weight_sum_g`, a validation/reconciliation working value
that is used only as a reconciliation control and is not a canonical field (`session_weight_control.csv`).

**Event dispositions** (from validation, one per event): MODELLABLE (feeds the business fields), DUPLICATE_EXCLUDED (an exact repeat of an earlier
row of the same file: kept as a row, left out of sums), QUARANTINED (its session key is quarantined: kept as a row, no selected weight).
Business fields (weight, component counts, `modellable_event_count`) use MODELLABLE events only; timing and identity fields (first/last,
span, tray) use every event that is not an exact repeat, so a quarantined session stays traceable in time.

**Session key.** the session id and the population joined by a vertical bar (`session_key`). 3,345 keys, 3,343 distinct ids; `session2266` and `session3222` exist in both populations and
are four keys, never merged.

**Other files in `outputs/model/`:** `model_manifest.json` (tables, grains, columns, semantic classes, checksums, inputs, controls),
`model_control_summary.csv` (26 controls: PASS, WARN, FAIL, INFO) and `session_weight_control.csv` (per session: canonical weight, validation
working value, span, counts and first weighing, each MATCH, MISMATCH or EXCLUDED_QUARANTINED). The two large tables
(`fact_weighing_event.csv`, `fact_session_component.csv`) are regenerable and ignored by git.

### fact_weighing_event

**Grain:** one observed component weighing event (one source data row). **Key:** `event_id`. 37 columns.

| Field | Type | Class | Null? | Meaning | Source lineage and rule | Used downstream |
|---|---|---|---|---|---|---|
| `event_id` | text | PROVENANCE | no | source file and 1-based data-row number, `file#row` | stg_weighing_event.event_id | every join back to staging |
| `source_snapshot_id` | text | PROVENANCE | no | content-derived id of the raw snapshot | stg_weighing_event.source_snapshot_id | lineage only |
| `raw_artifact_id` | text | PROVENANCE | no | raw member identity inside the snapshot | stg_weighing_event.raw_artifact_id | lineage only |
| `source_file` | text | PROVENANCE | no | source CSV member name | stg_weighing_event.source_file | lineage only |
| `source_row_number` | integer | PROVENANCE | no | 1-based data row within the file | stg_weighing_event.source_row_number | lineage only |
| `raw_row_sha256` | text | PROVENANCE | no | SHA-256 of the raw row text | stg_weighing_event.raw_row_sha256 | lineage only |
| `population` | text | DERIVED | no | registered_export or non_registered_export, from the file name; a source label, not a semantic claim | config/populations.yml prefix rule, via staging | every population split |
| `session_id` | text | OBSERVED | no | source session identifier | stg_weighing_event.session_id | session grouping |
| `session_key` | text | DERIVED | no | `session_id|population`; the two populations are never merged | session_id + '|' + population | session join |
| `tray_id` | text | OBSERVED | no | source tray identifier (not a person) | stg_weighing_event.tray_id | lineage only |
| `scale_id` | text | OBSERVED | no | source scale identifier | stg_weighing_event.scale_id | component-scale lineage |
| `station_family` | text | DERIVED | yes | first '-' separated part of scale_id | split scale_id on '-' | lineage only |
| `component_name_raw` | text | OBSERVED | no | component name exactly as in the source, whitespace included | stg_weighing_event.component_name_raw | raw-vs-normalised check |
| `component_id_normalized` | text | DERIVED | yes | trim, collapse whitespace, case-fold; NULL if empty. No alias table, no fuzzy matching | stg_weighing_event.component_id_normalized | distinct component counts |
| `weight_raw` | text | OBSERVED | no | weight text exactly as in the source | stg_weighing_event.weight_raw | lineage only |
| `component_weight_g` | integer | OBSERVED | yes | weight in grams parsed from weight_raw; NULL if not an integer; never clipped | stg_weighing_event.component_weight_g | derived_selected_meal_weight_g |
| `weight_status` | text | DERIVED | no | OK, NOT_INTEGER or EMPTY | stg_weighing_event.weight_parse_status | weight validity |
| `weighing_type` | text | OBSERVED | yes | source weighting_type; NULL where the file has no such column (not applicable, not missing) | stg_weighing_event.weighing_type | lineage only |
| `event_time_raw` | text | OBSERVED | no | weighing time exactly as written in the source | stg_weighing_event.event_time_raw | timezone provenance |
| `event_time_local` | timestamp_local | DERIVED | yes | wall time as read (Europe/Helsinki), plus the offset only where a file-specific override applies | stg_weighing_event.event_time_local | lineage only |
| `event_time_utc` | timestamp_utc | DERIVED | yes | canonical UTC instant via Europe/Helsinki rules; NULL if unparseable, ambiguous or nonexistent | stg_weighing_event.event_time_canonical_utc | session span, weather join |
| `event_time_status` | text | DERIVED | no | OK, AMBIGUOUS, NONEXISTENT or UNPARSEABLE | stg_weighing_event.event_time_status | lineage only |
| `identification_time_raw` | text | OBSERVED | no | user_identification_time as written | stg_weighing_event.identification_time_raw | lineage only |
| `identification_time_local` | timestamp_local | DERIVED | yes | as event_time_local, for the identification time | stg_weighing_event.identification_time_local | lineage only |
| `identification_time_utc` | timestamp_utc | DERIVED | yes | as event_time_utc, for the identification time | stg_weighing_event.identification_time_canonical_utc | lineage only |
| `identification_time_status` | text | DERIVED | no | as event_time_status | stg_weighing_event.identification_time_status | lineage only |
| `timezone_handling` | text | DERIVED | no | SOURCE_LOCAL_ASSUMED or NORMALISED_PLUS_3H_STRONGEST_SUPPORT (one named file only); provenance, not a conclusion | stg_weighing_event.timezone_handling | timezone provenance |
| `timezone_offset_hours_applied` | integer | DERIVED | no | hours added by a file-specific override (0 elsewhere) | stg_weighing_event.timezone_offset_hours_applied | lineage only |
| `timezone_transformation_reason` | text | DERIVED | no | why the handling was applied, e.g. cross-export temporal alignment | stg_weighing_event.timezone_transformation_reason | lineage only |
| `disposition` | text | VALIDATION | no | MODELLABLE, DUPLICATE_EXCLUDED or QUARANTINED; every event has exactly one | validation event_validation_status.disposition | which events feed business fields |
| `is_modellable` | boolean | DERIVED | no | disposition = MODELLABLE | derived from disposition | session weight and components |
| `is_exact_duplicate` | boolean | VALIDATION | no | an exact repeat of an earlier row of the same file (rule I02) | disposition = DUPLICATE_EXCLUDED, or I02 on the row | lineage only |
| `quarantine_rule_ids` | text | VALIDATION | yes | rule ids that quarantined the row's session key (set only when disposition is QUARANTINED) | validation session_validation_status.quarantine_rule_ids | why a row is quarantined |
| `quality_status` | text | DERIVED | no | INVALID if the row has an ERROR finding or is quarantined, WARN if it has a WARN finding, else VALID | from validation rule ids | lineage only |
| `validation_error_rule_ids` | text | VALIDATION | yes | `;`-joined ERROR rule ids on this row | validation event_validation_status | lineage only |
| `validation_warn_rule_ids` | text | VALIDATION | yes | `;`-joined WARN rule ids on this row | validation event_validation_status | lineage only |
| `validation_info_rule_ids` | text | VALIDATION | yes | `;`-joined INFO rule ids on this row | validation event_validation_status | lineage only |

### fact_dining_session

**Grain:** one DERIVED session key (session_id, population). **Key:** `session_key`. 40 columns.

| Field | Type | Class | Null? | Meaning | Source lineage and rule | Used downstream |
|---|---|---|---|---|---|---|
| `session_key` | text | DERIVED | no | `session_id|population` | session_id + '|' + population | primary key |
| `session_id` | text | OBSERVED | no | source session identifier; also present in the other population for exactly two ids | grouping key | lineage only |
| `population` | text | DERIVED | no | source-derived label; never pooled | from the file name | lineage only |
| `is_primary_population` | boolean | DERIVED | no | population is registered_export (the primary population) | config/populations.yml role | metric filters |
| `source_snapshot_id` | text | PROVENANCE | no | raw snapshot the events came from | events' source_snapshot_id | lineage only |
| `source_files` | text | PROVENANCE | no | `;`-joined source files of the session's events | distinct source_file over its events | lineage only |
| `tray_id` | text | OBSERVED | yes | the one tray of the session; NULL if the events disagree (an I04 error) | distinct tray_id over non-repeat events | lineage only |
| `service_date` | date | DERIVED | yes | local date of the first weighing | date part of first_weighing_local | daily volume |
| `first_weighing_local` | timestamp_local | DERIVED | yes | local time of the earliest non-repeat event | event with the minimum UTC instant | lineage only |
| `first_weighing_utc` | timestamp_utc | DERIVED | yes | earliest non-repeat event, UTC | min event_time_utc over non-repeat events | weather join |
| `last_weighing_local` | timestamp_local | DERIVED | yes | local time of the latest non-repeat event | event with the maximum UTC instant | lineage only |
| `last_weighing_utc` | timestamp_utc | DERIVED | yes | latest non-repeat event, UTC | max event_time_utc over non-repeat events | lineage only |
| `identification_time_local` | timestamp_local | DERIVED | yes | the session's one identification time; NULL if there is not exactly one | distinct identification instants over non-repeat events | lineage only |
| `identification_time_utc` | timestamp_utc | DERIVED | yes | as above, UTC | as above | lineage only |
| `session_span_s` | integer | DERIVED | yes | last minus first weighing, seconds (diagnostic) | last_weighing_utc - first_weighing_utc | T05 context |
| `session_duration_minutes` | real | DERIVED | yes | session_span_s / 60 | session_span_s / 60 | lineage only |
| `event_count` | integer | DERIVED | no | every staged event of the key, whatever its disposition | count of events | lineage only |
| `modellable_event_count` | integer | DERIVED | no | events with disposition MODELLABLE | count where disposition = MODELLABLE | weight and components |
| `duplicate_excluded_event_count` | integer | DERIVED | no | events with disposition DUPLICATE_EXCLUDED | count where disposition = DUPLICATE_EXCLUDED | lineage only |
| `quarantined_event_count` | integer | DERIVED | no | events with disposition QUARANTINED | count where disposition = QUARANTINED | lineage only |
| `derived_selected_meal_weight_g` | integer | DERIVED | yes | DERIVED: sum of the weights the session's MODELLABLE events recorded on the line. NOT consumed quantity, NOT food waste, NOT actual intake. NULL for a quarantined session or if any modellable weight is invalid | sum(component_weight_g) over MODELLABLE events, reconstructed from fact_weighing_event | M1, M2 |
| `distinct_component_count` | integer | DERIVED | yes | distinct component_id_normalized among MODELLABLE events; NULL when the session has none | count distinct over MODELLABLE events | M4 |
| `distinct_raw_component_count` | integer | DERIVED | yes | distinct raw component names among MODELLABLE events (control for the normalisation property) | count distinct component_name_raw over MODELLABLE events | lineage only |
| `distinct_component_count_status` | text | DERIVED | no | READY_WITH_LIMITATION, or LIMITED where cross-export component identity is unstable on that scale and day (rule I07) | I07 findings matched to the session's scale-days | M4 caveat |
| `identity_conflict` | boolean | DERIVED | no | session_id occurs in both populations | session_id present under two populations | core_ready |
| `is_quarantined` | boolean | VALIDATION | no | the session key is quarantined by validation | all events QUARANTINED; equals the validation quarantine flag | lineage only |
| `quarantine_rule_ids` | text | VALIDATION | yes | rule ids that caused the quarantine | validation session_validation_status | lineage only |
| `core_ready` | boolean | DERIVED | no | primary population, not quarantined, at least one modellable event, no ERROR finding, valid weights and parsed times; weather, WARN rules and volume flags never enter it | the approved validation readiness contract; the metric itself is metrics | M1-M5 filter |
| `max_validation_severity` | text | VALIDATION | no | highest severity among the session's findings: ERROR, WARN, INFO or NONE | validation session_validation_status | lineage only |
| `validation_error_rule_ids` | text | VALIDATION | yes | `;`-joined ERROR rule ids | validation session_validation_status | lineage only |
| `validation_warn_rule_ids` | text | VALIDATION | yes | `;`-joined WARN rule ids | validation session_validation_status | lineage only |
| `has_session_warn` | boolean | VALIDATION | no | a session-level WARN (B04, B07, T04, T05, I06) | validation session_validation_status.session_level_warn | S2 canonical |
| `has_event_warn` | boolean | VALIDATION | no | an event-level WARN (B02, I02) | validation session_validation_status.event_level_warn | S2 diagnostic variant |
| `quality_status` | text | DERIVED | no | INVALID if quarantined or any ERROR finding, WARN if any WARN finding, else VALID | from validation rule ids | lineage only |
| `weather_hour_utc` | timestamp_utc | DERIVED | yes | first weighing in UTC, ceiled to the next full hour (an exact hour keeps itself): the FMI hour-ending observation that covers the meal | ceil_hour(first_weighing_utc) | weather context |
| `weather_fmisid` | integer | PROVENANCE | yes | FMI station of the joined observation | config weather fmisid, when matched | lineage only |
| `weather_join_status` | text | DERIVED | no | MATCHED, UNMATCHED_NO_OBSERVATION, NOT_ATTEMPTED_QUARANTINED, NO_TIMESTAMP or WEATHER_BLOCKED | join outcome; a session without weather stays valid | lineage only |
| `weather_matched` | boolean | DERIVED | no | a fact_weather row exists for weather_hour_utc | join_status = MATCHED | S1 |
| `weather_r_1h_null` | boolean | DERIVED | yes | the matched hour has a NULL r_1h (source NaN); NULL when not matched | fact_weather.r_1h_status | lineage only |
| `weather_ri_10min_null` | boolean | DERIVED | yes | the matched hour has a NULL ri_10min; NULL when not matched | fact_weather.ri_10min_status | lineage only |

### fact_session_component

**Grain:** one distinct normalised component within one session key (MODELLABLE events only). **Key:** `session_key, component_id_normalized`. 10 columns.

| Field | Type | Class | Null? | Meaning | Source lineage and rule | Used downstream |
|---|---|---|---|---|---|---|
| `session_key` | text | DERIVED | no | `session_id|population` | fact_dining_session key | lineage only |
| `session_id` | text | OBSERVED | no | source session identifier | grouping key | lineage only |
| `population` | text | DERIVED | no | source-derived label | from the file name | lineage only |
| `component_id_normalized` | text | DERIVED | no | trim, collapse whitespace, case-fold. No alias table; different dishes are never merged because their names look similar | from fact_weighing_event | M4 counts |
| `component_name_raw_variants` | text | OBSERVED | no | `|`-joined distinct raw spellings seen for it in this session | distinct component_name_raw, sorted | lineage only |
| `component_weighing_event_count` | integer | DERIVED | no | MODELLABLE events for the component (more than 1 means a repeat weighing or the same name on two scales) | count | lineage only |
| `scale_ids` | text | OBSERVED | no | `;`-joined sorted scales used | distinct scale_id, sorted | lineage only |
| `derived_component_weight_g` | integer | DERIVED | yes | sum of that component's event weights; NULL if any is invalid. Not a consumed quantity | sum(component_weight_g) | lineage only |
| `source_snapshot_id` | text | PROVENANCE | no | raw snapshot | events' source_snapshot_id | lineage only |
| `source_row_lineage` | text | PROVENANCE | no | `;`-joined event ids (`file#row`) that make up the row | event ids, sorted | lineage only |

### fact_weather

**Grain:** one FMI station x UTC hour observation (one column per requested parameter). **Key:** `fmisid, obs_time_utc`. 16 columns.

| Field | Type | Class | Null? | Meaning | Source lineage and rule | Used downstream |
|---|---|---|---|---|---|---|
| `fmisid` | integer | OBSERVED | no | FMI station identifier | stg_weather_observation.fmisid | join |
| `obs_time_utc` | timestamp_utc | OBSERVED | no | observation time as stated by FMI (UTC) | stg_weather_observation.obs_time_canonical_utc | join |
| `t2m_c` | real | OBSERVED | yes | air temperature at 2 m, degrees C, exactly as FMI states it; NULL when FMI reports NaN | stg value_raw for parameter t2m | context only |
| `ws_10min_ms` | real | OBSERVED | yes | 10-minute mean wind speed, m/s; NULL when NaN | parameter ws_10min | context only |
| `r_1h_mm` | real | OBSERVED | yes | precipitation over the HOUR ENDING at obs_time_utc, mm; NULL when NaN, never 0 | parameter r_1h | context only |
| `ri_10min_mmh` | real | OBSERVED | yes | 10-minute precipitation intensity, mm/h; NULL when NaN, never 0 | parameter ri_10min | context only |
| `t2m_status` | text | DERIVED | no | OK, NAN_SOURCE_NULL or MISSING (no row for that hour) | stg value_status | lineage only |
| `ws_10min_status` | text | DERIVED | no | as t2m_status | stg value_status | lineage only |
| `r_1h_status` | text | DERIVED | no | as t2m_status | stg value_status | lineage only |
| `ri_10min_status` | text | DERIVED | no | as t2m_status | stg value_status | lineage only |
| `is_null_any` | boolean | DERIVED | no | any of the four parameters is not OK | any status != OK | lineage only |
| `r_1h_convention` | text | DERIVED | no | states the approved reading of r_1h (hour ending at the timestamp) | config/sources.yml weather r_1h_convention | lineage only |
| `timezone_handling` | text | DERIVED | no | SOURCE_UTC_STATED: FMI states UTC | stg_weather_observation.timezone_handling | lineage only |
| `source_snapshot_id` | text | PROVENANCE | no | raw weather snapshot | stg_weather_observation.source_snapshot_id | lineage only |
| `source_files` | text | PROVENANCE | no | response file(s) the hour came from | distinct source_file | lineage only |
| `source_row_lineage` | text | PROVENANCE | no | `;`-joined observation ids (`file#element`) | observation ids, sorted | lineage only |

### fact_daily_volume

**Grain:** one service date x population. **Key:** `service_date, population`. 13 columns.

| Field | Type | Class | Null? | Meaning | Source lineage and rule | Used downstream |
|---|---|---|---|---|---|---|
| `service_date` | date | DERIVED | no | local service date | service_date of the sessions | flags |
| `population` | text | DERIVED | no | source-derived label; never pooled | session population | lineage only |
| `weekday` | text | DERIVED | no | English weekday name | from service_date | lineage only |
| `is_primary_population` | boolean | DERIVED | no | population is registered_export | config role | lineage only |
| `sessions` | integer | DERIVED | no | Observed Valid Sessions: session keys with a modellable event that are not quarantined. For the registered-export population this is M3's basis. It is an observation of the export, NOT demand | count of fact_dining_session rows | M3 |
| `quarantined_sessions` | integer | DERIVED | no | quarantined session keys whose first weighing falls on the day | count | lineage only |
| `events` | integer | DERIVED | no | modellable events of those sessions | sum modellable_event_count | lineage only |
| `observed_regime` | text | DERIVED | no | high if sessions >= 30 else low | config thresholds volume.high_regime_min_sessions | lineage only |
| `expected_regime` | text | DERIVED | yes | the weekday's baseline regime (Mon-Wed high, Thu-Fri low; baseline 2020-10-05..30); registered-export only | config thresholds volume.expected_regime_by_weekday | lineage only |
| `low_observed_volume_day` | boolean | DERIVED | no | C02a: sessions < 30; registered-export only; FLAG ONLY | rule C02a | lineage only |
| `volume_irregularity` | boolean | DERIVED | no | C02b: observed regime differs from the weekday baseline; registered-export only; FLAG ONLY; not a data error, never excluded | rule C02b | lineage only |
| `source_snapshot_id` | text | PROVENANCE | no | raw snapshot | sessions' source_snapshot_id | lineage only |
| `source_files` | text | PROVENANCE | no | `;`-joined source files of the day's sessions | distinct source_files | lineage only |


## 13. Metric outputs

Written to `outputs/metrics/` from the canonical model (all tracked; small). Contract, computation and presentation are separate (see `metric_contract.md` section 8).

| File | Grain | Content |
|---|---|---|
| `metrics.csv` | one metric | the metric id, name, role, value, display value, unit, population and its definition, grain, numerator, denominator, n used, n excluded against the fixed eligible population (1,699), formula, source tables, source snapshot, approved value, tolerance, status, evidence status, interpretation and limitation |
| `metric_evidence.csv` | one evidence row | Metric, Value, Population, Grain, What it tells us, What it does NOT tell us, records used, records excluded, evidence status |
| `metric_contracts.json` | one metric contract | every contract field plus the computed value, numerator, denominator, pass/fail and any problems |
| `metric_summary.json` | run | values, populations, controls, supporting detail (M3 by service date, M4 distribution), semantic chain, waste status |
| `metric_controls.csv` | one control | 24 cross-checks (PASS / FAIL / INFO): populations, weights against the event fact, independent statistics, components, volume, readiness accounting, weather, semantics |
| `metrics_report.md` | report | the evidence table, results, populations, why M5 and S2 differ, the W1 statement |

`status` is PASS, FAIL or BLOCKED. `evidence_status` is READY_WITH_LIMITATION or BLOCKED. `value` is empty for W1; there is no waste, consumption, leftover or intake column anywhere.


## 14. Sensitivity and evidence outputs

Written to `outputs/evidence/` (all tracked; small) by `python -m src.pipeline.run --stages sensitivity`. Definitions and thresholds: `sensitivity_analysis.md`, decisions D59-D63.

| File | Grain | Content |
|---|---|---|
| `scenario_registry.json` / `.csv` | one scenario | id, group, assumption changed, baseline and alternative assumption, rationale, affected tables and population, metrics recalculated, operation, interpretation, decision impact, defensible, diagnostic-only, forbidden |
| `sensitivity_results.csv` | one scenario | the metric values, deltas and percentage deltas, worst robustness class, whether the profiling reference reproduced |
| `metric_sensitivity.csv` | one metric x scenario | `metric_id, scenario_id, baseline_value, scenario_value, absolute_delta, relative_delta, population, interpretation, robustness_class` |
| `timezone_evidence.csv` | one candidate offset | sessions outside service hours, median first-event hour, gap to the other files, weather-hour changes, temperature difference, rainy-hour share |
| `evidence_matrix.csv` | one question | Question, Baseline evidence, Sensitivity tested, Observed range/change, Robustness, What can be concluded, What cannot be concluded, Next evidence needed |
| `uncertainty_register.csv` | one uncertainty | id, assumption, why it matters, current evidence, sensitivity result, impact level, affected metrics, current disposition, evidence that would resolve it |
| `sensitivity_summary.json`, `sensitivity_controls.csv` | run | baseline (frozen), ranges, largest changes, classification thresholds, conclusion classes, 13 controls |
| `figures/*.png` | figure | four sensitivity figures |

`robustness_class` is STABLE, SENSITIVE, CONDITIONAL, BLOCKED, or NOT_CLASSIFIED (the diagnostic population contrast S40 and the forbidden guardrail G01). There is no waste, consumption or leftover value in any file.

## 15. Pipeline outputs

Written to `outputs/pipeline/` by every `python -m src.pipeline.run`. Definitions and gates: `pipeline.md`, decisions D64-D68. Stage names are `ingest, stage, validate, model, metrics, sensitivity`; statuses are `PASSED, FAILED, BLOCKED, INVALIDATED, NOT_RUN, REUSED`.

| File | Grain | Content |
|---|---|---|
| `stage_summary.csv` | one stage | `stage, status, gate, exit_class, reason, warnings, errors, output_files, output_bytes, outputs_sha256, removed_outputs` (deterministic; tracked) |
| `pipeline_controls.csv` | one control | `control_id` P01-P11, `control`, `status` PASS/FAIL/INFO, `detail` (deterministic; tracked) |
| `run_manifest.json` | run | run id, pipeline version, started/finished, elapsed, target, resume point, exit code and meaning, weather flag, config fingerprint (per-file SHA-256), provenance (input fingerprint, snapshot ids, validation run id, 18 links), per-stage record with counts and output path/SHA-256/size (not tracked) |
| `runtime_summary.json` | run | total and per-stage seconds, output bytes, optional peak Python allocation (not tracked) |
| `run_log.jsonl` | event | `ts, run_id, event, stage, status` plus counts or reason (not tracked) |

## 16. Glossary (plain English)

The terms below are used in the README and the evidence table. Each states what it means, its grain, whether it is observed or derived, and what it does **not** mean.

| Term | Meaning | Grain | Observed / derived | Does NOT mean |
|---|---|---|---|---|
| **Weighing event** | A scale recorded a weight for one named component at one moment | one row of the source (12,284) | OBSERVED | a whole meal, or anything eaten |
| **Component** | One named item weighed on one scale (a dish or side). Counted within a session by its normalised name | one distinct component in one session | OBSERVED name, DERIVED count | a recipe, a dish identity that holds across days or exports |
| **Session** | The weighing events that share one `session_id` within one population: one tray pass through the weighed line | one row of `fact_dining_session` (3,345) | DERIVED (the source never states it) | a person, a whole visit, a purchase or a meal eaten |
| **Session key** | `(session_id, population)`. `session_id` alone is not enough because two IDs (`session2266`, `session3222`) occur in both exports | one session | DERIVED | a person identifier |
| **Population** | Which export a record came from, taken from the file-name prefix: registered-export (primary, the measurement population) or non-registered-export (diagnostic, never pooled) | one session | label inherited from file names | customer-registration status, or a business segment (the source does not define the labels) |
| **Derived selected meal weight** (`derived_selected_meal_weight_g`) | The sum of the observed component weighing events of a session, in grams, under our rule | one session | DERIVED from observed events | **consumed quantity, actual intake, food waste or leftover food** |
| **Core-ready** | A registered-export session that is not quarantined, has at least one valid event, no ERROR-level finding, valid weights and parsed times. The measurement population (1,697 of 1,699) | one session | DERIVED status | that the data is error-free, or that the session is typical |
| **Warn-free** | A core-ready session with no session-level WARN finding (S2, 1,663 of 1,699) | one session | DERIVED status | a second readiness score, or a claim that flagged sessions are wrong |
| **Quarantine** | A record kept in the model, flagged and listed, but excluded from the measurement population until the source owner resolves it (the two crossover sessions) | one session key | DERIVED status | deletion: quarantined records are never removed |
| **Observed volume** | The count of sessions observed on a service date in one population (`fact_daily_volume`, M3 for the measurement population) | one service date × population | DERIVED count of observed sessions | how many people came, or demand |
| **Weather observation** | One FMI reading (`t2m`, `ws_10min`, `r_1h`, `ri_10min`) for one hour at Turku Artukainen, joined to a session by the hour-ending observation | one station × one UTC hour | OBSERVED (by FMI) | on-site weather, or a cause of anything |
