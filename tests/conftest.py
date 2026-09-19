"""Shared fixtures."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

from src.config import Config, load_config

REPO = Path(__file__).resolve().parents[1]
GOLDEN_DIR = REPO / "tests" / "golden"


@pytest.fixture(scope="session")
def repo() -> Path:
    return REPO


@pytest.fixture(scope="session")
def cfg() -> Config:
    return load_config(REPO / "config")


@pytest.fixture(scope="session")
def golden() -> dict:
    return yaml.safe_load((GOLDEN_DIR / "golden_values.yml").read_text(encoding="utf-8"))


class ConfigCopy:
    """A writable copy of config/ with a helper that edits one file by exact text replacement."""

    def __init__(self, directory: Path):
        self.dir = directory

    def edit(self, filename: str, old: str, new: str) -> None:
        p = self.dir / filename
        text = p.read_text(encoding="utf-8")
        assert old in text, f"test setup error: {old!r} not found in {filename}"
        p.write_text(text.replace(old, new, 1), encoding="utf-8")


@pytest.fixture()
def config_copy(tmp_path: Path) -> ConfigCopy:
    dst = tmp_path / "config"
    shutil.copytree(REPO / "config", dst)
    return ConfigCopy(dst)


@pytest.fixture()
def raw_repo(tmp_path: Path) -> Path:
    """A throwaway repository root holding a COPY of data/raw, so tests can damage raw files safely."""
    root = tmp_path / "repo"
    shutil.copytree(REPO / "data" / "raw", root / "data" / "raw")
    return root


@pytest.fixture()
def no_network(monkeypatch):
    """Any attempt to open a network connection fails the test. Proves offline execution."""
    import socket

    def refuse(*args, **kwargs):
        raise AssertionError("network access attempted during an offline test")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)


class RealStaging:
    """One real ingestion + staging run over the committed data, shared by many tests (read-only)."""

    def __init__(self, out, result, handoff, events, weather):
        self.out, self.result, self.handoff, self.events, self.weather = out, result, handoff, events, weather


@pytest.fixture(scope="session")
def real_staging(tmp_path_factory, cfg):
    import pandas as pd

    from src.ingest.handoff import VerifiedReader, load_handoff
    from src.ingest.ingest import run_ingestion
    from src.stage.stage import run_staging

    out = tmp_path_factory.mktemp("real_staging")
    run_ingestion(cfg, REPO, out)
    handoff = load_handoff(out / "ingestion" / "staging_handoff.json")
    result = run_staging(cfg, VerifiedReader(REPO, handoff), out)
    read = lambda n: pd.read_csv(out / "staging" / n, dtype=str, keep_default_na=False)      # every cell as text: no float surprises
    return RealStaging(out, result, handoff, read("stg_weighing_event.csv"), read("stg_weather_observation.csv"))


class RealValidation:
    """Validation run over the shared real staging output (read-only for tests; tests that damage things copy `out` first)."""

    def __init__(self, out, result):
        self.out, self.result = out, result
        self.issues = result.issues
        self.checks = {c.check_id: c for c in result.checks}


@pytest.fixture(scope="session")
def real_validation(real_staging, cfg):
    from src.validate.validate import run_validation

    return RealValidation(real_staging.out, run_validation(cfg, real_staging.out))


class RealModel:
    """Canonical model built over the shared real validation output (read-only for tests)."""

    def __init__(self, out, result):
        self.out, self.result = out, result
        self.tables = result.tables
        self.checks = {c.check_id: c for c in result.checks}


@pytest.fixture(scope="session")
def real_model(real_validation, cfg):
    from src.model.build import run_model

    return RealModel(real_validation.out, run_model(cfg, real_validation.out))


class RealMetrics:
    """Metrics computed over the shared real canonical model (read-only for tests)."""

    def __init__(self, out, result):
        self.out, self.result = out, result
        self.rows = {r["metric_id"]: r for r in result.rows}
        self.checks = {c.check_id: c for c in result.checks}


@pytest.fixture(scope="session")
def real_metrics(real_model, cfg):
    from src.metrics.evaluate import run_metrics

    return RealMetrics(real_model.out, run_metrics(cfg, real_model.out))


class RealSensitivity:
    """The sensitivity stage run over the shared real canonical model (read-only for tests)."""

    def __init__(self, out, result):
        self.out, self.result = out, result
        self.analysis = result.analysis
        self.results = result.analysis.results


@pytest.fixture(scope="session")
def real_sensitivity(real_metrics, cfg):
    from src.sensitivity.stage import run_sensitivity

    return RealSensitivity(real_metrics.out, run_sensitivity(cfg, real_metrics.out))
