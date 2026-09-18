"""Offline execution, raw immutability, determinism and idempotency."""
from __future__ import annotations

import ast
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from src.ingest import preserve
from src.ingest.ingest import run_ingestion
from src.ingest.manifest import DETERMINISTIC_FILES
from src.ingest.model import LaneOutcome
from src.pipeline import run as run_module

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "src"
NETWORK_MODULES = {"src/ingest/requests_client.py", "src/ingest/retrieval.py", "src/ingest/http.py", "src/pipeline/fetch.py"}


def imports_of(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
            names |= {f"{node.module}.{a.name}" for a in node.names}     # 'from pkg import submodule' imports pkg.submodule
    return names


# ---- offline: proven three ways -----------------------------------------------------------------------------------------------------
class TestOfflineExecution:
    def test_a_normal_run_completes_with_every_socket_operation_forbidden(self, cfg, raw_repo, tmp_path, no_network):
        r, _ = run_ingestion(cfg, raw_repo, tmp_path / "out")
        assert (r.core_outcome, r.context_outcome) == (LaneOutcome.OK, LaneOutcome.OK)

    def test_only_the_explicit_retrieval_modules_import_requests(self):
        offenders = []
        for p in SRC.rglob("*.py"):
            rel = p.relative_to(REPO).as_posix()
            if any(m == "requests" or m.startswith("requests.") for m in imports_of(p)) and rel != "src/ingest/requests_client.py":
                offenders.append(rel)
        assert offenders == [], f"only src/ingest/requests_client.py may import requests: {offenders}"

    def test_the_normal_run_never_imports_retrieval_code(self):
        """Follow every import from src.pipeline.run and prove none of them is a network module."""
        seen: set[str] = set()
        todo = ["src/pipeline/run.py"]
        while todo:
            rel = todo.pop()
            if rel in seen:
                continue
            seen.add(rel)
            for mod in imports_of(REPO / rel):
                if mod.startswith("src"):
                    candidate = mod.replace(".", "/")
                    for c in (f"{candidate}.py", f"{candidate}/__init__.py"):
                        if (REPO / c).exists():
                            todo.append(c)
        assert seen.isdisjoint(NETWORK_MODULES), f"normal run reaches network code: {sorted(seen & NETWORK_MODULES)}"
        assert "src/ingest/ingest.py" in seen and "src/ingest/flavoria.py" in seen      # the traversal did follow the real imports

    def test_the_run_works_with_the_requests_library_made_unimportable(self, tmp_path):
        code = ("import sys; sys.modules['requests'] = None\n"
                "from src.pipeline.run import main\n"
                f"sys.exit(main(['--stages','ingest','--out',r'{tmp_path / 'o'}']))")
        r = subprocess.run([sys.executable, "-c", code], cwd=REPO, capture_output=True, text=True, timeout=120)
        assert r.returncode == 0, r.stderr


# ---- raw preservation ------------------------------------------------------------------------------------------------------------------
class TestRawPreservation:
    def test_a_run_leaves_the_raw_tree_byte_and_mtime_identical(self, cfg, raw_repo, tmp_path):
        before = preserve.capture(raw_repo / "data" / "raw")
        r, _ = run_ingestion(cfg, raw_repo, tmp_path / "out")
        assert before.diff(preserve.capture(raw_repo / "data" / "raw")) == [] and r.raw_unchanged is True

    def test_outputs_inside_the_raw_tree_are_refused(self, cfg, raw_repo):
        with pytest.raises(ValueError, match="inside the immutable raw tree"):
            run_ingestion(cfg, raw_repo, raw_repo / "data" / "raw" / "sneaky")

    def test_a_write_into_raw_during_a_run_is_detected_and_fails_the_core_lane(self, cfg, raw_repo, tmp_path, monkeypatch):
        from src.ingest import ingest as ing
        real = ing.verify_flavoria

        def naughty(c, root):
            (root / "data" / "raw" / "flavoria" / "stray.txt").write_text("written by a buggy stage")
            return real(c, root)

        monkeypatch.setattr(ing, "verify_flavoria", naughty)
        r, _ = run_ingestion(cfg, raw_repo, tmp_path / "out")
        assert r.raw_unchanged is False and r.core_outcome is LaneOutcome.FAILED
        assert any("raw preservation violated" in m.text and "stray.txt" in m.text for m in r.messages)


# ---- determinism and idempotency ---------------------------------------------------------------------------------------------------------
def output_hashes(out: Path) -> dict[str, str]:
    d = out / "ingestion"
    return {n: hashlib.sha256((d / n).read_bytes()).hexdigest() for n in DETERMINISTIC_FILES}


class TestDeterminism:
    def test_two_runs_give_identical_outputs(self, cfg, raw_repo, tmp_path):
        _, h1 = run_ingestion(cfg, raw_repo, tmp_path / "a")
        _, h2 = run_ingestion(cfg, raw_repo, tmp_path / "b")
        assert h1 == h2 == output_hashes(tmp_path / "a") == output_hashes(tmp_path / "b")

    def test_rerunning_into_the_same_directory_does_not_duplicate_or_change_anything(self, cfg, raw_repo, tmp_path):
        out = tmp_path / "out"
        run_ingestion(cfg, raw_repo, out)
        first = output_hashes(out)
        rows_first = (out / "ingestion" / "raw_artifact_manifest.csv").read_text().count("\n")
        run_ingestion(cfg, raw_repo, out)
        run_ingestion(cfg, raw_repo, out)
        assert output_hashes(out) == first
        assert (out / "ingestion" / "raw_artifact_manifest.csv").read_text().count("\n") == rows_first == 22     # header + 21, never appended

    def test_outputs_are_independent_of_hash_seed_and_working_directory(self, tmp_path):
        results = []
        for seed, cwd in (("1", REPO), ("98765", tmp_path)):
            out = tmp_path / f"out{seed}"
            env = {**os.environ, "PYTHONHASHSEED": seed, "PYTHONPATH": str(REPO)}
            r = subprocess.run([sys.executable, "-m", "src.pipeline.run", "--stages", "ingest", "--out", str(out)], cwd=cwd, env=env,
                               capture_output=True, text=True, timeout=120)
            assert r.returncode == 0, r.stderr
            results.append(output_hashes(out))
        assert results[0] == results[1]

    def test_no_wall_clock_value_leaks_into_deterministic_outputs(self, cfg, raw_repo, tmp_path):
        run_ingestion(cfg, raw_repo, tmp_path / "out")
        text = "".join((tmp_path / "out" / "ingestion" / n).read_text() for n in DETERMINISTIC_FILES)
        assert "started_at" not in text and "finished_at" not in text and "run_id" not in text
        import re
        assert not re.search(r"2026-09-(19|2\d)|2026-1\d", text), "only pinned retrieval dates (2026-09-18) may appear"

    def test_the_run_record_is_the_only_time_dependent_file(self, tmp_path):
        out = tmp_path / "out"
        assert run_module.main(["--stages", "ingest", "--out", str(out)]) == 0
        rec = json.loads((out / "ingestion" / "ingestion_run.json").read_text())
        assert rec["network_used"] is False and rec["started_at"] and rec["run_id"].startswith("ingest-")
        assert rec["deterministic_output_sha256"] == output_hashes(out)
        assert "ingestion_run.json" not in DETERMINISTIC_FILES

    def test_the_real_repository_raw_files_match_their_pins_after_a_real_run(self, tmp_path, cfg):
        """The committed data/raw itself (not a copy) verifies and is untouched by the run."""
        before = preserve.capture(REPO / "data" / "raw")
        r, _ = run_ingestion(cfg, REPO, tmp_path / "out")
        assert r.core_outcome is LaneOutcome.OK and r.context_outcome is LaneOutcome.OK and r.raw_unchanged
        assert before.diff(preserve.capture(REPO / "data" / "raw")) == []
