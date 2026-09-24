"""Configuration encodes approved decisions. These tests fail if a decision is changed by accident."""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from src.config import ConfigError, env_path, load_config
from src.vocab import Handling, Population, Severity, TimezoneNormalization

MANDATED_TZ_STATEMENT = (
    "A +3 hour normalization is the strongest-supported engineering decision based on cross-export temporal "
    "consistency checks; the original source does not explicitly confirm the timezone metadata."
)


def flat(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


class TestEnvPath:
    def test_the_environment_variable_is_used_when_set(self, monkeypatch):
        monkeypatch.setenv("LAST_TRAY_TEST_VAR", "/somewhere/else")
        assert env_path("LAST_TRAY_TEST_VAR", Path("/default")) == Path("/somewhere/else")

    def test_the_default_is_used_when_the_variable_is_unset(self, monkeypatch):
        monkeypatch.delenv("LAST_TRAY_TEST_VAR", raising=False)
        assert env_path("LAST_TRAY_TEST_VAR", Path("/default")) == Path("/default")

    def test_an_empty_environment_variable_is_treated_as_unset(self, monkeypatch):
        monkeypatch.setenv("LAST_TRAY_TEST_VAR", "")
        assert env_path("LAST_TRAY_TEST_VAR", Path("/default")) == Path("/default")


# ---- thresholds: the approved values, exactly ----------------------------------------------------------------------
class TestApprovedThresholds:
    def test_b02_large_event_weight(self, cfg):
        r = cfg.thresholds.rules["B02"]
        assert (r.operator, r.value, r.severity, r.handling) == (">=", 1500, Severity.WARN, Handling.FLAG)

    def test_b07_session_weight_bounds(self, cfg):
        r = cfg.thresholds.rules["B07"]
        assert (r.low, r.high, r.severity) == (50, 2200, Severity.WARN)

    def test_t05_session_span(self, cfg):
        r = cfg.thresholds.rules["T05"]
        assert (r.operator, r.value, r.severity) == (">", 600, Severity.WARN)

    def test_t07_first_event_hour_band(self, cfg):
        r = cfg.thresholds.rules["T07"]
        assert (r.low, r.high) == (pytest.approx(10.0), pytest.approx(11.0))   # floats compared with tolerance: representation is not a business rule
        assert r.severity == Severity.WARN

    def test_c02_low_volume(self, cfg):
        r = cfg.thresholds.rules["C02a"]
        assert (r.operator, r.value) == ("<", 30)
        assert cfg.thresholds.volume.high_regime_min_sessions == 30

    def test_weekday_baseline_regime(self, cfg):
        assert cfg.thresholds.volume.expected_regime_by_weekday == {
            "Monday": "high", "Tuesday": "high", "Wednesday": "high", "Thursday": "low", "Friday": "low"}

    def test_thresholds_are_declared_diagnostic_not_physical(self, cfg):
        assert "not claims of physical impossibility" in flat(cfg.thresholds.statement)

    def test_only_service_hours_can_remove_a_record(self, cfg):
        """WARN and INFO thresholds flag; they never quarantine. Only T03 (ERROR) does."""
        for rid, r in cfg.thresholds.rules.items():
            if r.severity is Severity.ERROR:
                assert rid == "T03" and r.handling is Handling.QUARANTINE
            else:
                assert r.handling is Handling.FLAG, f"{rid} is {r.severity.value} but handled as {r.handling.value}"

    def test_volume_flags_can_never_exclude(self, cfg):
        assert cfg.thresholds.volume.flag_only is True
        assert cfg.thresholds.rules["C02a"].handling is Handling.FLAG
        assert cfg.thresholds.rules["C02b"].handling is Handling.FLAG
        assert cfg.thresholds.rules["C02b"].severity is Severity.WARN


# ---- timezone -----------------------------------------------------------------------------------------------------------
class TestTimezone:
    def test_exactly_one_override_of_plus_three_hours(self, cfg):
        assert list(cfg.timezone.overrides) == ["registered_2020_10_05-2020_10_18.csv"]
        o = cfg.timezone.overrides["registered_2020_10_05-2020_10_18.csv"]
        assert o.offset_hours == 3
        assert o.label is TimezoneNormalization.NORMALISED_PLUS_3H_STRONGEST_SUPPORT

    def test_never_claimed_as_source_confirmed(self, cfg):
        assert all(o.source_confirmed is False for o in cfg.timezone.overrides.values())

    def test_mandated_wording(self, cfg):
        assert flat(cfg.timezone.statement) == MANDATED_TZ_STATEMENT

    def test_default_is_local_time_assumed(self, cfg):
        assert cfg.timezone.default_assume == "Europe/Helsinki"
        assert cfg.timezone.default_label is TimezoneNormalization.SOURCE_LOCAL_ASSUMED

    def test_both_time_columns_are_normalised(self, cfg):
        o = cfg.timezone.overrides["registered_2020_10_05-2020_10_18.csv"]
        assert set(o.applies_to_columns) == {"weighing_event_time", "user_identification_time"}

    def test_tray_collision_test_is_not_cited_as_evidence(self, repo):
        """It was uninformative (0 collisions at every offset). The config may mention it only as NOT evidence."""
        text = (repo / "config" / "timezone_overrides.yml").read_text(encoding="utf-8")
        for m in re.finditer(r"tray[- ]collision", text, flags=re.I):
            context = text[max(0, m.start() - 120): m.end() + 120].lower()
            assert "not evidence" in context or "uninformative" in context


# ---- populations --------------------------------------------------------------------------------------------------------
class TestPopulations:
    def test_source_derived_labels(self, cfg):
        names = {r.code: r.display_name for r in cfg.populations.rules}
        assert names == {Population.REGISTERED_EXPORT: "registered-export population",
                         Population.NON_REGISTERED_EXPORT: "non-registered-export population"}

    def test_registered_export_is_primary_and_the_other_is_diagnostic(self, cfg):
        roles = {r.code: r.role for r in cfg.populations.rules}
        assert roles == {Population.REGISTERED_EXPORT: "primary", Population.NON_REGISTERED_EXPORT: "diagnostic"}
        assert cfg.populations.primary.code is Population.REGISTERED_EXPORT

    def test_never_pooled(self, cfg):
        assert cfg.populations.never_pooled is True

    def test_labels_stated_as_inherited_from_filenames(self, cfg):
        s = flat(cfg.populations.statement)
        assert "inherited from source filenames" in s and "not customer-registration status" in s

    def test_every_archive_member_maps_to_exactly_one_population(self, cfg):
        counts = {Population.REGISTERED_EXPORT: 0, Population.NON_REGISTERED_EXPORT: 0}
        for m in cfg.sources.flavoria.members:
            counts[cfg.populations.population_for_filename(m.file)] += 1
        assert counts == {Population.REGISTERED_EXPORT: 6, Population.NON_REGISTERED_EXPORT: 5}

    def test_unrecognised_filename_is_rejected_not_guessed(self, cfg):
        with pytest.raises(ConfigError):
            cfg.populations.population_for_filename("mystery_2020-10-05.csv")

    def test_no_semantic_inflation_in_config_or_code(self, cfg, repo):
        """'registered diners/customers/users/meals' assert a meaning the source does not establish."""
        banned = cfg.populations.forbidden_phrases
        assert banned, "the forbidden phrase list must not be empty"
        files = [p for p in (repo / "config").glob("*.yml") if p.name != "populations.yml"]
        files += list((repo / "src").rglob("*.py"))
        for p in files:
            text = p.read_text(encoding="utf-8").lower()
            for phrase in banned:
                assert phrase not in text, f"{p.relative_to(repo)} contains {phrase!r}"


# ---- sources ------------------------------------------------------------------------------------------------------------
class TestSources:
    def test_flavoria_pins(self, cfg):
        f = cfg.sources.flavoria
        assert len(f.members) == 11
        assert sum(m.rows for m in f.members) == f.expected_total_rows == 12284
        assert f.expected_session_ids == 3343
        assert f.archive_md5 == "74410f922287ceffbd8092d7dd4e5530"       # as published by Zenodo
        assert f.archive_size_bytes == 1277440
        assert f.license == "CC-BY-4.0" and "10.5281/zenodo.5850856" in f.attribution

    def test_seven_of_eleven_files_lack_weighting_type(self, cfg):
        members = cfg.sources.flavoria.members
        assert sum(1 for m in members if not m.weighting_type) == 7
        assert "weighting_type" not in cfg.sources.flavoria.required_columns
        assert "weighting_type" in cfg.sources.flavoria.optional_columns

    def test_required_columns_are_by_name(self, cfg):
        assert set(cfg.sources.flavoria.required_columns) == {
            "session_id", "weighing_event_time", "scale_identifier", "weight_of_a_component",
            "component_name", "tray_id", "user_identification_time"}

    def test_weather_window_yields_expected_hours(self, cfg):
        w = cfg.sources.weather
        start = datetime.strptime(w.window_start, "%Y-%m-%dT%H:%M:%SZ")
        end = datetime.strptime(w.window_end, "%Y-%m-%dT%H:%M:%SZ")
        assert int((end - start) / timedelta(hours=1)) + 1 == w.expected_hours == 1129

    def test_weather_requests_respect_the_server_limit(self, cfg):
        w = cfg.sources.weather
        assert w.max_hours_per_request == 168 and w.chunk_hours <= 168
        assert len(w.raw_files) == 7

    def test_hour_ending_convention(self, cfg):
        assert cfg.sources.weather.r_1h_convention == "hour_ending"

    def test_weather_station_and_parameters(self, cfg):
        w = cfg.sources.weather
        assert w.fmisid == 100949
        assert set(w.request["parameters"]) == {"t2m", "ws_10min", "r_1h", "ri_10min"}

    def test_retry_is_bounded(self, cfg):
        r = cfg.sources.weather.retry
        assert 1 <= r.max_attempts <= 10 and r.backoff_base_seconds > 0 and r.timeout_seconds > 0

    def test_waste_is_a_blocked_source_gap_with_a_stated_remedy(self, cfg):
        g = cfg.sources.gaps["waste"]
        assert g.status == "BLOCKED"
        assert "TODO, Ask!" in g.evidence
        assert "tray_id" in g.required_extract       # what integration closes the gap
        assert not hasattr(cfg.sources.flavoria, "waste"), "waste must never be a Flavoria ingest field"


# ---- configuration refuses to change an approved decision silently ---------------------------------------------------------
class TestConfigRefusesDishonestEdits:
    def test_source_confirmed_true_is_rejected(self, config_copy):
        config_copy.edit("timezone_overrides.yml", "source_confirmed: false", "source_confirmed: true")
        with pytest.raises(ConfigError, match="source_confirmed must be false"):
            load_config(config_copy.dir)

    def test_volume_flags_that_exclude_are_rejected(self, config_copy):
        config_copy.edit("thresholds.yml", "flag_only: true", "flag_only: false")
        with pytest.raises(ConfigError, match="flag_only"):
            load_config(config_copy.dir)

    def test_pooling_populations_is_rejected(self, config_copy):
        config_copy.edit("populations.yml", "never_pooled: true", "never_pooled: false")
        with pytest.raises(ConfigError, match="never_pooled"):
            load_config(config_copy.dir)

    def test_unblocking_waste_is_rejected(self, config_copy):
        config_copy.edit("sources.yml", "    status: BLOCKED\n    evidence: 'Documentation sample", "    status: RESTRICTED\n    evidence: 'Documentation sample")
        with pytest.raises(ConfigError, match="waste source must be present and BLOCKED"):
            load_config(config_copy.dir)

    def test_threshold_statement_must_disclaim_physical_claims(self, config_copy):
        config_copy.edit("thresholds.yml", "They are not claims of\n  physical impossibility or universal abnormality.", "They are physical limits.")
        with pytest.raises(ConfigError, match="physical impossibility"):
            load_config(config_copy.dir)

    def test_inverted_bounds_are_rejected(self, config_copy):
        config_copy.edit("thresholds.yml", "    low: 50\n    high: 2200", "    low: 2200\n    high: 50")
        with pytest.raises(ConfigError, match="must be below"):
            load_config(config_copy.dir)

    def test_unknown_severity_is_rejected(self, config_copy):
        config_copy.edit("thresholds.yml", "severity: ERROR", "severity: CRITICAL")
        with pytest.raises(ConfigError, match="not one of"):
            load_config(config_copy.dir)

    def test_chunk_larger_than_server_limit_is_rejected(self, config_copy):
        config_copy.edit("sources.yml", "chunk_hours: 167", "chunk_hours: 200")
        with pytest.raises(ConfigError, match="exceeds the server limit"):
            load_config(config_copy.dir)

    def test_row_pin_mismatch_is_rejected(self, config_copy):
        config_copy.edit("sources.yml", "expected_total_rows: 12284", "expected_total_rows: 12000")
        with pytest.raises(ConfigError, match="expected_total_rows"):
            load_config(config_copy.dir)

    def test_override_for_a_file_not_in_the_archive_is_rejected(self, config_copy):
        config_copy.edit("timezone_overrides.yml", "registered_2020_10_05-2020_10_18.csv:\n    scope: file_specific", "registered_typo.csv:\n    scope: file_specific")
        with pytest.raises(ConfigError, match="not a member of the Flavoria archive"):
            load_config(config_copy.dir)

    def test_hour_starting_precipitation_convention_is_rejected(self, config_copy):
        config_copy.edit("sources.yml", "r_1h_convention: hour_ending", "r_1h_convention: hour_starting")
        with pytest.raises(ConfigError, match="hour_ending"):
            load_config(config_copy.dir)

    def test_missing_file_is_reported_by_name(self, config_copy):
        (config_copy.dir / "thresholds.yml").unlink()
        with pytest.raises(ConfigError, match="thresholds.yml"):
            load_config(config_copy.dir)

    def test_malformed_yaml_is_reported_not_swallowed(self, config_copy):
        (config_copy.dir / "populations.yml").write_text("populations: [unclosed", encoding="utf-8")
        with pytest.raises(ConfigError, match="not valid YAML"):
            load_config(config_copy.dir)


# ---- ingestion pins: everything ingestion verifies must be pinned, and pinned precisely ---------------------------------------------------
class TestIngestionPins:
    def test_every_member_is_pinned_by_sha256(self, cfg):
        shas = [m.sha256 for m in cfg.sources.flavoria.members]
        assert len(shas) == 11 and len(set(shas)) == 11 and all(re.fullmatch(r"[0-9a-f]{64}", h) for h in shas)

    def test_both_header_variants_are_pinned_and_distinct(self, cfg):
        from src.ingest.schema import fingerprint
        v = cfg.sources.flavoria.schema_variants
        assert set(v) == {"V8_with_weighting_type", "V7_without_weighting_type"}
        assert fingerprint(v["V8_with_weighting_type"]) != fingerprint(v["V7_without_weighting_type"])
        assert len(v["V8_with_weighting_type"]) == 12 and len(v["V7_without_weighting_type"]) == 11     # named columns + 4 trailing blanks

    def test_weather_chunks_are_pinned_by_bytes_and_by_content(self, cfg):
        raw = cfg.sources.weather.raw_files
        assert len(raw) == 7 and all(r.content_sha256 and r.elements for r in raw)
        assert sum(r.elements for r in raw) == 4516                      # 1,129 hours x 4 parameters

    def test_retrieval_metadata_is_recorded_for_every_source(self, cfg):
        assert str(cfg.sources.flavoria.archive_retrieved_on) == "2026-09-18" and cfg.sources.flavoria.archive_retrieval_method
        assert str(cfg.sources.weather.retrieved_on) == "2026-09-18" and cfg.sources.weather.retrieval_method

    def test_fmi_licence_is_recorded_as_verified_not_guessed(self, cfg):
        w = cfg.sources.weather
        assert w.license == "CC-BY-4.0" and w.license_terms_url == "https://en.ilmatieteenlaitos.fi/open-data-licence"
        assert str(w.license_verified_on) == "2026-09-19"

    def test_override_scope_is_configured(self, cfg):
        v = cfg.timezone.overrides["registered_2020_10_05-2020_10_18.csv"].valid_for
        assert (v.first_event_date.isoformat(), v.last_event_date.isoformat()) == ("2020-10-05", "2020-10-16")
        assert v.raw_median_first_event_hour_band == (pytest.approx(7.0), pytest.approx(8.5))

    def test_a_variant_that_lacks_a_required_column_is_rejected(self, config_copy):
        config_copy.edit("sources.yml", "V7_without_weighting_type: [session_id, weighing_event_time, scale_identifier,", "V7_without_weighting_type: [session_id, weighing_event_time,")
        with pytest.raises(ConfigError, match="lacks required columns"):
            load_config(config_copy.dir)

    def test_a_short_member_sha_is_rejected(self, config_copy):
        config_copy.edit("sources.yml", "sha256: b8132640bc606a2b51fbe622536fd147b8486ae393e6796e629b6a7872be6056", "sha256: b813")
        with pytest.raises(ConfigError, match="64 hex"):
            load_config(config_copy.dir)
