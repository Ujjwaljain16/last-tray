"""The assignment-facing documents must state what the artifacts contain, and must not drift from them.

These tests protect contracts (numbers, names, paths, forbidden claims), not prose formatting.
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
DOCS = REPO / "docs"


def text(path: str) -> str:
    return (REPO / path).read_text(encoding="utf-8")


def metrics() -> dict[str, dict[str, str]]:
    with (REPO / "outputs" / "metrics" / "metrics.csv").open(newline="", encoding="utf-8") as fh:
        return {r["metric_id"]: r for r in csv.DictReader(fh)}


def table_row(doc: str, metric_id: str) -> str:
    rows = [line for line in doc.splitlines() if line.startswith(f"| {metric_id} ")]
    assert len(rows) == 1, f"expected exactly one {metric_id} row, found {len(rows)}"
    return rows[0]


APPROVED = {"M1": "499 g", "M2": "1,039.6 g", "M3": "1,697", "M4": "5", "M5": "99.88%", "S2": "97.88%", "W1": "BLOCKED / SOURCE GAP"}


@pytest.mark.parametrize("doc", ["README.md", "docs/final_evidence.md"])
def test_headline_table_values_equal_the_metric_artifact_and_the_approved_baseline(doc):
    m = metrics()
    body = text(doc)
    for mid, approved in APPROVED.items():
        row = table_row(body, mid)
        name = m[mid]["metric_name"]
        assert name in row, f"{doc}: {mid} must use the approved name {name!r}"
        shown = m[mid]["value_display"].replace(" sessions", "").replace(" components", "")
        assert shown == approved, f"the metric artifact moved: {mid} is {shown}, approved {approved}"
        assert f"| {approved}" in row or f"| {approved} " in row, f"{doc}: {mid} value drifted from {approved}"
    assert "1,697 / 1,699" in table_row(body, "M5")


def test_the_headline_table_is_compact_and_lists_no_other_metric():
    body = text("docs/final_evidence.md")
    head = body.split("## Supporting evidence")[0]
    rows = [line for line in head.splitlines() if re.match(r"\| M\d ", line)]
    assert [r.split(" ")[1] for r in rows] == ["M1", "M2", "M3", "M4", "M5"]
    assert not re.search(r"\| S1 |\| S2D ", body.split("## Evidence interpretation")[0])


def test_the_judgement_states_the_approved_numbers_and_the_source_gap():
    body = text("docs/judgement_call.md")
    for needle in ("499 g", "1,039.6 g", "99.88%", "1,697", "BLOCKED", "SOURCE GAP", "not actual consumption", "tray-linked"):
        assert needle in body, needle
    for section in ("Decision / question", "Evidence", "What the evidence supports", "What the evidence does not support", "Critical missing evidence", "What we would ask for next",
                    "Why that evidence changes the future decision"):
        assert section in body, section


FORBIDDEN = [
    r"waste[d]?\s+(was|is|of|totalled|amounted)\s+[\d~]",
    r"\d[\d,.]*\s*(g|kg|%)\s+(of\s+)?(the\s+)?(food\s+)?(was\s+)?wasted",
    r"(estimated|estimate of|approximate)\s+(food\s+)?waste\s+(is|was|of)\s+\d",
    r"waste[- ]reduction\s+of\s+\d",
    r"(people|diners|customers|guests|staff)\s+(ate|consumed|wasted|left)\b",
    r"weather\s+(caused|drove|explains|led to)",
    r"(saves?|saved|savings of)\s+[\d$€£]",
    r"\bdemand\s+(was|is|rose|fell|increased|decreased)\b",
]
CLAIM_DOCS = ["README.md", "docs/final_evidence.md", "docs/judgement_call.md", "docs/demo_script.md", "docs/source_truth_decisions.md", "docs/source_map.md",
              "docs/known_unknowns_assumptions_limitations.md", "docs/assignment_traceability.md"]


@pytest.mark.parametrize("doc", CLAIM_DOCS)
def test_no_document_claims_waste_consumption_savings_demand_or_weather_causation(doc):
    body = text(doc)
    for pattern in FORBIDDEN:
        hit = re.search(pattern, body, re.I)
        assert not hit, f"{doc}: unsupported claim pattern {pattern!r}: {hit.group(0)!r}"


def test_generated_evidence_makes_no_waste_or_consumption_value_claim():
    """The generated metric and evidence tables may name waste only as BLOCKED, never give it a number."""
    m = metrics()
    assert m["W1"]["value"] == "" and m["W1"]["status"] == "BLOCKED"
    for name in ("outputs/evidence/evidence_matrix.csv", "outputs/evidence/uncertainty_register.csv", "outputs/metrics/metrics_report.md"):
        body = text(name)
        for pattern in FORBIDDEN[:4] + FORBIDDEN[5:6]:
            assert not re.search(pattern, body, re.I), (name, pattern)


def test_the_source_map_covers_the_five_required_sources_and_classes():
    body = text("docs/source_map.md")
    for source in ("FlavoriaFoodWeight1700", "FMI open data", "Flavoria Data Catalog", "Weigh & Dine documentation", "Lunch Line Waste documentation"):
        assert source in body, source
    for cls in ("primary measurement data", "weather enrichment", "contextual documentation", "source-gap documentation"):
        assert cls in body, cls
    header = next(line for line in body.splitlines() if line.startswith("| Source | Class"))
    for column in ("Information needed", "Key fields", "Grain", "Owner / publisher", "Authority", "Freshness / period", "Retrieval", "Licence / access", "Reliability",
                   "Known gaps", "Authoritative for the question?"):
        assert column in header, column
    assert "Problem → Questions → Information → Fields → Sources" in body


def test_the_source_truth_decisions_cover_every_required_fact_and_state_the_waste_gap():
    body = text("docs/source_truth_decisions.md")
    for heading in ("weighing event", "dining session", "population", "component", "clock", "weather observation", "waste"):
        assert re.search(rf"^## .*{heading}", body, re.I | re.M), heading
    assert "conceptually documented but not publicly accessible in the required usable form" in body
    assert "W1 remains BLOCKED / SOURCE GAP" in body


def test_the_known_unknown_document_has_exactly_the_four_buckets():
    body = text("docs/known_unknowns_assumptions_limitations.md")
    assert re.findall(r"^## ([A-Z]+)\b", body, re.M) == ["KNOWN", "UNKNOWN", "ASSUMPTION", "LIMITATION"]
    assumptions = body.split("## ASSUMPTION")[1].split("## LIMITATION")[0]
    for row in [line for line in assumptions.splitlines() if re.match(r"\| A\d+ ", line)]:
        assert row.count("|") == 7, "each assumption needs why it matters, evidence and a sensitivity result: " + row[:40]


def test_the_glossary_defines_the_required_terms_and_what_they_do_not_mean():
    body = text("docs/data_dictionary.md")
    section = body[body.index("## 16. Glossary"):]
    for term in ("Weighing event", "Component", "Session", "Session key", "Population", "Derived selected meal weight", "Core-ready", "Warn-free", "Quarantine", "Observed volume",
                 "Weather observation"):
        assert f"**{term}**" in section, term
    row = next(line for line in section.splitlines() if line.startswith("| **Derived selected meal weight**"))
    for needle in ("consumed quantity", "actual intake", "food waste", "leftover food"):
        assert needle in row, needle


def backticked_paths(body: str) -> set[str]:
    out = set()
    for token in re.findall(r"`([^`\s]+)`", body):
        if re.fullmatch(r"\w[\w./-]*", token) and ("/" in token or re.search(r"\.(md|csv|png|svg|py|yml|json|txt)$", token)):
            out.add(token)
    return out


def resolve(token: str) -> bool:
    for base in (REPO, DOCS):
        if (base / token).exists():
            return True
    return False


@pytest.mark.parametrize("doc", ["docs/assignment_traceability.md", "docs/demo_script.md", "docs/final_evidence.md", "docs/judgement_call.md"])
def test_every_artifact_a_document_points_to_exists(doc):
    missing = sorted(t for t in backticked_paths(text(doc)) if not resolve(t) and not t.startswith(("../", "outputs/pipeline/run_", "outputs/pipeline/runtime", "outputs/pipeline/run_log")))
    assert not missing, missing


def test_the_traceability_page_covers_the_five_graded_areas_with_all_four_fields():
    body = text("docs/assignment_traceability.md")
    for area in ("Source reasoning", "Retrieval", "Profiling and validation", "Workflow and metrics", "Dependable pipeline"):
        assert re.search(rf"^## \d\. {area}", body, re.M), area
    for field in ("Assignment expectation", "Repository evidence", "Key artifacts", "Show in 3-5 minutes"):
        assert body.count(f"**{field}**") == 5, field


def test_the_readme_links_and_images_resolve():
    body = text("README.md")
    targets = re.findall(r"\]\(([^)#]+)\)", body)
    assert targets
    missing = [t for t in targets if not t.startswith("http") and not (REPO / t).exists()]
    assert not missing, missing


def test_the_readme_pipeline_command_parses_and_its_offline_promise_is_stated():
    from src.pipeline.run import build_parser
    body = text("README.md")
    commands = re.findall(r"^python -m src\.pipeline\.run(.*?)(?:\s+#.*)?$", body, re.M)
    assert commands
    for args in commands:
        build_parser().parse_args(args.split())
    assert "python -m src.pipeline.run --stages all" in body and "offline" in body.lower() and "python -m src.pipeline.fetch" in body


def test_the_readme_has_the_reviewer_sections_and_the_engagement_framing():
    body = text("README.md")
    headings = re.findall(r"^## \d+\. (.+)$", body, re.M)
    assert headings[:3] == ["Problem", "Scope and engagement framing", "Key finding"]
    for needle in ("Source map", "Evidence model", "Final evidence", "What we can conclude", "What we cannot conclude", "Data quality", "Sensitivity", "Pipeline", "Reproducibility",
                   "Repository structure", "Known / Unknown / Assumptions / Limitations", "FDE judgement", "Demo"):
        assert needle in headings, needle
    assert "FDE-style reconstruction" in body and "publicly available Flavoria research data" in body
    assert re.search(r"not affiliated with or endorsed by", body)
    assert not re.search(r"\b(our client|our team at Flavoria|Flavoria's analytics team)\b", body, re.I)


REQUIRED_ARTIFACTS = [
    "README.md", "NOTICE", "docs/source_map.md", "docs/source_truth_decisions.md", "docs/known_unknowns_assumptions_limitations.md", "docs/judgement_call.md",
    "docs/assignment_traceability.md", "docs/demo_script.md", "docs/pipeline.md", "docs/sensitivity_analysis.md", "docs/data_provenance.md", "docs/final_evidence.md",
    "diagrams/workflow.png", "diagrams/data-model.png", "diagrams/source-map.png", "diagrams/weight-distribution.png", "diagrams/build_diagrams.py",
    "outputs/metrics/metrics.csv", "outputs/evidence/evidence_matrix.csv", "outputs/model/model_manifest.json", "outputs/validation/validation_issues.csv",
    "outputs/pipeline/stage_summary.csv", "outputs/pipeline/pipeline_controls.csv",
]


@pytest.mark.parametrize("path", REQUIRED_ARTIFACTS)
def test_required_assignment_artifact_exists_and_is_not_empty(path):
    p = REPO / path
    assert p.is_file() and p.stat().st_size > 0, path


def test_notice_and_provenance_state_sources_licences_and_the_open_items_without_inventing_terms():
    notice = text("NOTICE")
    prov = text("docs/data_provenance.md")
    for needle in ("10.5281/zenodo.5850856", "CC BY 4.0", "Finnish Meteorological Institute", "flavoriadatacatalog.tt.utu.fi", "not affiliated with", "No ownership is claimed"):
        assert needle in notice, needle
    assert "state no\nlicence or terms" in notice or "states no licence" in notice or "state no licence" in notice.replace("\n", " ")
    assert "MIT Licence" in notice and "does NOT apply to third-party material" in notice
    assert "no licence or terms statement was found" in prov and "Ownership and public-accessibility limits" in prov


def test_the_diagram_build_script_is_the_editable_source_of_every_diagram():
    script = text("diagrams/build_diagrams.py")
    for name in ("workflow", "data_model", "pipeline", "source_map", "weight_distribution"):
        assert f"def {name}(" in script, name
    for svg in ("workflow.svg", "data-model.svg", "pipeline.svg", "source-map.svg", "weight-distribution.svg"):
        assert (REPO / "diagrams" / svg).is_file(), svg


def test_the_licence_is_mit_and_is_fenced_off_from_the_third_party_data():
    licence = text("LICENSE")
    assert licence.startswith("MIT License") and "Permission is hereby granted, free of charge" in licence and 'THE SOFTWARE IS PROVIDED "AS IS"' in licence
    readme = text("README.md")
    assert "MIT Licence" in readme and "does not cover third-party data" in readme and "CC BY 4.0" in readme
    notice = text("NOTICE")
    for needle in ("data/raw/flavoria/", "data/raw/weather/", "Flavoria Data Catalog", "MIT Licence"):
        assert needle in notice, needle
    assert "MIT" in text("docs/data_provenance.md")


def _tracked_files() -> list[str]:
    import subprocess
    try:
        out = subprocess.run(["git", "ls-files"], cwd=REPO, capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("not a git checkout")
    return [f for f in out.splitlines() if f]


def test_drafting_and_course_material_is_not_part_of_the_public_repository():
    tracked = _tracked_files()
    assert "plan.md" not in tracked and "assignment.md" not in tracked
    for doc in ("README.md", "docs/source_map.md", "docs/decision_log.md"):
        assert "`plan.md`" not in text(doc) and "`assignment.md`" not in text(doc), doc


def test_no_personal_identifier_email_or_local_path_is_tracked():
    """Only text files outside the raw data are scanned; the patterns are generic so this test does not itself contain a personal identifier."""
    email = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+\.[A-Za-z]{2,}")
    path = re.compile(r"[A-Za-z]:[\/]Users[\/]|OneDrive|/c/Users/|/home/[a-z]+/|AppData[\/]", re.I)
    problems = []
    for f in _tracked_files():
        if f.startswith("data/raw/") or f.endswith((".png", ".tar", ".webm")) or f == "tests/test_final_docs.py":   # this file holds the patterns; binary files are not text
            continue
        body = (REPO / f).read_text(encoding="utf-8", errors="ignore")
        problems += [(f, m.group(0)) for m in email.finditer(body) if not m.group(0).endswith("@users.noreply.github.com")]
        problems += [(f, m.group(0)) for m in path.finditer(body)]
    assert not problems, problems


def test_no_build_phase_vocabulary_appears_anywhere_in_the_repository():
    """The repository describes the project, not how it was staged: no phase numbers, work-package labels or MVP language."""
    pattern = re.compile(r"\b[Pp]hase[ -]?[0-9]|phase2|\bWP ?[0-9]+\b|\bwp[0-9]|[Ww]ork packages?|\bMVP\b|vs plan")
    problems = []
    for f in _tracked_files():
        if f.startswith("data/raw/") or f.endswith((".png", ".tar", ".svg", ".webm")) or f == "tests/test_final_docs.py":   # binary files are not text
            continue
        p = REPO / f
        if not p.is_file():
            continue
        body = p.read_text(encoding="utf-8", errors="ignore")
        problems += [(f, m.group(0)) for m in pattern.finditer(body)]
    assert not problems, problems[:10]
