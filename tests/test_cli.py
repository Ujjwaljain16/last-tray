"""The command line must never report success for work it has not done, and must never touch the network."""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def run(*args: str, cwd=REPO, module="src.pipeline.run"):
    return subprocess.run([sys.executable, "-m", module, *args], cwd=cwd, capture_output=True, text=True, timeout=120)


def fake_repo(tmp_path: Path, *, drop: tuple[str, ...] = ()) -> Path:
    """A repo root with a copy of data/raw, optionally missing some files."""
    root = tmp_path / "repo"
    shutil.copytree(REPO / "data" / "raw", root / "data" / "raw")
    for rel in drop:
        (root / rel).unlink()
    return root


def test_help_lists_the_documented_options_and_the_offline_promise():
    r = run("--help")
    assert r.returncode == 0
    for option in ("--stages", "--repo-root", "--out", "--config-dir", "--check-config"):
        assert option in r.stdout
    assert "not consumption" in r.stdout and "OFFLINE" in r.stdout
    assert "--refresh-weather" not in r.stdout and "--offline" not in r.stdout, "there is no network flag on the offline run"


def test_check_config_succeeds_and_states_the_locked_decisions():
    r = run("--check-config")
    assert r.returncode == 0
    assert "Configuration OK" in r.stdout
    assert "registered-export population (primary)" in r.stdout
    assert "file-specific override" in r.stdout and "source_confirmed=False" in r.stdout
    assert "Flavoria Lunch Line Waste [BLOCKED]" in r.stdout and "CC-BY-4.0" in r.stdout


def test_stages_ingest_succeeds_offline_and_writes_only_ingestion_outputs(tmp_path):
    out = tmp_path / "out"
    r = run("--stages", "ingest", "--out", str(out))
    assert r.returncode == 0, r.stderr
    assert "core lane   : OK" in r.stdout and "context lane: OK" in r.stdout and "21 VERIFIED" in r.stdout
    assert {p.name for p in out.iterdir()} == {"ingestion"}
    assert (out / "ingestion" / "staging_handoff.json").is_file()


def test_stages_stage_runs_ingestion_then_staging_and_reports_the_counts(tmp_path):
    out = tmp_path / "out"
    r = run("--stages", "stage", "--out", str(out))
    assert r.returncode == 0, r.stderr
    assert "Staging (verified reads only)" in r.stdout and "events staged: 12,284" in r.stdout and "weather observations staged: 4,516" in r.stdout
    assert "3,343 ids / 3,345 (session_id, population) keys" in r.stdout
    assert {p.name for p in out.iterdir()} == {"ingestion", "staging"}
    assert (out / "staging" / "stg_weighing_event.csv").is_file() and (out / "staging" / "staging_summary.json").is_file()


def test_full_run_is_honest_that_later_stages_do_not_exist_yet(tmp_path):
    out = tmp_path / "out"
    r = run("--out", str(out))
    assert r.returncode == 3, "a run that cannot complete every stage must not exit 0"
    assert "not implemented yet" in r.stderr and "Outputs cover ingestion and staging only" in r.stderr
    assert {p.name for p in out.iterdir()} == {"ingestion", "staging"}, "no validation, model, metrics or evidence files may appear before those stages exist"


def test_missing_core_source_exits_4_names_the_fetch_command_and_downloads_nothing(tmp_path):
    root = fake_repo(tmp_path, drop=("data/raw/flavoria/dataset_csv.tar",))
    r = run("--stages", "ingest", "--repo-root", str(root), "--out", str(tmp_path / "out"))
    assert r.returncode == 4
    assert "python -m src.pipeline.fetch --source" in r.stderr and "FAILED" in r.stderr
    assert not (root / "data" / "raw" / "flavoria" / "dataset_csv.tar").exists(), "the run must never fetch what is missing"


def test_missing_weather_exits_6_and_leaves_core_usable(tmp_path):
    root = fake_repo(tmp_path, drop=("data/raw/weather/fmi_100949_20201012_20201018.xml",))
    r = run("--stages", "ingest", "--repo-root", str(root), "--out", str(tmp_path / "out"))
    assert r.returncode == 6
    assert "core lane   : OK" in r.stdout and "context lane: BLOCKED" in r.stdout
    assert "Core outputs are unaffected" in r.stderr
    assert not (root / "data" / "raw" / "weather" / "fmi_100949_20201012_20201018.xml").exists()


def test_corrupt_source_exits_4_and_is_not_repaired(tmp_path):
    root = fake_repo(tmp_path)
    p = root / "data" / "raw" / "flavoria" / "dataset_csv.tar"
    p.write_bytes(p.read_bytes()[:-2048])
    before = p.read_bytes()
    r = run("--stages", "ingest", "--repo-root", str(root), "--out", str(tmp_path / "out"))
    assert r.returncode == 4 and p.read_bytes() == before
    assert "SIZE_MISMATCH" in r.stdout or "SIZE_MISMATCH" in r.stderr or "not verified" in r.stdout


def test_bad_configuration_exits_2_with_a_useful_message(tmp_path):
    r = run("--config-dir", str(tmp_path))         # empty directory: every file missing
    assert r.returncode == 2
    assert "FAILED: configuration" in r.stderr and ".yml" in r.stderr


def test_fetch_command_exists_and_documents_that_it_is_the_only_network_command():
    r = run("--help", module="src.pipeline.fetch")
    assert r.returncode == 0 and "--source" in r.stdout and "--refresh" in r.stdout and "--print-pins" in r.stdout
    assert "Never edits pins" in r.stdout


def test_a_core_failure_removes_stale_staging_tables_and_exits_4(tmp_path):
    root = fake_repo(tmp_path)
    out = tmp_path / "out"
    assert run("--stages", "stage", "--repo-root", str(root), "--out", str(out)).returncode == 0
    assert (out / "staging" / "stg_weighing_event.csv").is_file()
    (root / "data" / "raw" / "flavoria" / "dataset_csv.tar").unlink()
    r = run("--stages", "stage", "--repo-root", str(root), "--out", str(out))
    assert r.returncode == 4
    assert not (out / "staging" / "stg_weighing_event.csv").exists(), "a stale staging table must not survive a failed run"


def test_a_weather_problem_never_stops_core_staging(tmp_path):
    root = fake_repo(tmp_path, drop=("data/raw/weather/fmi_100949_20201012_20201018.xml",))
    out = tmp_path / "out"
    r = run("--stages", "stage", "--repo-root", str(root), "--out", str(out))
    assert r.returncode == 6 and "Core outputs are unaffected" in r.stderr
    assert (out / "staging" / "stg_weighing_event.csv").is_file(), "core staging must be produced even though weather is blocked"
    assert not (out / "staging" / "stg_weather_observation.csv").exists()


def test_a_weather_failure_removes_only_the_stale_weather_table(tmp_path):
    root = fake_repo(tmp_path)
    out = tmp_path / "out"
    assert run("--stages", "stage", "--repo-root", str(root), "--out", str(out)).returncode == 0
    (root / "data" / "raw" / "weather" / "fmi_100949_20201012_20201018.xml").unlink()
    assert run("--stages", "stage", "--repo-root", str(root), "--out", str(out)).returncode == 6
    assert (out / "staging" / "stg_weighing_event.csv").is_file() and not (out / "staging" / "stg_weather_observation.csv").exists()
