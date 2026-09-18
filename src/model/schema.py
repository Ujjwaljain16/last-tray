"""The canonical model schema: the single authority for every table, grain and column.

CSV headers, the model manifest and the data-dictionary text (docs/data_dictionary.md, section 12) are all produced from THIS file,
and a test fails if the documentation drifts from it. Nothing here is a business calculation; it only declares what each field is.

Semantic classes (see docs/data_dictionary.md):
  OBSERVED    written by a source system and carried through unchanged (raw text, weights, names, weather values)
  DERIVED     computed by this pipeline from observed values by a stated rule
  VALIDATION  consumed unchanged from the WP4 validation layer (dispositions, rule ids)
  PROVENANCE  identifies where a value came from (snapshot, artifact, file, row)
There is deliberately NO column for consumed quantity (UNKNOWN) or for food waste (SOURCE GAP).
"""
from __future__ import annotations

from dataclasses import dataclass

OBSERVED, DERIVED, VALIDATION, PROVENANCE = "OBSERVED", "DERIVED", "VALIDATION", "PROVENANCE"


@dataclass(frozen=True)
class Col:
    name: str
    dtype: str          # text | integer | real | boolean | date | timestamp_local | timestamp_utc
    cls: str
    nullable: bool
    meaning: str
    rule: str           # source lineage and transformation rule
    downstream: str


@dataclass(frozen=True)
class Table:
    name: str
    grain: str
    key: tuple[str, ...]
    columns: tuple[Col, ...]

    @property
    def column_names(self) -> tuple[str, ...]:
        return tuple(c.name for c in self.columns)


def C(name, dtype, cls, nullable, meaning, rule, downstream="") -> Col:
    return Col(name, dtype, cls, nullable, meaning, rule, downstream or "lineage only")


EVENT = Table("fact_weighing_event", "one observed component weighing event (one source data row)", ("event_id",), (
    C("event_id", "text", PROVENANCE, False, "source file and 1-based data-row number, `file#row`", "stg_weighing_event.event_id", "every join back to staging"),
    C("source_snapshot_id", "text", PROVENANCE, False, "content-derived id of the raw snapshot", "stg_weighing_event.source_snapshot_id"),
    C("raw_artifact_id", "text", PROVENANCE, False, "raw member identity inside the snapshot", "stg_weighing_event.raw_artifact_id"),
    C("source_file", "text", PROVENANCE, False, "source CSV member name", "stg_weighing_event.source_file"),
    C("source_row_number", "integer", PROVENANCE, False, "1-based data row within the file", "stg_weighing_event.source_row_number"),
    C("raw_row_sha256", "text", PROVENANCE, False, "SHA-256 of the raw row text", "stg_weighing_event.raw_row_sha256"),
    C("population", "text", DERIVED, False, "registered_export or non_registered_export, from the file name; a source label, not a semantic claim", "config/populations.yml prefix rule, via staging", "every population split"),
    C("session_id", "text", OBSERVED, False, "source session identifier", "stg_weighing_event.session_id", "session grouping"),
    C("session_key", "text", DERIVED, False, "`session_id|population`; the two populations are never merged", "session_id + '|' + population", "session join"),
    C("tray_id", "text", OBSERVED, False, "source tray identifier (not a person)", "stg_weighing_event.tray_id"),
    C("scale_id", "text", OBSERVED, False, "source scale identifier", "stg_weighing_event.scale_id", "component-scale lineage"),
    C("station_family", "text", DERIVED, True, "first '-' separated part of scale_id", "split scale_id on '-'"),
    C("component_name_raw", "text", OBSERVED, False, "component name exactly as in the source, whitespace included", "stg_weighing_event.component_name_raw", "raw-vs-normalised check"),
    C("component_id_normalized", "text", DERIVED, True, "trim, collapse whitespace, case-fold; NULL if empty. No alias table, no fuzzy matching", "stg_weighing_event.component_id_normalized", "distinct component counts"),
    C("weight_raw", "text", OBSERVED, False, "weight text exactly as in the source", "stg_weighing_event.weight_raw"),
    C("component_weight_g", "integer", OBSERVED, True, "weight in grams parsed from weight_raw; NULL if not an integer; never clipped", "stg_weighing_event.component_weight_g", "derived_selected_meal_weight_g"),
    C("weight_status", "text", DERIVED, False, "OK, NOT_INTEGER or EMPTY", "stg_weighing_event.weight_parse_status", "weight validity"),
    C("weighing_type", "text", OBSERVED, True, "source weighting_type; NULL where the file has no such column (not applicable, not missing)", "stg_weighing_event.weighing_type"),
    C("event_time_raw", "text", OBSERVED, False, "weighing time exactly as written in the source", "stg_weighing_event.event_time_raw", "timezone provenance"),
    C("event_time_local", "timestamp_local", DERIVED, True, "wall time as read (Europe/Helsinki), plus the offset only where a file-specific override applies", "stg_weighing_event.event_time_local"),
    C("event_time_utc", "timestamp_utc", DERIVED, True, "canonical UTC instant via Europe/Helsinki rules; NULL if unparseable, ambiguous or nonexistent", "stg_weighing_event.event_time_canonical_utc", "session span, weather join"),
    C("event_time_status", "text", DERIVED, False, "OK, AMBIGUOUS, NONEXISTENT or UNPARSEABLE", "stg_weighing_event.event_time_status"),
    C("identification_time_raw", "text", OBSERVED, False, "user_identification_time as written", "stg_weighing_event.identification_time_raw"),
    C("identification_time_local", "timestamp_local", DERIVED, True, "as event_time_local, for the identification time", "stg_weighing_event.identification_time_local"),
    C("identification_time_utc", "timestamp_utc", DERIVED, True, "as event_time_utc, for the identification time", "stg_weighing_event.identification_time_canonical_utc"),
    C("identification_time_status", "text", DERIVED, False, "as event_time_status", "stg_weighing_event.identification_time_status"),
    C("timezone_handling", "text", DERIVED, False, "SOURCE_LOCAL_ASSUMED or NORMALISED_PLUS_3H_STRONGEST_SUPPORT (one named file only); provenance, not a conclusion", "stg_weighing_event.timezone_handling", "timezone provenance"),
    C("timezone_offset_hours_applied", "integer", DERIVED, False, "hours added by a file-specific override (0 elsewhere)", "stg_weighing_event.timezone_offset_hours_applied"),
    C("timezone_transformation_reason", "text", DERIVED, False, "why the handling was applied, e.g. cross-export temporal alignment", "stg_weighing_event.timezone_transformation_reason"),
    C("disposition", "text", VALIDATION, False, "MODELLABLE, DUPLICATE_EXCLUDED or QUARANTINED; every event has exactly one", "validation event_validation_status.disposition", "which events feed business fields"),
    C("is_modellable", "boolean", DERIVED, False, "disposition = MODELLABLE", "derived from disposition", "session weight and components"),
    C("is_exact_duplicate", "boolean", VALIDATION, False, "an exact repeat of an earlier row of the same file (rule I02)", "disposition = DUPLICATE_EXCLUDED, or I02 on the row"),
    C("quarantine_rule_ids", "text", VALIDATION, True, "rule ids that quarantined the row's session key (set only when disposition is QUARANTINED)", "validation session_validation_status.quarantine_rule_ids", "why a row is quarantined"),
    C("quality_status", "text", DERIVED, False, "INVALID if the row has an ERROR finding or is quarantined, WARN if it has a WARN finding, else VALID", "from validation rule ids"),
    C("validation_error_rule_ids", "text", VALIDATION, True, "`;`-joined ERROR rule ids on this row", "validation event_validation_status"),
    C("validation_warn_rule_ids", "text", VALIDATION, True, "`;`-joined WARN rule ids on this row", "validation event_validation_status"),
    C("validation_info_rule_ids", "text", VALIDATION, True, "`;`-joined INFO rule ids on this row", "validation event_validation_status"),
))

SESSION = Table("fact_dining_session", "one DERIVED session key (session_id, population)", ("session_key",), (
    C("session_key", "text", DERIVED, False, "`session_id|population`", "session_id + '|' + population", "primary key"),
    C("session_id", "text", OBSERVED, False, "source session identifier; also present in the other population for exactly two ids", "grouping key"),
    C("population", "text", DERIVED, False, "source-derived label; never pooled", "from the file name"),
    C("is_primary_population", "boolean", DERIVED, False, "population is registered_export (the primary population)", "config/populations.yml role", "metric filters"),
    C("source_snapshot_id", "text", PROVENANCE, False, "raw snapshot the events came from", "events' source_snapshot_id"),
    C("source_files", "text", PROVENANCE, False, "`;`-joined source files of the session's events", "distinct source_file over its events"),
    C("tray_id", "text", OBSERVED, True, "the one tray of the session; NULL if the events disagree (an I04 error)", "distinct tray_id over non-repeat events"),
    C("service_date", "date", DERIVED, True, "local date of the first weighing", "date part of first_weighing_local", "daily volume"),
    C("first_weighing_local", "timestamp_local", DERIVED, True, "local time of the earliest non-repeat event", "event with the minimum UTC instant"),
    C("first_weighing_utc", "timestamp_utc", DERIVED, True, "earliest non-repeat event, UTC", "min event_time_utc over non-repeat events", "weather join"),
    C("last_weighing_local", "timestamp_local", DERIVED, True, "local time of the latest non-repeat event", "event with the maximum UTC instant"),
    C("last_weighing_utc", "timestamp_utc", DERIVED, True, "latest non-repeat event, UTC", "max event_time_utc over non-repeat events"),
    C("identification_time_local", "timestamp_local", DERIVED, True, "the session's one identification time; NULL if there is not exactly one", "distinct identification instants over non-repeat events"),
    C("identification_time_utc", "timestamp_utc", DERIVED, True, "as above, UTC", "as above"),
    C("session_span_s", "integer", DERIVED, True, "last minus first weighing, seconds (diagnostic)", "last_weighing_utc - first_weighing_utc", "T05 context"),
    C("session_duration_minutes", "real", DERIVED, True, "session_span_s / 60", "session_span_s / 60"),
    C("event_count", "integer", DERIVED, False, "every staged event of the key, whatever its disposition", "count of events"),
    C("modellable_event_count", "integer", DERIVED, False, "events with disposition MODELLABLE", "count where disposition = MODELLABLE", "weight and components"),
    C("duplicate_excluded_event_count", "integer", DERIVED, False, "events with disposition DUPLICATE_EXCLUDED", "count where disposition = DUPLICATE_EXCLUDED"),
    C("quarantined_event_count", "integer", DERIVED, False, "events with disposition QUARANTINED", "count where disposition = QUARANTINED"),
    C("derived_selected_meal_weight_g", "integer", DERIVED, True, "DERIVED: sum of the weights the session's MODELLABLE events recorded on the line. NOT consumed quantity, NOT food waste, NOT actual intake. NULL for a quarantined session or if any modellable weight is invalid", "sum(component_weight_g) over MODELLABLE events, reconstructed from fact_weighing_event", "M1, M2"),
    C("distinct_component_count", "integer", DERIVED, True, "distinct component_id_normalized among MODELLABLE events; NULL when the session has none", "count distinct over MODELLABLE events", "M4"),
    C("distinct_raw_component_count", "integer", DERIVED, True, "distinct raw component names among MODELLABLE events (control for the normalisation property)", "count distinct component_name_raw over MODELLABLE events"),
    C("distinct_component_count_status", "text", DERIVED, False, "READY_WITH_LIMITATION, or LIMITED where cross-export component identity is unstable on that scale and day (rule I07)", "I07 findings matched to the session's scale-days", "M4 caveat"),
    C("identity_conflict", "boolean", DERIVED, False, "session_id occurs in both populations", "session_id present under two populations", "core_ready"),
    C("is_quarantined", "boolean", VALIDATION, False, "the session key is quarantined by WP4", "all events QUARANTINED; equals the WP4 quarantine flag"),
    C("quarantine_rule_ids", "text", VALIDATION, True, "rule ids that caused the quarantine", "validation session_validation_status"),
    C("core_ready", "boolean", DERIVED, False, "primary population, not quarantined, at least one modellable event, no ERROR finding, valid weights and parsed times; weather, WARN rules and volume flags never enter it", "the approved WP4 readiness contract; the metric itself is WP6", "M1-M5 filter"),
    C("max_validation_severity", "text", VALIDATION, False, "highest severity among the session's findings: ERROR, WARN, INFO or NONE", "validation session_validation_status"),
    C("validation_error_rule_ids", "text", VALIDATION, True, "`;`-joined ERROR rule ids", "validation session_validation_status"),
    C("validation_warn_rule_ids", "text", VALIDATION, True, "`;`-joined WARN rule ids", "validation session_validation_status"),
    C("has_session_warn", "boolean", VALIDATION, False, "a session-level WARN (B04, B07, T04, T05, I06)", "validation session_validation_status.session_level_warn", "S2 canonical"),
    C("has_event_warn", "boolean", VALIDATION, False, "an event-level WARN (B02, I02)", "validation session_validation_status.event_level_warn", "S2 diagnostic variant"),
    C("quality_status", "text", DERIVED, False, "INVALID if quarantined or any ERROR finding, WARN if any WARN finding, else VALID", "from validation rule ids"),
    C("weather_hour_utc", "timestamp_utc", DERIVED, True, "first weighing in UTC, ceiled to the next full hour (an exact hour keeps itself): the FMI hour-ending observation that covers the meal", "ceil_hour(first_weighing_utc)", "weather context"),
    C("weather_fmisid", "integer", PROVENANCE, True, "FMI station of the joined observation", "config weather fmisid, when matched"),
    C("weather_join_status", "text", DERIVED, False, "MATCHED, UNMATCHED_NO_OBSERVATION, NOT_ATTEMPTED_QUARANTINED, NO_TIMESTAMP or WEATHER_BLOCKED", "join outcome; a session without weather stays valid"),
    C("weather_matched", "boolean", DERIVED, False, "a fact_weather row exists for weather_hour_utc", "join_status = MATCHED", "S1"),
    C("weather_r_1h_null", "boolean", DERIVED, True, "the matched hour has a NULL r_1h (source NaN); NULL when not matched", "fact_weather.r_1h_status"),
    C("weather_ri_10min_null", "boolean", DERIVED, True, "the matched hour has a NULL ri_10min; NULL when not matched", "fact_weather.ri_10min_status"),
))

COMPONENT = Table("fact_session_component", "one distinct normalised component within one session key (MODELLABLE events only)", ("session_key", "component_id_normalized"), (
    C("session_key", "text", DERIVED, False, "`session_id|population`", "fact_dining_session key"),
    C("session_id", "text", OBSERVED, False, "source session identifier", "grouping key"),
    C("population", "text", DERIVED, False, "source-derived label", "from the file name"),
    C("component_id_normalized", "text", DERIVED, False, "trim, collapse whitespace, case-fold. No alias table; different dishes are never merged because their names look similar", "from fact_weighing_event", "M4 counts"),
    C("component_name_raw_variants", "text", OBSERVED, False, "`|`-joined distinct raw spellings seen for it in this session", "distinct component_name_raw, sorted"),
    C("component_weighing_event_count", "integer", DERIVED, False, "MODELLABLE events for the component (more than 1 means a repeat weighing or the same name on two scales)", "count"),
    C("scale_ids", "text", OBSERVED, False, "`;`-joined sorted scales used", "distinct scale_id, sorted"),
    C("derived_component_weight_g", "integer", DERIVED, True, "sum of that component's event weights; NULL if any is invalid. Not a consumed quantity", "sum(component_weight_g)"),
    C("source_snapshot_id", "text", PROVENANCE, False, "raw snapshot", "events' source_snapshot_id"),
    C("source_row_lineage", "text", PROVENANCE, False, "`;`-joined event ids (`file#row`) that make up the row", "event ids, sorted"),
))

WEATHER = Table("fact_weather", "one FMI station x UTC hour observation (one column per requested parameter)", ("fmisid", "obs_time_utc"), (
    C("fmisid", "integer", OBSERVED, False, "FMI station identifier", "stg_weather_observation.fmisid", "join"),
    C("obs_time_utc", "timestamp_utc", OBSERVED, False, "observation time as stated by FMI (UTC)", "stg_weather_observation.obs_time_canonical_utc", "join"),
    C("t2m_c", "real", OBSERVED, True, "air temperature at 2 m, degrees C, exactly as FMI states it; NULL when FMI reports NaN", "stg value_raw for parameter t2m", "context only"),
    C("ws_10min_ms", "real", OBSERVED, True, "10-minute mean wind speed, m/s; NULL when NaN", "parameter ws_10min", "context only"),
    C("r_1h_mm", "real", OBSERVED, True, "precipitation over the HOUR ENDING at obs_time_utc, mm; NULL when NaN, never 0", "parameter r_1h", "context only"),
    C("ri_10min_mmh", "real", OBSERVED, True, "10-minute precipitation intensity, mm/h; NULL when NaN, never 0", "parameter ri_10min", "context only"),
    C("t2m_status", "text", DERIVED, False, "OK, NAN_SOURCE_NULL or MISSING (no row for that hour)", "stg value_status"),
    C("ws_10min_status", "text", DERIVED, False, "as t2m_status", "stg value_status"),
    C("r_1h_status", "text", DERIVED, False, "as t2m_status", "stg value_status"),
    C("ri_10min_status", "text", DERIVED, False, "as t2m_status", "stg value_status"),
    C("is_null_any", "boolean", DERIVED, False, "any of the four parameters is not OK", "any status != OK"),
    C("r_1h_convention", "text", DERIVED, False, "states the approved reading of r_1h (hour ending at the timestamp)", "config/sources.yml weather r_1h_convention"),
    C("timezone_handling", "text", DERIVED, False, "SOURCE_UTC_STATED: FMI states UTC", "stg_weather_observation.timezone_handling"),
    C("source_snapshot_id", "text", PROVENANCE, False, "raw weather snapshot", "stg_weather_observation.source_snapshot_id"),
    C("source_files", "text", PROVENANCE, False, "response file(s) the hour came from", "distinct source_file"),
    C("source_row_lineage", "text", PROVENANCE, False, "`;`-joined observation ids (`file#element`)", "observation ids, sorted"),
))

VOLUME = Table("fact_daily_volume", "one service date x population", ("service_date", "population"), (
    C("service_date", "date", DERIVED, False, "local service date", "service_date of the sessions", "flags"),
    C("population", "text", DERIVED, False, "source-derived label; never pooled", "session population"),
    C("weekday", "text", DERIVED, False, "English weekday name", "from service_date"),
    C("is_primary_population", "boolean", DERIVED, False, "population is registered_export", "config role"),
    C("sessions", "integer", DERIVED, False, "Observed Valid Sessions: session keys with a modellable event that are not quarantined. For the registered-export population this is M3's basis. It is an observation of the export, NOT demand", "count of fact_dining_session rows", "M3"),
    C("quarantined_sessions", "integer", DERIVED, False, "quarantined session keys whose first weighing falls on the day", "count"),
    C("events", "integer", DERIVED, False, "modellable events of those sessions", "sum modellable_event_count"),
    C("observed_regime", "text", DERIVED, False, "high if sessions >= 30 else low", "config thresholds volume.high_regime_min_sessions"),
    C("expected_regime", "text", DERIVED, True, "the weekday's baseline regime (Mon-Wed high, Thu-Fri low; baseline 2020-10-05..30); registered-export only", "config thresholds volume.expected_regime_by_weekday"),
    C("low_observed_volume_day", "boolean", DERIVED, False, "C02a: sessions < 30; registered-export only; FLAG ONLY", "rule C02a"),
    C("volume_irregularity", "boolean", DERIVED, False, "C02b: observed regime differs from the weekday baseline; registered-export only; FLAG ONLY; not a data error, never excluded", "rule C02b"),
    C("source_snapshot_id", "text", PROVENANCE, False, "raw snapshot", "sessions' source_snapshot_id"),
    C("source_files", "text", PROVENANCE, False, "`;`-joined source files of the day's sessions", "distinct source_files"),
))

TABLES = (EVENT, SESSION, COMPONENT, WEATHER, VOLUME)
BY_NAME = {t.name: t for t in TABLES}


def render_markdown() -> str:
    """The data-dictionary section for the canonical model, generated from the declarations above."""
    out: list[str] = []
    for t in TABLES:
        out += [f"### {t.name}", "", f"**Grain:** {t.grain}. **Key:** `{', '.join(t.key)}`. {len(t.columns)} columns.", "",
                "| Field | Type | Class | Null? | Meaning | Source lineage and rule | Used downstream |", "|---|---|---|---|---|---|---|"]
        for c in t.columns:
            out.append(f"| `{c.name}` | {c.dtype} | {c.cls} | {'yes' if c.nullable else 'no'} | {c.meaning} | {c.rule} | {c.downstream} |")
        out.append("")
    return "\n".join(out)


if __name__ == "__main__":
    print(render_markdown())
