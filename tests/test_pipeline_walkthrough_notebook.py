"""The evaluator walkthrough notebook is read-only: it displays committed pipeline outputs and computes nothing of its own."""
from __future__ import annotations

import ast
import contextlib
import csv
import io
import json
import os
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
NOTEBOOK = REPO / "notebooks" / "02_pipeline_walkthrough.ipynb"
NOTE = "This notebook is an evaluator walkthrough only; the canonical computations live in `src/` and are executed by `python -m src.pipeline.run --stages all`."


@pytest.fixture(scope="module")
def nb() -> dict:
    return json.loads(NOTEBOOK.read_text(encoding="utf-8"))


def code_cells(nb) -> list[dict]:
    return [c for c in nb["cells"] if c["cell_type"] == "code"]


def source(cell) -> str:
    return "".join(cell["source"])


def test_the_notebook_exists_and_is_a_concise_walkthrough_with_the_required_sections(nb):
    assert NOTEBOOK.is_file() and 15 <= len(nb["cells"]) <= 21
    # nbformat allows a cell's "source" to be either a list of lines or one string; normalise before splitting.
    headings = [line.strip() for c in nb["cells"] if c["cell_type"] == "markdown" for line in "".join(c["source"]).splitlines() if line.startswith("## ")]
    expected = ["Project question", "Source map summary", "Pipeline stages", "Validation summary", "Canonical business model summary", "Final evidence", "Sensitivity summary",
                "Known vs unknown", "Selected weight is not consumption, and consumption is not waste", "Where to look next"]
    assert len(headings) == len(expected) and all(e in h for h, e in zip(headings, expected)), headings


def test_the_notebook_ends_with_the_walkthrough_only_note(nb):
    last = "".join(nb["cells"][-1]["source"])
    assert NOTE in last


def test_every_output_file_and_image_the_notebook_refers_to_exists(nb):
    referenced = set()
    for c in code_cells(nb):
        referenced |= set(re.findall(r'(?:csv|js)\("([^"]+)"\)', source(c)))
    assert referenced, "the notebook must load committed outputs"
    missing = [r for r in sorted(referenced) if not (REPO / "outputs" / r).is_file()]
    assert not missing, missing
    images = [m for c in nb["cells"] if c["cell_type"] == "markdown" for m in re.findall(r"!\[[^\]]*\]\(([^)]+)\)", "".join(c["source"]))]
    assert images and all((NOTEBOOK.parent / i).resolve().is_file() for i in images), images
    docs = [m for c in nb["cells"] if c["cell_type"] == "markdown" for m in re.findall(r"`((?:docs|src|config)/[\w./-]+)`", "".join(c["source"]))]
    assert docs and all((REPO / d).exists() for d in docs), [d for d in docs if not (REPO / d).exists()]


def test_the_notebook_reads_no_raw_data_and_imports_no_pipeline_logic(nb):
    body = NOTEBOOK.read_text(encoding="utf-8")
    assert "data/raw" not in body and "data\\\\raw" not in body and "dataset_csv" not in body
    for c in code_cells(nb):
        src = source(c)
        assert not re.search(r"^\s*(from|import)\s+src\b", src, re.M), "the notebook must not import pipeline code"
        assert "open(" not in src.replace("read_text(", "") and "tarfile" not in src and "requests" not in src and "urllib" not in src
        for path in re.findall(r'(?:csv|js)\("([^"]+)"\)', src):
            assert not path.startswith(("raw", "data")), path


def test_the_notebook_computes_no_metric_of_its_own(nb):
    banned = re.compile(r"\.(median|quantile|mean|sum|std|percentile)\(|np\.|numpy|\bround\(|\bsorted\(|/ ?\d")
    for c in code_cells(nb):
        src = source(c)
        assert not banned.search(src), src
        assert not re.search(r"\b(499|1039|1,039|1697|1,697|99\.88|97\.88)\b", src), "metric values must come from the outputs, never from the notebook code"


def test_displayed_headline_values_equal_metrics_csv(nb):
    with (REPO / "outputs" / "metrics" / "metrics.csv").open(newline="", encoding="utf-8") as fh:
        rows = {r["metric_id"]: r for r in csv.DictReader(fh)}
    shown = "\n".join("".join(o["data"]["text/plain"]) for c in code_cells(nb) for o in c["outputs"] if o["output_type"] == "execute_result")
    html = "\n".join("".join(o["data"].get("text/html", [])) for c in code_cells(nb) for o in c["outputs"] if o["output_type"] == "execute_result")
    for metric_id in ("M1", "M2", "M3", "M4", "M5", "S2", "W1"):
        assert rows[metric_id]["value_display"] in html, f"{metric_id} must show {rows[metric_id]['value_display']}"
        assert rows[metric_id]["metric_name"] in shown
    assert {"M1": "499 g", "M2": "1,039.6 g", "M5": "99.88%", "S2": "97.88%", "W1": "BLOCKED / SOURCE GAP"}.items() <= {k: rows[k]["value_display"] for k in rows}.items()
    assert rows["M3"]["value_display"].startswith("1,697") and rows["M4"]["value_display"].startswith("5")


def _execute(nb) -> list[str]:
    """Re-run the notebook's code cells against the committed outputs and return each cell's text output."""
    import pandas as pd
    ns: dict = {}
    results = []
    old = os.getcwd()
    os.chdir(NOTEBOOK.parent)
    try:
        for c in code_cells(nb):
            tree = ast.parse(source(c))
            last = ast.Expression(tree.body.pop().value) if tree.body and isinstance(tree.body[-1], ast.Expr) else None
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                exec(compile(tree, "<cell>", "exec"), ns)
                value = eval(compile(last, "<cell>", "eval"), ns) if last is not None else None
            results.append(buf.getvalue() + (str(value) if value is not None else ""))
    finally:
        os.chdir(old)
    return results


def test_the_embedded_outputs_equal_a_fresh_run_over_the_committed_outputs(nb):
    """A stale notebook is a defect: if a pipeline output changes, the embedded cell outputs must be regenerated."""
    fresh = _execute(nb)
    embedded = []
    for c in code_cells(nb):
        text = ""
        for o in c["outputs"]:
            text += "".join(o["text"]) if o["output_type"] == "stream" else "".join(o["data"]["text/plain"])
        embedded.append(text)
    assert [f.strip() for f in fresh] == [e.strip() for e in embedded]
