"""Corpus regressions use synthetic records; the real v0.1 data is only read."""

import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from app.json_documents import DocumentError
from features.gagaku.references.validation import (
    DEFAULT_CORPUS,
    load_corpus,
    validate_corpus,
)


def fixture() -> dict:
    return {
        "schema_version": "0.1.0",
        "purpose": "reference_metadata_only_no_audio_or_figures_stored",
        "sources": {
            "fixture-source": {
                "kind": "journal_article",
                "citation_text": "Synthetic fixture citation only.",
                "doi": None,
                "doi_verification_status": "not_applicable",
                "publisher_or_venue": None,
                "retrieved_on": None,
                "primary_source_rechecked": False,
            },
        },
        "entries": [{
            "entry_id": "fixture-entry",
            "instrument": "sho",
            "pitch_or_fingering": "fixture-pitch",
            "technique": "fixture-technique",
            "source_ref": "fixture-source",
            "performer": None,
            "recording_date": None,
            "recording_environment": None,
            "rights_category": "unclear_or_prohibited",
            "analysis_permission": "unknown",
            "production_permission": "not_granted",
            "raw_audio_included": False,
            "evidence": {"status": "unverified", "source_ref": "fixture-source", "checked_on": None},
            "notes": None,
        }],
    }


class CorpusValidationTests(unittest.TestCase):
    def setUp(self):
        self.data = fixture()

    def test_valid_corpus_is_not_mutated(self):
        before = copy.deepcopy(self.data)
        self.assertIsNone(validate_corpus(self.data))
        self.assertEqual(self.data, before)

    def test_zero_records_are_allowed(self):
        self.data.update(entries=[], sources={})
        validate_corpus(self.data)

    def test_duplicate_entry_id_is_rejected(self):
        self.data["entries"].append(copy.deepcopy(self.data["entries"][0]))
        with self.assertRaisesRegex(DocumentError, "^corpus_duplicate_entry_id$"):
            validate_corpus(self.data)

    def test_unknown_source_reference_is_rejected(self):
        self.data["entries"][0]["source_ref"] = "fixture-missing"
        with self.assertRaisesRegex(DocumentError, "^corpus_unknown_source$"):
            validate_corpus(self.data)

    def test_unknown_evidence_source_reference_is_rejected(self):
        self.data["entries"][0]["evidence"]["source_ref"] = "fixture-missing"
        with self.assertRaisesRegex(DocumentError, "^corpus_unknown_source$"):
            validate_corpus(self.data)

    def test_evidence_source_ref_may_be_null(self):
        self.data["entries"][0]["evidence"]["source_ref"] = None
        validate_corpus(self.data)

    def test_raw_audio_included_cannot_be_true(self):
        self.data["entries"][0]["raw_audio_included"] = True
        with self.assertRaises(DocumentError):
            validate_corpus(self.data)

    def test_production_permission_cannot_be_granted_unless_public_domain(self):
        self.data["entries"][0]["production_permission"] = "granted"
        with self.assertRaises(DocumentError):
            validate_corpus(self.data)
        self.data["entries"][0]["rights_category"] = "public_domain_production_usable"
        validate_corpus(self.data)

    def test_schema_rejects_missing_required_fields_and_unknown_properties(self):
        for section, field in ((None, "schema_version"), ("entries", "instrument")):
            data = fixture()
            target = data if section is None else data[section][0]
            del target[field]
            with self.subTest(section=section, field=field), self.assertRaises(DocumentError):
                validate_corpus(data)
        self.data["entries"][0]["audio_base64"] = "not-allowed"
        with self.assertRaises(DocumentError):
            validate_corpus(self.data)

    def test_full_identifier_is_checked_including_final_newlines(self):
        changes = (
            lambda data: data["entries"][0].update(entry_id="fixture-entry\n"),
            lambda data: data["entries"][0].update(source_ref="fixture-source\n"),
            lambda data: data["sources"].update({"fixture-source\n": data["sources"].pop("fixture-source")}),
        )
        for index, change in enumerate(changes):
            data = fixture()
            change(data)
            with self.subTest(case=index), self.assertRaises(DocumentError):
                validate_corpus(data)

    def test_loading_rejects_duplicate_keys_at_top_level_and_nested_records(self):
        raw = json.dumps(self.data, ensure_ascii=False)
        invalid_documents = (
            raw.replace('"schema_version": "0.1.0"', '"schema_version": "0.1.0", "schema_version": "0.1.0"'),
            raw.replace('"checked_on": null', '"checked_on": null, "checked_on": null', 1),
            raw.replace('"sources": {', '"sources": {"fixture-source": {}, ', 1),
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic-corpus.json"
            for index, document in enumerate(invalid_documents):
                path.write_text(document, encoding="utf-8")
                with self.subTest(case=index), self.assertRaises(DocumentError):
                    load_corpus(path)

    def test_loading_preserves_unicode(self):
        self.data["entries"][0]["technique"] = "単音"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic-corpus.json"
            path.write_text(json.dumps(self.data, ensure_ascii=False), encoding="utf-8")
            before = path.read_bytes()
            result = load_corpus(path)
            self.assertEqual(result, self.data)
            self.assertEqual(path.read_bytes(), before)


class InitialCorpusTests(unittest.TestCase):
    def test_current_v0_1_corpus_loads_without_writing(self):
        before = hashlib.sha256(DEFAULT_CORPUS.read_bytes()).digest()
        data = load_corpus()
        self.assertEqual(hashlib.sha256(DEFAULT_CORPUS.read_bytes()).digest(), before)
        self.assertEqual(len(data["entries"]), 2)

    def test_sho_ichi_entry_defaults_deny_production_and_stores_no_audio(self):
        data = load_corpus()
        entry = data["entries"][0]
        self.assertEqual(entry["entry_id"], "sho-ichi-hikichi2003")
        self.assertEqual(entry["instrument"], "sho")
        self.assertFalse(entry["raw_audio_included"])
        self.assertIn(entry["production_permission"], ("not_granted", "unknown"))
        self.assertNotEqual(entry["rights_category"], "public_domain_production_usable")
        source = data["sources"][entry["source_ref"]]
        self.assertEqual(source["doi"], "10.1121/1.1534605")
        self.assertEqual(source["doi_verification_status"], "verified")

    def test_ensemble_candidate_is_not_ichi_reference_or_permissioned_audio(self):
        data = load_corpus()
        entry = next(item for item in data["entries"] if item["entry_id"] == "sho-ensemble-freesound-680565")
        self.assertIsNone(entry["pitch_or_fingering"])
        self.assertEqual(entry["rights_category"], "unclear_or_prohibited")
        self.assertEqual(entry["analysis_permission"], "unknown")
        self.assertEqual(entry["production_permission"], "not_granted")
        self.assertFalse(entry["raw_audio_included"])


if __name__ == "__main__":
    unittest.main()
