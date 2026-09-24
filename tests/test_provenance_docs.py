"""The attribution documents must agree with the pins and with what ingestion actually produces."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from src.ingest.ingest import run_ingestion

REPO = Path(__file__).resolve().parents[1]
NOTICE = (REPO / "NOTICE").read_text(encoding="utf-8")
PROV = (REPO / "docs" / "data_provenance.md").read_text(encoding="utf-8")
TZ_STATEMENT = ("A +3 hour normalization is the strongest-supported engineering decision based on cross-export temporal "
                "consistency checks; the original source does not explicitly confirm the timezone metadata.")


def flat(s: str) -> str:
    return re.sub(r"\s+", " ", s)


class TestNotice:
    def test_flavoria_attribution_is_present_verbatim_from_config(self, cfg):
        f = cfg.sources.flavoria
        assert f.doi in NOTICE and "CC BY 4.0" in NOTICE and f.record_url in NOTICE and f.archive_sha256 in NOTICE
        assert "Sarapisto" in NOTICE and "Zenodo" in NOTICE and "v1.0.0" in NOTICE
        assert "2026-09-18" in NOTICE and "unmodified" in NOTICE

    def test_fmi_licence_is_the_verified_one_and_wording_is_marked_as_ours(self, cfg):
        w = cfg.sources.weather
        assert w.license == "CC-BY-4.0" and str(w.license_verified_on) == "2026-09-19"
        assert w.license_terms_url in NOTICE and w.license_url in NOTICE and "2026-09-19" in NOTICE
        assert "does not prescribe wording" in flat(NOTICE)
        assert "Finnish Meteorological Institute open data" in NOTICE

    def test_no_licence_version_is_guessed_for_anything_unverified(self):
        assert "MIT Licence" in NOTICE and "does NOT apply to third-party material" in NOTICE   # the code licence is stated and fenced off from the data
        assert "state no licence or terms" in flat(NOTICE)        # the catalogue pages: no terms found, said plainly

    def test_notice_states_the_scenario_is_simulated_and_unaffiliated(self):
        t = flat(NOTICE)
        assert "simulated educational engagement" in t and "not affiliated" in t and "not endorsed" in t


class TestDataProvenanceMatchesThePins:
    def test_every_pinned_checksum_appears_in_the_document(self, cfg):
        f, w = cfg.sources.flavoria, cfg.sources.weather
        pins = [f.archive_md5, f.archive_sha256] + [m.sha256 for m in f.members] + [s.sha256 for s in (*w.raw_files, *w.evidence_files)]
        missing = [p for p in pins if p not in PROV]
        assert not missing, f"checksums pinned in config but absent from docs/data_provenance.md: {missing}"

    def test_snapshot_identifiers_match_a_real_run(self, cfg, tmp_path):
        r, _ = run_ingestion(cfg, REPO, tmp_path / "o")
        assert r.snapshot("flavoria").source_snapshot_id in PROV and r.snapshot("fmi_weather").source_snapshot_id in PROV
        assert r.input_fingerprint in PROV

    def test_urls_versions_dates_and_licences(self, cfg):
        f, w = cfg.sources.flavoria, cfg.sources.weather
        for needle in (f.record_url, f.doi, f.archive_url, w.endpoint, w.license_terms_url, "2026-09-18", "2026-09-19", "1.0.0", "2022-06-10", "CC BY 4.0"):
            assert needle in PROV or needle.replace("https://", "") in PROV, needle
        assert f.archive_url in PROV

    def test_states_what_is_and_is_not_known_about_terms(self):
        t = flat(PROV)
        assert "does not prescribe attribution wording" in t
        assert "no licence or terms statement was found" in t
        assert "**not** part of this project" in t or "are **not** part of this project" in t

    def test_states_the_refresh_policy(self):
        t = flat(PROV)
        for phrase in ("A normal run is offline", "never overwrites an existing raw file", "new snapshot", "never does this by itself"):
            assert phrase in t

    def test_the_documents_describe_the_timezone_decision_without_claiming_confirmation(self):
        assert "not confirm" in flat(PROV) and "evidence-backed engineering decision" in flat(PROV)


class TestTimezoneDocumentation:
    def test_the_mandated_sentence_appears_verbatim_in_the_decision_record(self):
        assert TZ_STATEMENT in flat((REPO / "docs" / "source_truth_decisions.md").read_text(encoding="utf-8"))

    def test_the_decision_record_says_file_specific_and_defines_t10(self):
        t = flat((REPO / "docs" / "source_truth_decisions.md").read_text(encoding="utf-8"))
        assert "file-specific" in t.lower() and "T10" in t

    @pytest.mark.parametrize("path", ["config/timezone_overrides.yml", "src/config.py", "src/ingest/tz_scope.py", "src/ingest/ingest.py"])
    def test_no_code_or_config_states_a_general_timezone_fact(self, path):
        text = (REPO / path).read_text(encoding="utf-8")
        assert not re.search(r"Helsinki\s+(is|=)\s+UTC\s*\+\s*3", text) and "Helsinki is UTC" not in text
