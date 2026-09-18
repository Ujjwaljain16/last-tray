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
| `waste_weight_g` | real | **Always NULL in MVP** | food discarded | **SOURCE GAP**, never 0 |

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

## 10. Staging tables (WP3)

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


## 11. Validation tables (WP4)

Written to `outputs/validation/` from the verified staging tables. They are evidence about staging: they add findings, dispositions and
reconciliation, and they change no staged value. Field meanings for the issue table, the severity / handling / quarantine distinction
and the lineage bases are in `validation_rules.md` ("WP4 implementation").

| Table | Grain | Key fields |
|---|---|---|
| `validation_issues` | one finding on one entity | `validation_issue_id` (content-derived), `run_id`, `rule_id`, `severity`, `handling`, `quarantine`, `entity_type`, `entity_id`, `session_key`, `event_id`, `lineage_basis`, `source_row_lineage` |
| `event_validation_status` | one staged event | `event_id`, `disposition` (`MODELLABLE`, `DUPLICATE_EXCLUDED`, `QUARANTINED`), rule ids by severity |
| `session_validation_status` | one `(session_id, population)` key | counts, `service_date`, `span_s`, `rule_weight_sum_g` (validation working value; the canonical `derived_selected_meal_weight_g` is produced in WP5), `quarantined`, `session_level_warn`, `event_level_warn`, day flags |
| `quarantine_manifest` | one quarantined session key or event | `quarantine_entity_type`, `entity_id`, `quarantine_rule_ids` |
| `reconciliation_summary` | one check | `check_id`, `status` (PASS, WARN, FAIL, INFO), `expected`, `observed`, `basis` |
| `service_day_volume` | one population and service date | `sessions`, `observed_regime`, `expected_regime`, `low_observed_volume_day`, `volume_irregularity_day` (registered-export only) |
| `field_completeness` | one field | `empty_rows` (true missingness), `not_applicable_rows` (column absent from the source file), `malformed_rows` |

Dispositions: `QUARANTINED` (session key quarantined; wins over repeat), `DUPLICATE_EXCLUDED` (an exact repeat of an earlier row of
the same file, left out of sums), `MODELLABLE` (available to the model layer). Every staged event has exactly one.
