"""docs/pipeline.md, the decision log, the data dictionary and the CLI docstring must state what the code does."""
from __future__ import annotations

import re
from pathlib import Path

from src.pipeline import run as runmod
from src.pipeline.exit_codes import EXIT_TABLE
from src.pipeline.report import ALL_FILES
from src.pipeline.stages import STAGE_ORDER

DOCS = Path(__file__).resolve().parents[1] / "docs"
PIPELINE = (DOCS / "pipeline.md").read_text(encoding="utf-8")


def test_every_stage_output_file_control_and_status_is_documented():
    for stage in STAGE_ORDER:
        assert f"`{stage}`" in PIPELINE, stage
    for name in ALL_FILES:
        assert name in PIPELINE, name
    for i in range(1, 12):
        assert f"P{i:02d}" in PIPELINE
    for status in ("PASSED", "FAILED", "BLOCKED", "INVALIDATED", "NOT_RUN", "REUSED"):
        assert status in PIPELINE


def test_the_documented_exit_code_table_equals_the_code():
    rows = {int(m.group(1)): m.group(2) for m in re.finditer(r"^\| (\d+) \| ([A-Za-z]+) \|", PIPELINE, re.M)}
    assert rows == {int(code): ("retired" if name == "RETIRED" else name) for code, name, _ in EXIT_TABLE}


def test_the_cli_docstring_lists_every_exit_code():
    doc = runmod.__doc__
    for code, name, _ in EXIT_TABLE:
        assert re.search(rf"^\s+{int(code)}\s+", doc, re.M), code


def test_the_runtime_placeholder_was_replaced_with_measured_numbers():
    assert "RUNTIME_TABLE" not in PIPELINE and re.search(r"\| total \|", PIPELINE)


def test_decisions_d64_to_d68_are_logged_in_the_seven_field_format():
    log = (DOCS / "decision_log.md").read_text(encoding="utf-8")
    for n in range(64, 69):
        block = log[log.index(f"## D{n}."):].split("\n## ")[0]
        for field in ("Decision.", "Evidence.", "Alternatives tested.", "Chosen approach.", "Why.", "Business impact.", "Residual uncertainty."):
            assert f"**{field}**" in block, (n, field)


def test_the_data_dictionary_documents_the_pipeline_outputs():
    text = (DOCS / "data_dictionary.md").read_text(encoding="utf-8")
    section = text[text.index("## 15. Pipeline outputs"):]
    for name in ALL_FILES:
        assert name in section
