"""The canonical model as a stage: determinism, refusal to build on damaged or inconsistent inputs, control-failure behaviour,
weather-only blocking, static 'no raw reads' guarantees, and documentation that cannot drift from the schema."""
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

from src.model import schema
from src.model.build import CONTROL_CSV, DETERMINISTIC_FILES, MANIFEST_JSON, OUT_SUBDIR, SESSION_CONTROL_CSV, TABLE_FILES, run_model
from src.model.inputs import ModelInputError, load_model_inputs
from src.stage.stage import EVENTS_CSV, WEATHER_CSV

REPO = Path(__file__).resolve().parents[1]
MODEL_DIR = REPO / "src" / "model"
pytestmark = pytest.mark.usefixtures("no_network")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rows(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


@pytest.fixture()
def model_copy(tmp_path, real_validation) -> Path:
    """A private copy of the real staging + validation directories that a test may damage."""
    out = tmp_path / "out"
    for sub in ("staging", "validation"):
        shutil.copytree(real_validation.out / sub, out / sub)
    return out


def resign(out: Path, name: str) -> None:
    """Simulate a CONSISTENT forgery: record the new checksum of a validation file in the validation summary."""
    p = out / "validation" / "validation_summary.json"
    summary = json.loads(p.read_text(encoding="utf-8"))
    summary["output_sha256"][name] = sha(out / "validation" / name)
    p.write_text(json.dumps(summary), encoding="utf-8")


# ---- determinism ----------------------------------------------------------------------------------------------------------------------------
class TestDeterminism:
    def test_two_runs_write_byte_identical_files(self, model_copy, cfg):
        run_model(cfg, model_copy)
        first = {n: sha(model_copy / OUT_SUBDIR / n) for n in DETERMINISTIC_FILES}
        run_model(cfg, model_copy)
        assert {n: sha(model_copy / OUT_SUBDIR / n) for n in DETERMINISTIC_FILES} == first

    def test_files_use_lf_and_carry_no_wall_clock(self, real_model):
        for n in DETERMINISTIC_FILES:
            assert b"\r\n" not in (real_model.out / OUT_SUBDIR / n).read_bytes(), n
        text = (real_model.out / OUT_SUBDIR / MANIFEST_JSON).read_text(encoding="utf-8")
        assert not any(k in text for k in ("started", "finished", "created_at", "utc_now"))

    def test_output_ordering_is_stable_and_sorted(self, real_model):
        s = rows(real_model.out / OUT_SUBDIR / TABLE_FILES["fact_dining_session"])
        assert [r["session_key"] for r in s] == sorted(r["session_key"] for r in s)
        v = rows(real_model.out / OUT_SUBDIR / TABLE_FILES["fact_daily_volume"])
        assert [(r["service_date"], r["population"]) for r in v] == sorted((r["service_date"], r["population"]) for r in v)
        w = rows(real_model.out / OUT_SUBDIR / TABLE_FILES["fact_weather"])
        assert [r["obs_time_utc"] for r in w] == sorted(r["obs_time_utc"] for r in w)

    def test_processes_with_different_hash_seeds_and_directories_agree(self, tmp_path, real_validation):
        outs = []
        for seed, cwd in (("3", REPO), ("8675309", tmp_path)):
            out = tmp_path / f"seed{seed}"
            for sub in ("staging", "validation"):
                shutil.copytree(real_validation.out / sub, out / sub)
            env = {**os.environ, "PYTHONHASHSEED": seed, "PYTHONPATH": str(REPO)}
            code = ("import sys; from pathlib import Path; from src.config import load_config; from src.model.build import run_model; "
                    f"r = run_model(load_config(Path(r'{REPO}') / 'config'), Path(r'{out}')); sys.exit(0 if r.core_status == 'BUILT' else 4)")
            done = subprocess.run([sys.executable, "-c", code], cwd=cwd, env=env, capture_output=True, text=True, timeout=180)
            assert done.returncode == 0, done.stderr
            outs.append({n: sha(out / OUT_SUBDIR / n) for n in DETERMINISTIC_FILES})
        assert outs[0] == outs[1], {n: 1 for n in outs[0] if outs[0][n] != outs[1][n]}


# ---- missing or corrupt inputs ------------------------------------------------------------------------------------------------------------------
class TestInputsAreVerified:
    def test_a_missing_validation_summary_stops_the_model(self, model_copy, cfg):
        (model_copy / "validation" / "validation_summary.json").unlink()
        res = run_model(cfg, model_copy)
        assert res.core_status == "BLOCKED" and "validation has not run" in res.error and not (model_copy / OUT_SUBDIR / TABLE_FILES["fact_dining_session"]).exists()

    @pytest.mark.parametrize("name", ["session_validation_status.csv", "event_validation_status.csv", "quarantine_manifest.csv", "validation_issues.csv", "service_day_volume.csv"])
    def test_an_altered_validation_file_is_detected_by_checksum(self, model_copy, cfg, name):
        p = model_copy / "validation" / name
        p.write_bytes(p.read_bytes() + b" ")
        res = run_model(cfg, model_copy)
        assert res.core_status == "BLOCKED" and f"{name} does not match the SHA-256 recorded by validation" in res.error

    def test_a_missing_validation_file_stops_the_model(self, model_copy, cfg):
        (model_copy / "validation" / "session_validation_status.csv").unlink()
        assert "session_validation_status.csv is missing" in run_model(cfg, model_copy).error

    def test_validation_computed_on_other_staging_tables_is_refused(self, model_copy, cfg):
        p = model_copy / "validation" / "validation_summary.json"
        summary = json.loads(p.read_text(encoding="utf-8"))
        summary["staging_table_sha256"][EVENTS_CSV] = "0" * 64
        p.write_text(json.dumps(summary), encoding="utf-8")
        assert "different staging tables" in run_model(cfg, model_copy).error

    def test_an_altered_staging_table_stops_the_model_via_the_verified_loader(self, model_copy, cfg):
        p = model_copy / "staging" / EVENTS_CSV
        p.write_bytes(p.read_bytes().replace(b"koti2", b"koti3", 1))
        res = run_model(cfg, model_copy)
        assert res.core_status == "BLOCKED" and "staging is not usable" in res.error and "SHA-256" in res.error

    def test_a_blocked_validation_is_not_modelled(self, model_copy, cfg):
        p = model_copy / "validation" / "validation_summary.json"
        summary = json.loads(p.read_text(encoding="utf-8"))
        summary["core_status"] = "BLOCKED"
        p.write_text(json.dumps(summary), encoding="utf-8")
        assert "validation reports the core lane as BLOCKED" in run_model(cfg, model_copy).error

    def test_dispositions_that_do_not_cover_the_staged_events_are_refused(self, model_copy, cfg):
        p = model_copy / "validation" / "event_validation_status.csv"
        lines = p.read_text(encoding="utf-8").splitlines(keepends=True)
        p.write_text("".join(lines[:-1]), encoding="utf-8")
        resign(model_copy, "event_validation_status.csv")
        assert "does not list exactly the staged events" in run_model(cfg, model_copy).error

    def test_an_unknown_disposition_is_refused(self, model_copy, cfg):
        p = model_copy / "validation" / "event_validation_status.csv"
        p.write_text(p.read_text(encoding="utf-8").replace(",MODELLABLE,", ",KEEPER,", 1), encoding="utf-8")
        resign(model_copy, "event_validation_status.csv")
        assert "unknown dispositions" in run_model(cfg, model_copy).error

    def test_the_loader_raises_a_model_input_error(self, tmp_path):
        with pytest.raises(ModelInputError, match="staging is not usable"):
            load_model_inputs(tmp_path)

    def test_a_failed_run_removes_stale_canonical_tables(self, model_copy, cfg):
        assert run_model(cfg, model_copy).core_status == "BUILT" and all((model_copy / OUT_SUBDIR / n).exists() for n in DETERMINISTIC_FILES)
        (model_copy / "validation" / "validation_summary.json").unlink()
        run_model(cfg, model_copy)
        assert not any((model_copy / OUT_SUBDIR / n).exists() for n in DETERMINISTIC_FILES), "a stale canonical table must never look current"


# ---- a consistent forgery is caught by the independent reconstruction ---------------------------------------------------------------------------
class TestControlFailureStopsAndReports:
    def test_a_forged_wp4_weight_blocks_the_model_and_names_the_session(self, model_copy, cfg):
        p = model_copy / "validation" / "session_validation_status.csv"
        text = p.read_text(encoding="utf-8").splitlines(keepends=True)
        header = text[0].strip().split(",")
        idx = header.index("rule_weight_sum_g")
        target = next(i for i, l in enumerate(text[1:], 1) if l.startswith("session1006|non_registered_export,"))
        cells = text[target].rstrip("\n").split(",")
        original = cells[idx]
        cells[idx] = str(int(original) + 1)
        text[target] = ",".join(cells) + "\n"
        p.write_text("".join(text), encoding="utf-8")
        resign(model_copy, "session_validation_status.csv")
        res = run_model(cfg, model_copy)
        assert res.core_status == "BLOCKED" and "M10" in res.error
        ctrl = {r["session_key"]: r for r in rows(model_copy / OUT_SUBDIR / SESSION_CONTROL_CSV)}
        bad = ctrl["session1006|non_registered_export"]
        assert bad["weight_control"] == "MISMATCH" and int(bad["wp4_rule_weight_sum_g"]) == int(original) + 1 and int(bad["canonical_weight_g"]) == int(original)
        assert [r["session_key"] for r in ctrl.values() if r["weight_control"] == "MISMATCH"] == ["session1006|non_registered_export"], "exactly the tampered session"
        assert not any((model_copy / OUT_SUBDIR / TABLE_FILES[t.name]).exists() for t in schema.TABLES), "a blocked model publishes no canonical rows"
        assert (model_copy / OUT_SUBDIR / CONTROL_CSV).exists() and (model_copy / OUT_SUBDIR / MANIFEST_JSON).exists()

    def test_a_forged_disposition_that_disagrees_with_the_validation_summary_blocks(self, model_copy, cfg):
        p = model_copy / "validation" / "event_validation_status.csv"
        p.write_text(p.read_text(encoding="utf-8").replace(",MODELLABLE,", ",DUPLICATE_EXCLUDED,", 1), encoding="utf-8")
        resign(model_copy, "event_validation_status.csv")
        res = run_model(cfg, model_copy)
        assert res.core_status == "BLOCKED" and "M04" in res.error

    def test_a_forged_quarantine_list_is_refused(self, model_copy, cfg):
        p = model_copy / "validation" / "quarantine_manifest.csv"
        lines = [l for l in p.read_text(encoding="utf-8").splitlines(keepends=True) if not l.startswith("session_key,session3222|registered_export,")]
        p.write_text("".join(lines), encoding="utf-8")
        resign(model_copy, "quarantine_manifest.csv")
        assert "disagree about which session keys are quarantined" in run_model(cfg, model_copy).error


# ---- weather is context: damage blocks weather only ---------------------------------------------------------------------------------------------
class TestWeatherLaneIsIndependent:
    def test_a_damaged_weather_table_blocks_fact_weather_but_not_the_core_model(self, model_copy, cfg):
        p = model_copy / "staging" / WEATHER_CSV
        p.write_bytes(p.read_bytes() + b"x")
        res = run_model(cfg, model_copy)
        assert res.core_status == "BUILT" and res.weather_status == "BLOCKED"
        assert not (model_copy / OUT_SUBDIR / TABLE_FILES["fact_weather"]).exists() and (model_copy / OUT_SUBDIR / TABLE_FILES["fact_dining_session"]).exists()
        s = rows(model_copy / OUT_SUBDIR / TABLE_FILES["fact_dining_session"])
        assert {r["weather_join_status"] for r in s} == {"WEATHER_BLOCKED", "NOT_ATTEMPTED_QUARANTINED"} and not any(r["weather_matched"] == "true" for r in s)
        assert sum(r["core_ready"] == "true" for r in s) == 1697, "weather never enters readiness"

    def test_validation_reporting_blocked_weather_is_respected(self, model_copy, cfg):
        p = model_copy / "validation" / "validation_summary.json"
        summary = json.loads(p.read_text(encoding="utf-8"))
        summary["weather_status"] = "BLOCKED"
        p.write_text(json.dumps(summary), encoding="utf-8")
        res = run_model(cfg, model_copy)
        assert res.core_status == "BUILT" and res.weather_status == "BLOCKED" and not (model_copy / OUT_SUBDIR / TABLE_FILES["fact_weather"]).exists()


# ---- static guarantees ------------------------------------------------------------------------------------------------------------------------
def module_trees():
    for p in sorted(MODEL_DIR.glob("*.py")):
        yield p, ast.parse(p.read_text(encoding="utf-8"))


def imports(tree) -> set[str]:
    mods: set[str] = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            mods |= {a.name for a in n.names}
        if isinstance(n, ast.ImportFrom) and n.module:
            mods.add(n.module)
            mods |= {f"{n.module}.{a.name}" for a in n.names}
    return mods


class TestModelNeverReadsRawData:
    FORBIDDEN = {"tarfile", "zipfile", "shutil", "glob", "socket", "requests", "urllib", "http"}
    FORBIDDEN_MODULES = {"src.ingest.handoff", "src.ingest.flavoria", "src.ingest.retrieval", "src.ingest.requests_client", "src.ingest.snapshot", "src.ingest.preserve",
                         "src.ingest.ingest", "src.ingest.http", "src.stage.stage", "src.stage.events", "src.stage.components"}

    def test_no_file_access_or_network_library_is_imported(self):
        for p, tree in module_trees():
            assert not {m.split(".")[0] for m in imports(tree)} & self.FORBIDDEN, p.name

    def test_no_module_imports_the_raw_readers_or_the_staging_builder(self):
        for p, tree in module_trees():
            assert not imports(tree) & self.FORBIDDEN_MODULES, f"{p.name}: {sorted(imports(tree) & self.FORBIDDEN_MODULES)}"

    def test_only_inputs_and_build_touch_the_filesystem(self):
        for p, tree in module_trees():
            calls = {n.func.attr for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
            names = {n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
            if p.name not in ("inputs.py", "build.py"):
                assert not calls & {"read_bytes", "read_text", "open", "write_text", "write_bytes", "unlink", "mkdir"} and "open" not in names, p.name

    def test_no_string_names_the_raw_directory(self):
        for p, tree in module_trees():
            docstrings = {id(n.body[0].value) for n in ast.walk(tree) if isinstance(n, (ast.Module, ast.FunctionDef, ast.ClassDef)) and n.body
                          and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant)}
            strings = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docstrings]
            assert not [s for s in strings if "data/raw" in s or "data\\raw" in s or s in ("data", "flavoria")], p.name

    def test_the_model_succeeds_with_no_raw_directory_and_reads_only_staging_and_validation(self, model_copy, cfg, monkeypatch):
        assert not (model_copy / "data").exists() and not (model_copy.parent / "data").exists()
        opened: list[str] = []
        real_open = Path.open

        def spy(self, *a, **k):
            opened.append(str(self))
            return real_open(self, *a, **k)

        monkeypatch.setattr(Path, "open", spy)
        assert run_model(cfg, model_copy).core_status == "BUILT"
        reads = [p for p in opened if not p.startswith(str(model_copy / OUT_SUBDIR))]
        allowed = (str(model_copy / "staging"), str(model_copy / "validation"))
        assert reads and all(p.startswith(allowed) for p in reads), [p for p in reads if not p.startswith(allowed)]


# ---- schema and documentation ---------------------------------------------------------------------------------------------------------------
class TestSchemaAndDocumentation:
    def test_every_column_is_fully_specified(self):
        for t in schema.TABLES:
            assert len(set(t.column_names)) == len(t.column_names), t.name
            assert set(t.key) <= set(t.column_names)
            for c in t.columns:
                assert c.dtype in {"text", "integer", "real", "boolean", "date", "timestamp_local", "timestamp_utc"} and c.cls in {"OBSERVED", "DERIVED", "VALIDATION", "PROVENANCE"}
                assert c.meaning and c.rule and c.downstream, f"{t.name}.{c.name}"

    def test_the_data_dictionary_contains_the_generated_model_section_exactly(self):
        doc = (REPO / "docs" / "data_dictionary.md").read_text(encoding="utf-8")
        assert schema.render_markdown().strip() in doc, "regenerate section 12: python -m src.model.schema"

    def test_the_documentation_states_what_the_derived_weight_is_not(self):
        doc = (REPO / "docs" / "data_dictionary.md").read_text(encoding="utf-8")
        assert "NOT consumed quantity, NOT food waste, NOT actual intake" in doc and "rule_weight_sum_g" in doc and "reconciliation control" in doc

    def test_the_manifest_matches_the_schema(self, real_model):
        m = json.loads((real_model.out / OUT_SUBDIR / MANIFEST_JSON).read_text(encoding="utf-8"))
        assert set(m["tables"]) == {t.name for t in schema.TABLES}
        for t in schema.TABLES:
            assert m["tables"][t.name]["columns"] == list(t.column_names) and m["tables"][t.name]["grain"] == t.grain
