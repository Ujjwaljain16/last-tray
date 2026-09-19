"""Staging on the real committed data: counts against the golden expectations, raw preservation, reproducible canonical time,
population separation, override confinement, verified-reader enforcement and failure behaviour."""
from __future__ import annotations

import ast
import csv
import hashlib
import io
import json
import os
import subprocess
import sys
import tarfile
from pathlib import Path

import pandas as pd
import pytest

from src.ingest.handoff import VerifiedReader, load_handoff
from src.ingest.ingest import run_ingestion
from src.ingest.model import LaneOutcome
from src.stage.stage import DETERMINISTIC_FILES, EVENTS_CSV, RECON_CSV, WEATHER_CSV, run_staging
from tests.helpers import REG_FILE, build_tar, read_members

REPO = Path(__file__).resolve().parents[1]
STAGE_DIR = REPO / "src" / "stage"
pytestmark = pytest.mark.usefixtures("no_network")


# ---- golden expectations ----------------------------------------------------------------------------------------------------------------------
class TestStagingCountsMatchGolden:
    def test_event_counts(self, real_staging, golden):
        g = golden["staging"]
        ev = real_staging.events
        assert len(ev) == g["events_rows"] == golden["counts"]["raw_event_rows"]
        assert ev.groupby("population").size().to_dict() == g["events_by_population"]

    def test_session_keys_keep_the_populations_apart(self, real_staging, golden):
        g, ev = golden["staging"], real_staging.events
        assert ev.session_id.nunique() == g["distinct_session_ids"] == 3343
        assert ev.session_key.nunique() == g["distinct_session_keys"] == 3345 == golden["counts"]["session_population_rows"]
        both = sorted(set(ev[ev.population == "registered_export"].session_id) & set(ev[ev.population == "non_registered_export"].session_id))
        assert both == g["session_ids_in_both_populations"] == golden["counts"]["crossover_session_ids"]

    def test_timezone_handling_counts(self, real_staging, golden):
        assert real_staging.events.timezone_handling.value_counts().to_dict() == golden["staging"]["timezone_handling"]

    def test_no_event_time_is_ambiguous_or_nonexistent_or_unparseable(self, real_staging, golden):
        ev = real_staging.events
        assert int(((ev.event_time_status != "OK") | (ev.identification_time_status != "OK")).sum()) == golden["staging"]["rows_with_local_time_status_not_ok"] == 0

    def test_schema_drift_is_visible_in_the_staged_rows(self, real_staging, golden):
        ev = real_staging.events
        assert int((ev.weighing_type != "").sum()) == golden["staging"]["rows_with_weighing_type"] == 5294
        assert set(ev[ev.weighing_type != ""].weighing_type) == {"line"}
        assert ev.schema_variant.value_counts().to_dict() == {"V7_without_weighting_type": 6990, "V8_with_weighting_type": 5294}

    def test_component_fields(self, real_staging, golden):
        ev = real_staging.events
        assert int((ev.component_name_had_edge_whitespace == "true").sum()) == golden["staging"]["rows_with_component_name_edge_whitespace"] == 398
        assert ev.component_name_raw.nunique() == 246 and ev.component_id_normalized.nunique() == 245     # profiling: one case-fold merge only

    def test_staging_keeps_what_validation_will_judge_later(self, real_staging, golden):
        ev = real_staging.events
        assert int((ev.component_weight_g.astype(int) >= 1500).sum()) == golden["staging"]["events_at_or_above_1500g"] == 6
        assert int(ev.raw_row_sha256.duplicated().sum()) == golden["staging"]["exact_duplicate_raw_rows_within_file"] == 2
        assert (ev.weight_parse_status == "OK").all() and (ev.row_parse_status == "OK").all()

    def test_file_reconciliation_agrees_with_ingestion(self, real_staging, cfg):
        recon = pd.read_csv(real_staging.out / "staging" / RECON_CSV)
        pins = {m.file: m.rows for m in cfg.sources.flavoria.members}
        assert dict(zip(recon.source_file, recon.rows_staged)) == pins == dict(zip(recon.source_file, recon.rows_verified_at_ingestion))
        by_pop = recon.groupby("population").distinct_sessions.sum().to_dict()
        assert by_pop == {"registered_export": 1699, "non_registered_export": 1646}


# ---- raw timestamps and values are untouched ------------------------------------------------------------------------------------------------------
def raw_rows_independently():
    """Read the archive with plain tarfile + csv, sharing no code with the pipeline."""
    out = []
    with tarfile.open(REPO / "data/raw/flavoria/dataset_csv.tar") as tf:
        for m in sorted(tf.getmembers(), key=lambda m: m.name):
            text = tf.extractfile(m).read().decode("utf-8-sig")
            reader = csv.reader(io.StringIO(text))
            header = next(reader)
            ix = {n: i for i, n in enumerate(header) if n}
            n = 0
            for rec in reader:
                if not any(c.strip() for c in rec):
                    continue
                n += 1
                g = lambda k: rec[ix[k]]
                out.append((m.name, n, g("session_id"), g("weighing_event_time"), g("scale_identifier"), g("weight_of_a_component"),
                            g("component_name"), g("tray_id"), g("user_identification_time"), hashlib.sha256("\x1f".join(rec).encode()).hexdigest()))
    return out


class TestRawTimestampsAndValuesUntouched:
    def test_every_raw_field_of_every_row_equals_the_source_text(self, real_staging):
        raw = raw_rows_independently()
        ev = real_staging.events
        staged = list(zip(ev.source_file, ev.source_row_number.astype(int), ev.session_id, ev.event_time_raw, ev.scale_id, ev.weight_raw,
                          ev.component_name_raw, ev.tray_id, ev.identification_time_raw, ev.raw_row_sha256))
        assert len(raw) == len(staged) == 12284
        assert staged == raw, "a staged raw field differs from the source text"

    def test_raw_timestamp_formats_are_preserved_not_unified(self, real_staging):
        ev = real_staging.events
        assert ev.event_time_raw.str.contains(r"^\d{4}\.\d{2}\.\d{2} ", regex=True).sum() == 1931        # the dotted file stays dotted
        assert ev.event_time_raw.str.contains(r"^\d{4}-\d{2}-\d{2} ", regex=True).sum() == 12284 - 1931
        assert ev.identification_time_raw.str.contains(r"^\d{4}\.\d{2}\.\d{2} ", regex=True).sum() == 1931 + 580     # plus one file that is dotted only here

    def test_the_run_leaves_the_raw_tree_untouched(self, cfg, raw_repo, tmp_path):
        from src.ingest import preserve
        before = preserve.capture(raw_repo / "data" / "raw")
        run_ingestion(cfg, raw_repo, tmp_path)
        h = load_handoff(tmp_path / "ingestion" / "staging_handoff.json")
        run_staging(cfg, VerifiedReader(raw_repo, h), tmp_path)
        assert before.diff(preserve.capture(raw_repo / "data" / "raw")) == []


# ---- canonical timestamps are reproducible, and independently so --------------------------------------------------------------------------------------
class TestCanonicalTimestamps:
    @pytest.mark.parametrize("raw_col, utc_col", [("event_time_raw", "event_time_canonical_utc"), ("identification_time_raw", "identification_time_canonical_utc")])
    def test_an_independent_pandas_computation_agrees_on_every_row(self, real_staging, raw_col, utc_col):
        ev = real_staging.events
        naive = pd.to_datetime(ev[raw_col].str.replace(".", "-", regex=False))
        shifted = ev.source_file == REG_FILE
        expected = pd.Series(pd.NaT, index=ev.index, dtype="datetime64[ns, UTC]")
        expected[~shifted] = naive[~shifted].dt.tz_localize("Europe/Helsinki", ambiguous="NaT", nonexistent="NaT").dt.tz_convert("UTC")
        expected[shifted] = naive[shifted].dt.tz_localize("UTC")            # hypothesis H1: that file's raw times ARE UTC
        got = pd.to_datetime(ev[utc_col], utc=True)
        assert got.equals(expected), "canonical UTC differs from the independent computation"
        assert got.notna().all()

    def test_dst_is_respected_across_the_2020_10_25_change(self, real_staging):
        ev = real_staging.events[real_staging.events.source_file != REG_FILE]
        naive = pd.to_datetime(ev.event_time_raw)
        got = pd.to_datetime(ev.event_time_canonical_utc, utc=True).dt.tz_localize(None)
        offset_hours = ((naive - got).dt.total_seconds() / 3600).round().astype(int)
        before, after = naive < "2020-10-25", naive >= "2020-10-25"
        assert set(offset_hours[before]) == {3} and set(offset_hours[after]) == {2}, "Helsinki offset must differ across the clock change"

    def test_the_override_file_is_shifted_by_exactly_three_hours_and_only_it(self, real_staging):
        ev = real_staging.events
        shifted = ev[ev.timezone_handling == "NORMALISED_PLUS_3H_STRONGEST_SUPPORT"]
        raw = pd.to_datetime(shifted.event_time_raw.str.replace(".", "-", regex=False))
        assert ((pd.to_datetime(shifted.event_time_local) - raw) == pd.Timedelta(hours=3)).all()
        assert (shifted.timezone_offset_hours_applied == "3").all()
        assert (shifted.timezone_transformation_reason.str.startswith("cross-export temporal alignment")).all()

    def test_two_runs_reproduce_identical_canonical_timestamps_and_files(self, cfg, real_staging, tmp_path):
        h = real_staging.handoff
        again = run_staging(cfg, VerifiedReader(REPO, h), tmp_path)
        assert again.hashes == real_staging.result.hashes

    def test_reproducible_across_hash_seeds_and_working_directories(self, tmp_path):
        sums = []
        for seed, cwd in (("1", REPO), ("31337", tmp_path)):
            out = tmp_path / f"o{seed}"
            env = {**os.environ, "PYTHONHASHSEED": seed, "PYTHONPATH": str(REPO)}
            r = subprocess.run([sys.executable, "-m", "src.pipeline.run", "--stages", "stage", "--out", str(out)], cwd=cwd, env=env,
                               capture_output=True, text=True, timeout=300)
            assert r.returncode == 0, r.stderr
            sums.append({n: hashlib.sha256((out / "staging" / n).read_bytes()).hexdigest() for n in DETERMINISTIC_FILES})
        assert sums[0] == sums[1]


# ---- the override cannot reach another file -----------------------------------------------------------------------------------------------------------
class TestOverrideConfinement:
    def test_offset_is_applied_to_exactly_one_source_file(self, real_staging):
        ev = real_staging.events
        assert set(ev[ev.timezone_offset_hours_applied != "0"].source_file) == {REG_FILE}
        assert int((ev.source_file == REG_FILE).sum()) == 1931 == int((ev.timezone_offset_hours_applied == "3").sum())
        assert (ev[ev.source_file != REG_FILE].timezone_handling == "SOURCE_LOCAL_ASSUMED").all()

    def test_the_other_registered_export_files_are_not_shifted(self, real_staging):
        ev = real_staging.events
        other_registered = ev[(ev.population == "registered_export") & (ev.source_file != REG_FILE)]
        assert len(other_registered) == 8372 - 1931 and (other_registered.timezone_offset_hours_applied == "0").all()

    def test_a_forged_handoff_shifting_another_file_stops_core_staging(self, cfg, raw_repo, tmp_path):
        run_ingestion(cfg, raw_repo, tmp_path)
        h = load_handoff(tmp_path / "ingestion" / "staging_handoff.json")
        victim = next(m for m in h["core"]["members"] if m["file"] == "registered_2020-11-02_2020-11-08.csv")
        victim["timezone"] = {"normalization": "NORMALISED_PLUS_3H_STRONGEST_SUPPORT", "offset_hours": 3, "scope": "file_specific",
                              "source_confirmed": False, "assumed_zone_for_unshifted_times": "Europe/Helsinki"}
        res = run_staging(cfg, VerifiedReader(raw_repo, h), tmp_path)
        assert res.core is LaneOutcome.FAILED and any("configuration has none for that file" in m.text for m in res.messages)
        assert not (tmp_path / "staging" / EVENTS_CSV).exists() and res.events == []

    def test_a_handoff_that_stops_shifting_the_configured_file_also_stops_staging(self, cfg, raw_repo, tmp_path):
        run_ingestion(cfg, raw_repo, tmp_path)
        h = load_handoff(tmp_path / "ingestion" / "staging_handoff.json")
        next(m for m in h["core"]["members"] if m["file"] == REG_FILE)["timezone"].update(normalization="SOURCE_LOCAL_ASSUMED", offset_hours=0, scope="none")
        assert run_staging(cfg, VerifiedReader(raw_repo, h), tmp_path).core is LaneOutcome.FAILED


# ---- verified-reader enforcement ------------------------------------------------------------------------------------------------------------------------
def module_asts(exclude: set[str] = frozenset()):
    for p in sorted(STAGE_DIR.glob("*.py")):
        if p.name not in exclude:
            yield p, ast.parse(p.read_text(encoding="utf-8"))


class TestStagingCannotBypassTheVerifiedReader:
    FORBIDDEN_IMPORTS = {"tarfile", "shutil", "glob", "socket", "requests", "urllib", "zipfile"}

    def test_no_staging_module_imports_a_file_access_or_network_library(self):
        for p, tree in module_asts():
            imported = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
            imported |= {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
            assert not (imported & self.FORBIDDEN_IMPORTS), f"{p.name} imports {imported & self.FORBIDDEN_IMPORTS}"

    def test_the_parsing_modules_cannot_touch_the_filesystem_at_all(self):
        for p, tree in module_asts(exclude={"stage.py", "__init__.py"}):
            imported = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
            imported |= {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
            assert not (imported & {"pathlib", "os"}), f"{p.name} imports {imported & {'pathlib', 'os'}}"
            calls = {n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
            attrs = {n.func.attr for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
            assert "open" not in calls and not (attrs & {"read_bytes", "read_text", "open", "write_bytes", "write_text"}), p.name

    def test_no_staging_module_mentions_the_raw_directory(self):
        for p, tree in module_asts():
            docstrings = {id(n.body[0].value) for n in ast.walk(tree)
                          if isinstance(n, (ast.Module, ast.FunctionDef, ast.ClassDef)) and n.body and isinstance(n.body[0], ast.Expr)
                          and isinstance(n.body[0].value, ast.Constant)}                         # prose may say "never opens data/raw"
            strings = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docstrings]
            assert not [s for s in strings if "data/raw" in s or "data\\raw" in s or s == "raw"], f"{p.name} names the raw directory"

    def test_stage_orchestration_reads_no_raw_and_only_writes_outputs(self):
        tree = ast.parse((STAGE_DIR / "stage.py").read_text(encoding="utf-8"))
        attrs = {n.func.attr for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
        assert not (attrs & {"read_bytes", "read_text", "open"}), "stage.py must obtain bytes only from the VerifiedReader"

    def test_staging_works_from_a_reader_alone_with_no_raw_directory_anywhere(self, cfg, real_staging, tmp_path):
        """Prove the only input is the reader: feed staging bytes from a fake reader; no data/raw exists relative to it."""
        members = read_members(REPO / "data/raw/flavoria/dataset_csv.tar")
        chunks = {c["file"]: (REPO / c["path"]).read_bytes() for c in real_staging.handoff["context"]["chunks"]}

        class FakeReader:
            handoff = real_staging.handoff
            member = staticmethod(lambda name: members[name])
            weather_chunk = staticmethod(lambda name: chunks[name])

        res = run_staging(cfg, FakeReader(), tmp_path)
        assert res.core is LaneOutcome.OK and res.context is LaneOutcome.OK and res.hashes == real_staging.result.hashes


# ---- failure behaviour ------------------------------------------------------------------------------------------------------------------------------------
@pytest.fixture()
def staged_then_tampered(cfg, raw_repo, tmp_path):
    """Ingest and stage cleanly, so outputs exist. Returns helpers to tamper with raw AFTER ingestion (the pins are not consulted again)."""
    run_ingestion(cfg, raw_repo, tmp_path)
    h = load_handoff(tmp_path / "ingestion" / "staging_handoff.json")
    first = run_staging(cfg, VerifiedReader(raw_repo, h), tmp_path)
    assert first.core is LaneOutcome.OK and (tmp_path / "staging" / EVENTS_CSV).exists()
    return raw_repo, h, tmp_path


class TestFailedVerificationStopsThatSourcesStagingPath:
    def test_a_member_changed_after_ingestion_stops_core_staging_and_removes_the_stale_table(self, cfg, staged_then_tampered):
        root, h, out = staged_then_tampered
        arc = root / h["core"]["archive"]["path"]
        members = read_members(arc)
        members[REG_FILE] = members[REG_FILE].replace(b"session", b"sessioN", 1)
        build_tar(arc, members)
        res = run_staging(cfg, VerifiedReader(root, h), out)
        assert res.core is LaneOutcome.FAILED and any("no longer match the SHA-256 verified at ingestion" in m.text for m in res.messages)
        assert not (out / "staging" / EVENTS_CSV).exists() and not (out / "staging" / RECON_CSV).exists(), "a stale table must not survive a failure"
        assert res.context is LaneOutcome.OK and (out / "staging" / WEATHER_CSV).exists(), "core failure must not remove valid weather staging"
        assert json.loads((out / "staging" / "staging_summary.json").read_text())["core_outcome"] == "FAILED"

    def test_staging_stops_at_the_first_failed_member_and_reads_no_further(self, cfg, staged_then_tampered):
        root, h, out = staged_then_tampered
        arc = root / h["core"]["archive"]["path"]
        members = read_members(arc)
        ordered = sorted(members)
        members[ordered[2]] = members[ordered[2]] + b"\r\n"            # third member tampered
        build_tar(arc, members)
        inner = VerifiedReader(root, h)
        asked = []

        class Spy:
            handoff = h

            def member(self, name):
                asked.append(name)
                return inner.member(name)

            weather_chunk = staticmethod(inner.weather_chunk)

        res = run_staging(cfg, Spy(), out)
        assert res.core is LaneOutcome.FAILED and asked == ordered[:3], f"staging continued past the failure: {asked}"

    def test_a_weather_chunk_changed_after_ingestion_blocks_weather_only(self, cfg, staged_then_tampered):
        root, h, out = staged_then_tampered
        p = root / h["context"]["chunks"][1]["path"]
        p.write_bytes(p.read_bytes() + b" ")
        res = run_staging(cfg, VerifiedReader(root, h), out)
        assert res.context is LaneOutcome.BLOCKED and res.core is LaneOutcome.OK
        assert not (out / "staging" / WEATHER_CSV).exists() and (out / "staging" / EVENTS_CSV).exists()

    def test_a_handoff_that_is_not_ready_stages_nothing(self, cfg, raw_repo, tmp_path):
        (raw_repo / "data/raw/flavoria/dataset_csv.tar").unlink()
        run_ingestion(cfg, raw_repo, tmp_path)
        h = load_handoff(tmp_path / "ingestion" / "staging_handoff.json")
        res = run_staging(cfg, VerifiedReader(raw_repo, h), tmp_path)
        assert res.core is LaneOutcome.FAILED and res.events == [] and not (tmp_path / "staging" / EVENTS_CSV).exists()


# ---- weather staging --------------------------------------------------------------------------------------------------------------------------------------
class TestWeatherStaging:
    def test_counts_and_utc(self, real_staging, golden):
        w, g = real_staging.weather, golden["staging"]
        assert len(w) == g["weather_rows"] == 4516
        assert w.groupby("parameter").size().to_dict() == {"r_1h": 1129, "ri_10min": 1129, "t2m": 1129, "ws_10min": 1129}
        assert w[w.parameter == "t2m"].obs_time_raw.nunique() == g["weather_distinct_hours"] == 1129
        assert (w.obs_time_canonical_utc == w.obs_time_raw).all(), "FMI states UTC ('Z'): canonical UTC equals the stated instant"
        assert (w.timezone_handling == "SOURCE_UTC_STATED").all()

    def test_nan_stays_null_and_is_never_zero(self, real_staging, golden):
        w = real_staging.weather
        nan = w[w.value_status == "NAN_SOURCE_NULL"]
        assert len(nan) == golden["staging"]["weather_nan_values"] == 3
        assert (nan.value == "").all() and (nan.value_raw.str.lower() == "nan").all()
        assert not ((w.value_status == "NAN_SOURCE_NULL") & (w.value == "0")).any()

    def test_raw_value_text_is_preserved_beside_the_typed_value(self, real_staging):
        w = real_staging.weather
        ok = w[w.value_status == "OK"]
        assert (ok.value.astype(float) == ok.value_raw.astype(float)).all()


# ---- lineage ----------------------------------------------------------------------------------------------------------------------------------------------------
class TestLineagePropagation:
    def test_every_staged_row_traces_to_a_snapshot_and_a_manifest_artifact(self, real_staging):
        manifest = pd.read_csv(real_staging.out / "ingestion" / "raw_artifact_manifest.csv")
        member_ids = set(manifest[manifest.kind == "member"].artifact_id)
        ev = real_staging.events
        assert set(ev.raw_artifact_id) == member_ids and set(ev.source_snapshot_id) == {real_staging.handoff["core"]["source_snapshot_id"]}
        chunk_ids = set(manifest[manifest.kind == "weather_chunk"].artifact_id)
        assert set(real_staging.weather.raw_artifact_id) == chunk_ids
        assert set(real_staging.weather.source_snapshot_id) == {real_staging.handoff["context"]["source_snapshot_id"]}

    def test_event_ids_are_unique_and_encode_file_and_row(self, real_staging):
        ev = real_staging.events
        assert ev.event_id.is_unique and (ev.event_id == ev.source_file + "#" + ev.source_row_number).all()

    def test_a_row_can_be_traced_back_to_its_source_line_and_checksum(self, real_staging):
        row = real_staging.events.iloc[5000]
        manifest = pd.read_csv(real_staging.out / "ingestion" / "raw_artifact_manifest.csv")
        artifact = manifest[manifest.artifact_id == row.raw_artifact_id].iloc[0]
        assert artifact.filename == row.source_file and len(artifact.sha256) == 64 and artifact.source_url.startswith("https://")
        assert artifact.source_snapshot_id == row.source_snapshot_id and int(row.source_row_number) >= 1
