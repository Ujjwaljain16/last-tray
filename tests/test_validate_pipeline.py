"""Validation as a stage: schema, lineage, determinism, refusal to run on damaged staging, no raw reads, and no silent deletion."""
from __future__ import annotations

import ast
import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from src.stage.stage import DETERMINISTIC_FILES as STAGING_FILES, EVENTS_CSV, RECON_CSV, SUMMARY_JSON as STAGING_SUMMARY, WEATHER_CSV
from src.validate import reconcile as rc
from src.validate.load import StagingInputError, load_staging
from src.validate.model import ISSUE_COLUMNS
from src.validate.validate import DETERMINISTIC_FILES, ISSUES_CSV, OUT_SUBDIR, run_validation

REPO = Path(__file__).resolve().parents[1]
VALIDATE_DIR = REPO / "src" / "validate"
pytestmark = pytest.mark.usefixtures("no_network")


def rows(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture()
def staging_copy(tmp_path, real_staging) -> Path:
    """A private copy of the real staging directory that a test may damage."""
    out = tmp_path / "out"
    shutil.copytree(real_staging.out / "staging", out / "staging")
    return out


# ---- schema, lineage, traceability ---------------------------------------------------------------------------------------------------------
class TestIssueTableContract:
    def test_columns_and_value_domains(self, real_validation):
        path = real_validation.out / OUT_SUBDIR / ISSUES_CSV
        assert tuple(csv.DictReader(path.open(encoding="utf-8")).fieldnames) == ISSUE_COLUMNS
        issues = rows(path)
        assert {i["severity"] for i in issues} <= {"ERROR", "WARN", "INFO"} and {i["handling"] for i in issues} <= {"FLAG", "QUARANTINE", "BLOCK", "KEEP_FIRST"}
        assert len({i["validation_issue_id"] for i in issues}) == len(issues), "issue ids are unique"
        assert len({i["run_id"] for i in issues}) == 1 and issues[0]["run_id"].startswith("val-")
        assert all((i["quarantine"] == "true") == (i["handling"] == "QUARANTINE") for i in issues), "quarantine is a flag of handling, not a separate meaning"

    def test_severity_is_kept_apart_from_quarantine(self, real_validation):
        issues = rows(real_validation.out / OUT_SUBDIR / ISSUES_CSV)
        assert {(i["severity"], i["quarantine"]) for i in issues} == {("ERROR", "true"), ("WARN", "false"), ("INFO", "false")}

    def test_every_error_and_warn_traces_back_to_staged_rows_or_a_named_scope(self, real_validation, real_staging):
        staged_ids = set(real_staging.events.event_id)
        weather_ids = set(real_staging.weather.observation_id)
        snapshot = set(real_staging.events.source_snapshot_id)
        for i in rows(real_validation.out / OUT_SUBDIR / ISSUES_CSV):
            lineage = [x for x in i["source_row_lineage"].split(";") if x]
            if i["lineage_basis"] == "WEATHER_OBSERVATION":
                assert set(lineage) <= weather_ids and lineage, i["validation_issue_id"]
                continue
            assert set(lineage) <= staged_ids, f"{i['validation_issue_id']} points at a row that is not staged"
            if i["event_id"]:
                assert i["event_id"] in staged_ids and i["source_file"] == i["event_id"].split("#")[0] and i["source_snapshot_id"] in snapshot
            if i["severity"] in ("ERROR", "WARN"):
                traceable = bool(lineage) or (i["lineage_basis"] == "SOURCE_FILE" and i["source_file"]) or (i["lineage_basis"] == "SERVICE_DAY" and i["source_file"]) \
                    or (i["lineage_basis"] in ("ABSENT_SOURCE", "POPULATION") and i["population"])
                assert traceable, f"{i['rule_id']} {i['entity_id']} cannot be traced to a source"

    def test_error_findings_list_every_row_of_the_session(self, real_validation, real_staging):
        ev = real_staging.events
        for i in [x for x in rows(real_validation.out / OUT_SUBDIR / ISSUES_CSV) if x["severity"] == "ERROR"]:
            sid, pop = i["session_key"].split("|")
            expected = set(ev[(ev.session_id == sid) & (ev.population == pop)].event_id)
            assert set(i["source_row_lineage"].split(";")) == expected

    def test_the_session_and_event_status_tables_cover_everything(self, real_validation, real_staging):
        d = real_validation.out / OUT_SUBDIR
        events = rows(d / "event_validation_status.csv")
        assert [e["event_id"] for e in events] == list(real_staging.events.event_id), "every staged row appears exactly once, in staging order"
        assert {e["disposition"] for e in events} == {"MODELLABLE", "DUPLICATE_EXCLUDED", "QUARANTINED"}
        sessions = rows(d / "session_validation_status.csv")
        assert len(sessions) == 3345 and sum(int(s["events_staged"]) for s in sessions) == 12284


class TestNothingIsSilentlyDropped:
    def test_validation_does_not_modify_the_staging_tables(self, tmp_path, real_staging, cfg):
        out = tmp_path / "o"
        shutil.copytree(real_staging.out / "staging", out / "staging")
        before = {n: sha(out / "staging" / n) for n in STAGING_FILES}
        run_validation(cfg, out)
        assert {n: sha(out / "staging" / n) for n in STAGING_FILES} == before

    def test_every_quarantined_and_repeated_row_is_still_a_row_in_staging_and_has_a_disposition(self, real_validation, real_staging):
        disp = {e["event_id"]: e["disposition"] for e in rows(real_validation.out / OUT_SUBDIR / "event_validation_status.csv")}
        assert set(disp) == set(real_staging.events.event_id) and len(disp) == 12284
        assert list(disp.values()).count("QUARANTINED") == 22 and list(disp.values()).count("DUPLICATE_EXCLUDED") == 2

    def test_a_broken_partition_is_reported_as_c04_and_blocks(self, staging_copy, cfg, monkeypatch):
        real = rc.disposition
        monkeypatch.setattr(rc, "disposition", lambda *a, **k: {k2: v for k2, v in list(real(*a, **k).items())[:-1]})   # one event loses its disposition
        res = run_validation(cfg, staging_copy)
        assert res.core_status == "BLOCKED" and any(i["rule_id"] == "C04" and i["severity"] == "ERROR" and i["handling"] == "BLOCK" for i in res.issues)
        assert "E05" in res.summary["reconciliation"]["failed_checks"]


# ---- determinism --------------------------------------------------------------------------------------------------------------------------
class TestDeterminism:
    def test_two_runs_write_byte_identical_files(self, staging_copy, cfg):
        run_validation(cfg, staging_copy)
        first = {n: sha(staging_copy / OUT_SUBDIR / n) for n in DETERMINISTIC_FILES}
        run_validation(cfg, staging_copy)
        assert {n: sha(staging_copy / OUT_SUBDIR / n) for n in DETERMINISTIC_FILES} == first

    def test_outputs_carry_no_wall_clock_and_use_lf(self, real_validation):
        for n in DETERMINISTIC_FILES:
            data = (real_validation.out / OUT_SUBDIR / n).read_bytes()
            assert b"\r\n" not in data, n
        text = (real_validation.out / OUT_SUBDIR / "validation_summary.json").read_text(encoding="utf-8")
        assert not any(k in text for k in ("started", "finished", "created_at", "utc_now"))

    def test_the_run_id_is_derived_from_the_inputs(self, staging_copy, cfg):
        a = run_validation(cfg, staging_copy).run_id
        assert a == run_validation(cfg, staging_copy).run_id and a.startswith("val-")

    def test_independent_processes_with_different_hash_seeds_and_directories_agree(self, tmp_path, real_staging):
        outs = []
        for seed, cwd in (("1", REPO), ("4242", tmp_path)):
            out = tmp_path / f"seed{seed}"
            shutil.copytree(real_staging.out / "staging", out / "staging")
            env = {**os.environ, "PYTHONHASHSEED": seed, "PYTHONPATH": str(REPO)}
            code = "import sys; from pathlib import Path; from src.config import load_config; from src.validate.validate import run_validation; " \
                   f"r = run_validation(load_config(Path(r'{REPO}') / 'config'), Path(r'{out}')); sys.exit(0 if r.core_status != 'BLOCKED' else 4)"
            done = subprocess.run([sys.executable, "-c", code], cwd=cwd, env=env, capture_output=True, text=True, timeout=180)
            assert done.returncode == 0, done.stderr
            outs.append({n: sha(out / OUT_SUBDIR / n) for n in DETERMINISTIC_FILES})
        assert outs[0] == outs[1], {n: (outs[0][n][:8], outs[1][n][:8]) for n in outs[0] if outs[0][n] != outs[1][n]}


# ---- refusal to validate damaged staging ---------------------------------------------------------------------------------------------------
class TestDamagedOrMissingStaging:
    def test_a_missing_staging_summary_stops_validation(self, staging_copy, cfg):
        (staging_copy / "staging" / STAGING_SUMMARY).unlink()
        res = run_validation(cfg, staging_copy)
        assert res.core_status == "BLOCKED" and "staging has not run" in res.error and not (staging_copy / OUT_SUBDIR / ISSUES_CSV).exists()

    def test_a_missing_event_table_stops_validation(self, staging_copy, cfg):
        (staging_copy / "staging" / EVENTS_CSV).unlink()
        assert "stg_weighing_event.csv is missing" in run_validation(cfg, staging_copy).error

    def test_an_altered_event_table_is_detected_by_checksum(self, staging_copy, cfg):
        p = staging_copy / "staging" / EVENTS_CSV
        p.write_bytes(p.read_bytes().replace(b"koti2", b"koti3", 1))
        res = run_validation(cfg, staging_copy)
        assert res.core_status == "BLOCKED" and "does not match the SHA-256 recorded by staging" in res.error

    def test_a_truncated_event_table_is_detected(self, staging_copy, cfg):
        p = staging_copy / "staging" / EVENTS_CSV
        p.write_bytes(p.read_bytes()[:-500])
        assert "does not match the SHA-256" in run_validation(cfg, staging_copy).error

    def test_a_table_swapped_with_a_consistent_but_wrong_hash_is_still_caught_by_the_row_count(self, staging_copy, cfg):
        p = staging_copy / "staging" / EVENTS_CSV
        lines = p.read_bytes().splitlines(keepends=True)
        p.write_bytes(b"".join(lines[:-1]))
        summary = json.loads((staging_copy / "staging" / STAGING_SUMMARY).read_text(encoding="utf-8"))
        summary["output_sha256"][EVENTS_CSV] = sha(p)
        (staging_copy / "staging" / STAGING_SUMMARY).write_text(json.dumps(summary), encoding="utf-8")
        assert "has 12283 rows but staging recorded 12284" in run_validation(cfg, staging_copy).error

    def test_a_staging_core_failure_is_not_validated(self, staging_copy, cfg):
        s = staging_copy / "staging" / STAGING_SUMMARY
        summary = json.loads(s.read_text(encoding="utf-8"))
        summary["core_outcome"] = "FAILED"
        s.write_text(json.dumps(summary), encoding="utf-8")
        assert "core lane as FAILED" in run_validation(cfg, staging_copy).error

    def test_a_failed_run_removes_stale_findings(self, staging_copy, cfg):
        assert run_validation(cfg, staging_copy).core_status == "PASSED_WITH_QUARANTINE"
        assert all((staging_copy / OUT_SUBDIR / n).exists() for n in DETERMINISTIC_FILES)
        (staging_copy / "staging" / EVENTS_CSV).unlink()
        run_validation(cfg, staging_copy)
        assert not any((staging_copy / OUT_SUBDIR / n).exists() for n in DETERMINISTIC_FILES), "a stale finding must never look current"

    def test_a_damaged_weather_table_blocks_weather_only(self, staging_copy, cfg):
        p = staging_copy / "staging" / WEATHER_CSV
        p.write_bytes(p.read_bytes() + b"x")
        res = run_validation(cfg, staging_copy)
        assert res.core_status == "PASSED_WITH_QUARANTINE" and res.weather_status == "BLOCKED"
        assert res.checks and any(c.check_id == "K00" and c.status == "FAIL" for c in res.checks)
        assert res.summary["quarantine"]["session_keys"] == 4, "core validation is unaffected by the weather lane"

    def _rewrite_weather(self, staging_copy, mutate):
        p = staging_copy / "staging" / WEATHER_CSV
        lines = p.read_bytes().decode("utf-8").splitlines()
        lines = mutate(lines)
        p.write_bytes(("\n".join(lines) + "\n").encode("utf-8"))
        summary_path = staging_copy / "staging" / STAGING_SUMMARY
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        summary["output_sha256"][WEATHER_CSV] = sha(p)
        summary["weather"]["rows"] = len([l for l in lines[1:] if l])
        summary_path.write_text(json.dumps(summary), encoding="utf-8")

    def test_a_weather_grain_violation_blocks_weather_not_core(self, staging_copy, cfg):
        def add_second_element_for_the_same_hour_and_parameter(lines):
            body = [l for l in lines if l]
            first = body[1].split(",")
            first[0] = "fmi_100949_20201005_20201011.xml#99999"          # a NEW element id, same station, time and parameter
            return body + [",".join(first)]

        self._rewrite_weather(staging_copy, add_second_element_for_the_same_hour_and_parameter)
        res = run_validation(cfg, staging_copy)
        assert res.weather_status == "BLOCKED" and res.core_status == "PASSED_WITH_QUARANTINE"
        assert any(i["rule_id"] == "X07" and i["handling"] == "BLOCK" and "grain" in i["description"] for i in res.issues)

    def test_a_repeated_observation_id_is_rejected_by_the_loader_and_blocks_weather_only(self, staging_copy, cfg):
        self._rewrite_weather(staging_copy, lambda lines: [l for l in lines if l] + [lines[1]])
        res = run_validation(cfg, staging_copy)
        assert res.weather_status == "BLOCKED" and "observation_id is not unique" in res.summary["weather"]["error"] and res.core_status == "PASSED_WITH_QUARANTINE"

    def test_a_missing_weather_hour_is_reported_as_x01_coverage_and_only_an_empty_table_fails(self, real_staging, cfg):
        from src.validate.rules_weather import check_weather
        wx = load_staging(real_staging.out).weather
        gap = [o for o in wx if o.obs_time_utc.isoformat() != "2020-10-05T03:00:00+00:00"]
        issues = check_weather(gap, cfg)
        assert [i.rule_id for i in issues if i.rule_id in ("X01", "X07", "X08")] == ["X01"]
        assert rc.coverage("K02", "d", 1129, 1128).status == "WARN" and rc.coverage("K02", "d", 1129, 0).status == "FAIL" and rc.coverage("K02", "d", 1129, 1129).status == "PASS"

    def test_the_loader_reads_nothing_it_cannot_verify(self, tmp_path):
        with pytest.raises(StagingInputError, match="has not run"):
            load_staging(tmp_path)


# ---- the override cannot leak, checked end to end ------------------------------------------------------------------------------------------------
class TestOverrideCannotApplyElsewhere:
    def test_a_forged_override_label_on_another_file_blocks_the_core_lane(self, staging_copy, cfg):
        p = staging_copy / "staging" / EVENTS_CSV
        text = p.read_text(encoding="utf-8")
        lines = text.split("\n")
        target = next(i for i, l in enumerate(lines) if l.startswith("registered_2020-10-19_2020-10-25.csv#") and ",SOURCE_LOCAL_ASSUMED," in l)
        lines[target] = lines[target].replace(",SOURCE_LOCAL_ASSUMED,0,", ",NORMALISED_PLUS_3H_STRONGEST_SUPPORT,3,", 1)
        p.write_bytes("\n".join(lines).encode("utf-8"))
        summary_path = staging_copy / "staging" / STAGING_SUMMARY
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        summary["output_sha256"][EVENTS_CSV] = sha(p)
        summary_path.write_text(json.dumps(summary), encoding="utf-8")
        res = run_validation(cfg, staging_copy)
        t10 = [i for i in res.issues if i["rule_id"] == "T10"]
        assert res.core_status == "BLOCKED" and t10 and t10[0]["source_file"] == "registered_2020-10-19_2020-10-25.csv"
        assert {"Z01", "Z02", "Z03"} & set(res.summary["reconciliation"]["failed_checks"])


# ---- static guarantees: validation never reads raw data ------------------------------------------------------------------------------------------
def module_trees():
    for p in sorted(VALIDATE_DIR.glob("*.py")):
        yield p, ast.parse(p.read_text(encoding="utf-8"))


class TestValidationNeverReadsRawData:
    FORBIDDEN_IMPORTS = {"tarfile", "zipfile", "shutil", "glob", "socket", "requests", "urllib", "http"}
    FORBIDDEN_MODULES = {"src.ingest.handoff", "src.ingest.flavoria", "src.ingest.retrieval", "src.ingest.requests_client", "src.ingest.snapshot", "src.ingest.preserve",
                         "src.ingest.ingest", "src.ingest.http"}

    def imports(self, tree):
        mods = set()
        for n in ast.walk(tree):
            if isinstance(n, ast.Import):
                mods |= {a.name for a in n.names}
            if isinstance(n, ast.ImportFrom) and n.module:
                mods.add(n.module)
                mods |= {f"{n.module}.{a.name}" for a in n.names}
        return mods

    def test_no_file_access_or_network_library_is_imported(self):
        for p, tree in module_trees():
            imported = {m.split(".")[0] for m in self.imports(tree)}
            assert not imported & self.FORBIDDEN_IMPORTS, f"{p.name} imports {imported & self.FORBIDDEN_IMPORTS}"

    def test_no_module_imports_the_raw_readers_or_the_ingestion_engine(self):
        for p, tree in module_trees():
            bad = self.imports(tree) & self.FORBIDDEN_MODULES
            assert not bad, f"{p.name} imports {sorted(bad)}"

    def test_only_load_py_touches_the_filesystem_and_only_through_staging_paths(self):
        for p, tree in module_trees():
            calls = {n.func.attr for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
            names = {n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
            if p.name not in ("load.py", "validate.py"):
                assert not (calls & {"read_bytes", "read_text", "open", "write_text", "write_bytes"}) and "open" not in names, p.name

    def test_no_string_names_the_raw_directory(self):
        for p, tree in module_trees():
            docstrings = {id(n.body[0].value) for n in ast.walk(tree) if isinstance(n, (ast.Module, ast.FunctionDef, ast.ClassDef)) and n.body
                          and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant)}
            strings = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docstrings]
            assert not [s for s in strings if "data/raw" in s or "data\\raw" in s or s in ("data", "flavoria")], p.name

    def test_validation_succeeds_with_no_raw_directory_anywhere(self, staging_copy, cfg):
        assert not (staging_copy / "data").exists() and not (staging_copy.parent / "data").exists()
        assert run_validation(cfg, staging_copy).core_status == "PASSED_WITH_QUARANTINE"

    def test_validation_reads_only_files_under_the_staging_directory(self, staging_copy, cfg, monkeypatch):
        opened: list[str] = []
        real_open = Path.open

        def spy(self, *a, **k):
            opened.append(str(self))
            return real_open(self, *a, **k)

        monkeypatch.setattr(Path, "open", spy)
        run_validation(cfg, staging_copy)
        reads = [p for p in opened if not p.startswith(str(staging_copy / OUT_SUBDIR))]
        assert reads and all(p.startswith(str(staging_copy / "staging")) for p in reads), reads
