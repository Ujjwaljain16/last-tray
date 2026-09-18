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
