"""The canonical model on the real committed data: golden counts, independent reconstruction, control against validation, weather join,
quarantine, components, timezone provenance and lineage. The independent recomputation below uses pandas on the STAGING csv and the validation
disposition file; it shares no code with src/model."""
from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd
import pytest

from src.model import schema
from src.model.build import OUT_SUBDIR, TABLE_FILES

pytestmark = pytest.mark.usefixtures("no_network")


def table(real_model, name: str) -> pd.DataFrame:
    return pd.read_csv(real_model.out / OUT_SUBDIR / TABLE_FILES[name], dtype=str, keep_default_na=False)


@pytest.fixture(scope="module")
def independent(real_staging, real_validation):
    """Session weights and counts recomputed with pandas from stg_weighing_event + event_validation_status, using no src/model code."""
    ev = real_staging.events.merge(pd.read_csv(real_validation.out / "validation" / "event_validation_status.csv", dtype=str, keep_default_na=False)[["event_id", "disposition"]],
                                   on="event_id")
    ev["w"] = pd.to_numeric(ev.component_weight_g, errors="coerce")
    mod = ev[ev.disposition == "MODELLABLE"]
    weights = mod.groupby("session_key").w.sum().astype(int)
    comps = mod[mod.component_id_normalized != ""].groupby("session_key").component_id_normalized.nunique()
    pairs = mod[mod.component_id_normalized != ""].groupby(["session_key", "component_id_normalized"]).size()
    return {"ev": ev, "weights": weights, "components": comps, "pairs": pairs}


class TestRowCountsAndKeys:
    def test_exact_canonical_row_counts(self, real_model, golden):
        assert real_model.result.counts == golden["model"]["rows"]
        assert real_model.result.manifest["tables"]["fact_dining_session"]["rows"] == 3345

    def test_written_files_have_the_declared_headers_and_row_counts(self, real_model):
        for t in schema.TABLES:
            with (real_model.out / OUT_SUBDIR / TABLE_FILES[t.name]).open(newline="", encoding="utf-8") as fh:
                r = csv.reader(fh)
                assert tuple(next(r)) == t.column_names, t.name
                assert sum(1 for _ in r) == real_model.result.counts[t.name]

    def test_session_keys_carry_the_population_and_are_unique(self, real_model, golden):
        s = table(real_model, "fact_dining_session")
        assert len(s) == golden["model"]["session_keys"] == 3345 and s.session_key.is_unique
        assert (s.session_key == s.session_id + "|" + s.population).all()
        assert s.session_id.nunique() == golden["model"]["session_ids"] == 3343

    def test_the_two_crossover_ids_stay_two_keys_each(self, real_model, golden):
        s = table(real_model, "fact_dining_session")
        both = s.groupby("session_id").population.nunique()
        assert sorted(both[both > 1].index) == ["session2266", "session3222"]
        assert sorted(s[s.identity_conflict == "true"].session_key) == [f"{i}|{p}" for i in ("session2266", "session3222") for p in ("non_registered_export", "registered_export")]

    def test_no_table_has_a_consumed_or_waste_column(self):
        names = {c.name for t in schema.TABLES for c in t.columns}
        assert not {n for n in names if any(w in n for w in ("consumed", "waste", "intake", "leftover", "demand", "customer", "diner"))}


class TestEventFact:
    def test_every_staged_event_is_present_with_lineage_and_disposition(self, real_model, real_staging, golden):
        e = table(real_model, "fact_weighing_event")
        assert list(e.event_id) == list(real_staging.events.event_id), "same rows, same order, nothing removed"
        assert e.event_id.is_unique and e.disposition.value_counts().to_dict() == golden["model"]["event_dispositions"]
        for col in ("source_snapshot_id", "raw_artifact_id", "raw_row_sha256", "source_file", "source_row_number"):
            assert (e[col] == real_staging.events[col]).all(), col

    def test_event_id_is_file_and_row(self, real_model):
        e = table(real_model, "fact_weighing_event")
        assert (e.event_id == e.source_file + "#" + e.source_row_number).all()

    def test_raw_and_normalised_values_are_both_preserved(self, real_model, real_staging):
        e = table(real_model, "fact_weighing_event")
        for col_model, col_stg in (("weight_raw", "weight_raw"), ("component_weight_g", "component_weight_g"), ("component_name_raw", "component_name_raw"),
                                   ("component_id_normalized", "component_id_normalized"), ("event_time_raw", "event_time_raw"), ("event_time_local", "event_time_local"),
                                   ("event_time_utc", "event_time_canonical_utc"), ("identification_time_raw", "identification_time_raw")):
            assert (e[col_model] == real_staging.events[col_stg]).all(), col_model

    def test_the_2097g_event_is_present_modellable_and_warned(self, real_model):
        e = table(real_model, "fact_weighing_event")
        big = e[e.weight_raw == "2097"]
        assert len(big) == 1 and big.iloc[0].disposition == "MODELLABLE" and big.iloc[0].component_weight_g == "2097"
        assert "B02" in big.iloc[0].validation_warn_rule_ids and big.iloc[0].quality_status == "WARN"

    def test_timezone_provenance_is_preserved_and_confined(self, real_model, real_staging):
        e = table(real_model, "fact_weighing_event")
        shifted = e[e.timezone_handling == "NORMALISED_PLUS_3H_STRONGEST_SUPPORT"]
        assert len(shifted) == 1931 and set(shifted.source_file) == {"registered_2020_10_05-2020_10_18.csv"}
        assert set(shifted.timezone_offset_hours_applied) == {"3"} and shifted.timezone_transformation_reason.str.startswith("cross-export temporal alignment").all()
        other = e[e.timezone_handling != "NORMALISED_PLUS_3H_STRONGEST_SUPPORT"]
        assert set(other.timezone_handling) == {"SOURCE_LOCAL_ASSUMED"} and set(other.timezone_offset_hours_applied) == {"0"}
        assert (e.timezone_handling == real_staging.events.timezone_handling).all()

    def test_canonical_utc_is_dst_aware_across_the_clock_change(self, real_model):
        e = table(real_model, "fact_weighing_event")
        local = pd.to_datetime(e.event_time_local).dt.tz_localize("Europe/Helsinki")
        assert (local.dt.tz_convert("UTC").dt.strftime("%Y-%m-%dT%H:%M:%SZ") == e.event_time_utc).all()
        assert set(e[e.event_time_local.str.startswith("2020-10-2")].event_time_utc.str[:10]) >= {"2020-10-23", "2020-10-26"}

    def test_quarantined_events_are_present_but_marked(self, real_model):
        e = table(real_model, "fact_weighing_event")
        q = e[e.disposition == "QUARANTINED"]
        assert len(q) == 22 and set(q.session_id) == {"session2266", "session3222"} and (q.is_modellable == "false").all() and (q.quality_status == "INVALID").all()
        assert set(q.quarantine_rule_ids) == {"I01"} and (e[e.disposition != "QUARANTINED"].quarantine_rule_ids == "").all()


class TestIndependentSelectedMealWeight:
    def test_the_canonical_weight_equals_an_independent_pandas_recomputation(self, real_model, independent):
        s = table(real_model, "fact_dining_session").set_index("session_key")
        canon = pd.to_numeric(s.derived_selected_meal_weight_g, errors="coerce").dropna().astype(int)
        assert canon.to_dict() == independent["weights"].to_dict() and len(canon) == 3341

    def test_the_canonical_weight_equals_validation_rule_weight_sum_g_for_every_eligible_session(self, real_model, real_validation, golden):
        validation_status = pd.read_csv(real_validation.out / "validation" / "session_validation_status.csv", dtype=str, keep_default_na=False).set_index("session_key")
        s = table(real_model, "fact_dining_session").set_index("session_key")
        live = s[s.is_quarantined == "false"]
        assert len(live) == golden["model"]["weight_control_matches"] == 3341
        assert (live.derived_selected_meal_weight_g == validation_status.loc[live.index, "rule_weight_sum_g"]).all()
        assert real_model.checks["M10"].status == "PASS" and real_model.checks["M10"].observed == "[]"

    def test_the_control_file_lists_every_session_and_flags_no_mismatch(self, real_model):
        c = pd.read_csv(real_model.out / OUT_SUBDIR / "session_weight_control.csv", dtype=str, keep_default_na=False)
        assert len(c) == 3345 and c.weight_control.value_counts().to_dict() == {"MATCH": 3341, "EXCLUDED_QUARANTINED": 4}
        assert set(c.span_control) == set(c.event_count_control) == set(c.first_weighing_control) == {"MATCH"}

    def test_quarantined_sessions_have_no_selected_weight_but_stay_traceable(self, real_model):
        s = table(real_model, "fact_dining_session").set_index("session_key")
        q = s[s.is_quarantined == "true"]
        assert len(q) == 4 and (q.derived_selected_meal_weight_g == "").all() and (q.core_ready == "false").all() and (q.modellable_event_count == "0").all()
        assert (q.quarantined_event_count.astype(int) == q.event_count.astype(int)).all() and (q.first_weighing_utc != "").all()

    def test_repeats_are_excluded_once_and_scoops_stay_additive(self, real_model, independent):
        s = table(real_model, "fact_dining_session").set_index("session_key")
        dup = s[s.duplicate_excluded_event_count != "0"]
        assert len(dup) == 2 and (dup.event_count.astype(int) == dup.modellable_event_count.astype(int) + 1).all()
        e = independent["ev"]
        scoops = e[(e.disposition == "MODELLABLE")].groupby(["session_key", "scale_id"]).size()
        assert (scoops > 1).sum() > 200, "repeated same-scale weighings exist and are all summed"
        for key in ("session1006|non_registered_export",):
            assert int(s.loc[key, "derived_selected_meal_weight_g"]) == int(independent["weights"][key])

    def test_the_weight_is_documented_as_derived_and_never_as_consumed_or_waste(self):
        col = next(c for c in schema.SESSION.columns if c.name == "derived_selected_meal_weight_g")
        assert col.cls == "DERIVED" and "NOT consumed quantity" in col.meaning and "NOT food waste" in col.meaning and "NOT actual intake" in col.meaning
        assert not any(c.name == "rule_weight_sum_g" for t in schema.TABLES for c in t.columns), "the validation working value is not a canonical field"


class TestSessionReconstruction:
    def test_event_counts_and_disposition_totals(self, real_model):
        s = table(real_model, "fact_dining_session")
        ints = s[["event_count", "modellable_event_count", "duplicate_excluded_event_count", "quarantined_event_count"]].astype(int)
        assert (ints.event_count == ints.modellable_event_count + ints.duplicate_excluded_event_count + ints.quarantined_event_count).all()
        assert ints.event_count.sum() == 12284 and ints.modellable_event_count.sum() == 12260 and ints.quarantined_event_count.sum() == 22

    def test_first_last_and_span_are_reproducible_from_the_events(self, real_model, independent):
        s = table(real_model, "fact_dining_session").set_index("session_key")
        e = independent["ev"][independent["ev"].disposition != "DUPLICATE_EXCLUDED"].copy()
        e["t"] = pd.to_datetime(e.event_time_canonical_utc)
        g = e.groupby("session_key").t.agg(["min", "max"])
        assert (pd.to_datetime(s.first_weighing_utc) == g["min"].reindex(s.index)).all() and (pd.to_datetime(s.last_weighing_utc) == g["max"].reindex(s.index)).all()
        assert (s.session_span_s.astype(int) == (g["max"] - g["min"]).dt.total_seconds().reindex(s.index).astype(int)).all()

    def test_span_findings_match_the_approved_t05_count(self, real_model):
        s = table(real_model, "fact_dining_session")
        reg = s[(s.is_primary_population == "true") & (s.is_quarantined == "false")]
        assert (reg.session_span_s.astype(int) > 600).sum() == 7

    def test_core_ready_is_prepared_for_m5_without_computing_the_metric(self, real_model, golden):
        s = table(real_model, "fact_dining_session")
        elig = s[s.is_primary_population == "true"]
        assert len(elig) == golden["model"]["eligible_primary_sessions"] == 1699
        assert (elig.core_ready == "true").sum() == golden["model"]["core_ready_sessions"] == 1697
        assert (s[s.is_primary_population == "false"].core_ready == "false").all()
        assert set(elig[elig.core_ready == "false"].session_key) == {"session2266|registered_export", "session3222|registered_export"}

    def test_warn_accounting_fields_reproduce_the_golden_reconciliation(self, real_model, golden):
        s = table(real_model, "fact_dining_session")
        live = s[(s.is_primary_population == "true") & (s.is_quarantined == "false")]
        w = golden["supporting"]["warn_free_reconciliation"]
        assert (live.has_session_warn == "true").sum() == w["with_session_level_warn"] == 34 and (live.has_session_warn == "false").sum() == w["no_session_level_warn"]
        only_event = live[(live.has_event_warn == "true") & (live.has_session_warn == "false")]
        assert sorted(only_event.session_id) == sorted(w["event_level_only_warn_sessions"])

    def test_no_person_or_customer_identity_is_created(self, real_model):
        s = table(real_model, "fact_dining_session")
        assert not [c for c in s.columns if any(w in c for w in ("customer", "person", "user", "diner"))]
        assert s.tray_id.str.startswith("tray").all() or (s.tray_id == "").any()


class TestComponents:
    def test_component_rows_equal_the_independent_distinct_pairs(self, real_model, independent, golden):
        c = table(real_model, "fact_session_component")
        assert len(c) == golden["model"]["rows"]["fact_session_component"] == len(independent["pairs"])
        assert set(zip(c.session_key, c.component_id_normalized)) == set(independent["pairs"].index)

    def test_distinct_component_counts_match_independent_and_raw_equals_normalised(self, real_model, independent):
        s = table(real_model, "fact_dining_session").set_index("session_key")
        live = s[s.modellable_event_count != "0"]
        assert (live.distinct_component_count.astype(int) == independent["components"].reindex(live.index)).all()
        assert (s.distinct_raw_component_count == s.distinct_component_count).all(), "profiling property: raw and normalised counts never differ within a session"
        assert real_model.checks["M15"].status == "PASS"

    def test_no_alias_table_names_are_only_trimmed_collapsed_and_casefolded(self, real_model):
        e = table(real_model, "fact_weighing_event")
        e = e[e.component_id_normalized != ""]
        assert (e.component_id_normalized == e.component_name_raw.str.strip().str.replace(r"\s+", " ", regex=True).str.casefold()).all()
        assert e.component_id_normalized.nunique() == 245 and e.component_name_raw.nunique() == 246

    def test_raw_spelling_variants_and_lineage_are_kept(self, real_model):
        c = table(real_model, "fact_session_component")
        assert c.source_row_lineage.str.contains("#").all() and (c.component_weighing_event_count.astype(int) == c.source_row_lineage.str.count(";") + 1).all()
        assert (c.component_name_raw_variants != "").all()

    def test_the_limited_status_marks_sessions_on_i07_scale_days_only(self, real_model):
        s = table(real_model, "fact_dining_session")
        assert set(s.distinct_component_count_status) == {"READY_WITH_LIMITATION", "LIMITED"}
        limited = s[s.distinct_component_count_status == "LIMITED"]
        assert len(limited) > 0 and limited.service_date.min() >= "2020-10-05" and limited.service_date.max() <= "2020-10-16", "only in the override window"


class TestWeather:
    def test_fact_weather_grain_and_lineage(self, real_model, real_staging, golden):
        w = table(real_model, "fact_weather")
        assert len(w) == 1129 == golden["model"]["rows"]["fact_weather"] and not w.duplicated(["fmisid", "obs_time_utc"]).any()
        assert set(w.fmisid) == {"100949"} and set(w.timezone_handling) == {"SOURCE_UTC_STATED"} and set(w.r_1h_convention) == {"hour_ending"}
        ids = set(real_staging.weather.observation_id)
        assert set(x for cell in w.source_row_lineage for x in cell.split(";")) == ids and sum(len(c.split(";")) for c in w.source_row_lineage) == 4516

    def test_missing_values_are_null_never_zero_and_raw_text_is_kept(self, real_model, real_staging):
        w = table(real_model, "fact_weather")
        nulls = w[w.is_null_any == "true"]
        assert 1 <= len(nulls) <= 3, "three NaN values across at most three hours"
        raw_nan = real_staging.weather[real_staging.weather.value_status == "NAN_SOURCE_NULL"]
        assert len(raw_nan) == 3
        for _, r in raw_nan.iterrows():
            row = w[w.obs_time_utc == r.obs_time_canonical_utc].iloc[0]
            col = {"t2m": "t2m_c", "ws_10min": "ws_10min_ms", "r_1h": "r_1h_mm", "ri_10min": "ri_10min_mmh"}[r.parameter]
            assert row[col] == "" and row[f"{r.parameter}_status"] == "NAN_SOURCE_NULL"
        ok = real_staging.weather[real_staging.weather.value_status == "OK"]
        sample = ok.iloc[100]
        row = w[w.obs_time_utc == sample.obs_time_canonical_utc].iloc[0]
        assert row[{"t2m": "t2m_c", "ws_10min": "ws_10min_ms", "r_1h": "r_1h_mm", "ri_10min": "ri_10min_mmh"}[sample.parameter]] == sample.value_raw

    def test_the_approved_1697_of_1697_alignment_is_reproduced(self, real_model, golden):
        s = table(real_model, "fact_dining_session")
        core = s[s.core_ready == "true"]
        j = golden["model"]["weather_join"]
        assert ((core.weather_matched == "true").sum(), len(core)) == (j["matched_core_ready"], j["eligible_core_ready"]) == (1697, 1697)
        assert s.weather_join_status.value_counts().to_dict() == {"MATCHED": j["matched_all"], "NOT_ATTEMPTED_QUARANTINED": j["not_attempted_quarantined"]}
        assert real_model.checks["M25"].observed == "1697 | 1697"

    def test_the_join_uses_the_next_full_utc_hour_independently(self, real_model):
        s = table(real_model, "fact_dining_session")
        m = s[s.weather_join_status == "MATCHED"]
        first = pd.to_datetime(m.first_weighing_utc)
        assert (pd.to_datetime(m.weather_hour_utc) == first.dt.ceil("h")).all()
        on_the_hour = m[first.dt.minute.eq(0) & first.dt.second.eq(0)]
        assert (pd.to_datetime(on_the_hour.weather_hour_utc) == pd.to_datetime(on_the_hour.first_weighing_utc)).all()

    def test_null_precipitation_counts_reproduce_reference(self, real_model, golden):
        s = table(real_model, "fact_dining_session")
        core = s[s.core_ready == "true"]
        n = golden["model"]["weather_null_precipitation_core_ready"]
        assert ((core.weather_r_1h_null == "true").sum(), (core.weather_ri_10min_null == "true").sum()) == (n["r_1h"], n["ri_10min"]) == (67, 25)

    def test_no_session_is_unmatched_and_quarantined_sessions_are_not_attempted(self, real_model):
        s = table(real_model, "fact_dining_session").set_index("session_key")
        assert not (s.weather_join_status == "UNMATCHED_NO_OBSERVATION").any()
        q = s[s.is_quarantined == "true"]
        assert (q.weather_join_status == "NOT_ATTEMPTED_QUARANTINED").all() and (q.weather_matched == "false").all() and (q.weather_hour_utc == "").all()


class TestDailyVolume:
    def test_grain_flags_and_wording(self, real_model, golden):
        v = table(real_model, "fact_daily_volume")
        assert len(v) == 65 and not v.duplicated(["service_date", "population"]).any()
        reg = v[v.is_primary_population == "true"]
        assert len(reg) == 35 and (reg.low_observed_volume_day == "true").sum() == 16
        assert sorted(reg[reg.volume_irregularity == "true"].service_date) == [str(d) for d in golden["supporting"]["volume_irregularity_days"]]
        assert (v[v.is_primary_population == "false"][["low_observed_volume_day", "volume_irregularity"]] == "false").all().all()
        assert (v[v.is_primary_population == "false"].expected_regime == "").all()

    def test_registered_sessions_sum_to_m3s_basis_and_no_day_is_excluded(self, real_model):
        v = table(real_model, "fact_daily_volume")
        assert v[v.is_primary_population == "true"].sessions.astype(int).sum() == 1697, "Observed Valid Sessions — Registered-Export Population"
        assert real_model.checks["M21"].status == "PASS"
        assert "demand" not in schema.VOLUME.grain.lower()
        assert "NOT demand" in next(c for c in schema.VOLUME.columns if c.name == "sessions").meaning


class TestControlSummary:
    def test_all_controls_pass_and_the_expected_facts_are_reported(self, real_model):
        assert real_model.result.core_status == "BUILT" and real_model.result.weather_status == "BUILT"
        assert not [c.check_id for c in real_model.result.checks if c.status == "FAIL"]
        assert real_model.checks["M19"].observed == "1697 | 1699" and real_model.checks["M11"].observed == "3341 | 4"

    def test_the_manifest_declares_semantics_and_inputs(self, real_model):
        m = real_model.result.manifest
        assert m["semantic_chain"][-1].startswith("SOURCE GAP") and "not consumed quantity" in m["field_notes"]["derived_selected_meal_weight_g"]
        assert m["field_notes"]["rule_weight_sum_g"].startswith("validation working value")
        assert m["inputs"]["validation_run_id"].startswith("val-") and set(m["inputs"]["staging_table_sha256"]) >= {"stg_weighing_event.csv"}
        assert all(t["sha256"] for t in m["tables"].values()) and m["tables"]["fact_weighing_event"]["rows"] == 12284
