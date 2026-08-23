"""Tests for deterministic file-backed classification fallback decisions."""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from hana_poc.classification import (
    ClassificationFallbackConfigurationError,
    FileBackedClassificationAdapter,
    classify_document_unit,
    segment_ocr_file,
)
from schemas import ClassificationMethod, ClassificationStatus, DocumentType, PocInput


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
FALLBACK_PATH = (
    REPOSITORY_ROOT
    / "fixtures/006_ambiguous_document/classification_fallback.json"
)


def ambiguous_document_unit():
    poc_input = PocInput.model_validate_json(
        (REPOSITORY_ROOT / "fixtures/006_ambiguous_document/input.json").read_text()
    )
    return segment_ocr_file(poc_input.files[1])[0]


def write_fallback(directory: str, filename: str, content: object) -> Path:
    path = Path(directory) / filename
    path.write_text(json.dumps(content), encoding="utf-8")
    return path


class FileBackedClassificationAdapterTests(unittest.TestCase):
    def test_loads_fixture_fallback_and_returns_unknown_with_candidate(self) -> None:
        adapter = FileBackedClassificationAdapter.from_json_file(FALLBACK_PATH)

        classified = classify_document_unit(
            ambiguous_document_unit(), llm_adapter=adapter
        )
        adapter.ensure_all_responses_used()

        self.assertEqual(classified.document_type, DocumentType.UNKNOWN)
        self.assertEqual(classified.classification_status, ClassificationStatus.UNKNOWN)
        self.assertEqual(classified.classification_method, ClassificationMethod.LLM)
        self.assertEqual(
            classified.candidate_document_types,
            [DocumentType.CORPORATE_REGISTRY],
        )

    def test_can_return_a_confident_document_type_with_evidence(self) -> None:
        with TemporaryDirectory() as directory:
            fallback_path = write_fallback(
                directory,
                "confident.json",
                {
                    "responses": [
                        {
                            "source_file_id": "file_ambiguous",
                            "page_start": 1,
                            "page_end": 1,
                            "document_type": "CORPORATE_REGISTRY",
                            "evidence_block_ids": ["amb_1"],
                        }
                    ]
                },
            )
            adapter = FileBackedClassificationAdapter.from_json_file(fallback_path)

            classified = classify_document_unit(
                ambiguous_document_unit(), llm_adapter=adapter
            )
            adapter.ensure_all_responses_used()

        self.assertEqual(classified.document_type, DocumentType.CORPORATE_REGISTRY)
        self.assertEqual(classified.classification_status, ClassificationStatus.CONFIDENT)
        self.assertEqual(classified.evidence_block_ids, ["amb_1"])

    def test_rejects_invalid_json_and_malformed_responses(self) -> None:
        with TemporaryDirectory() as directory:
            invalid_json_path = Path(directory) / "invalid.json"
            invalid_json_path.write_text("{invalid json", encoding="utf-8")
            malformed_response_path = write_fallback(
                directory,
                "malformed.json",
                {
                    "responses": [
                        {
                            "source_file_id": "file_ambiguous",
                            "page_start": 1,
                            "document_type": "UNKNOWN",
                        }
                    ]
                },
            )

            for fallback_path in (invalid_json_path, malformed_response_path):
                with self.subTest(fallback_path=fallback_path.name):
                    with self.assertRaises(
                        ClassificationFallbackConfigurationError
                    ):
                        FileBackedClassificationAdapter.from_json_file(fallback_path)

    def test_rejects_unknown_document_types_and_unknown_candidates(self) -> None:
        with TemporaryDirectory() as directory:
            invalid_type_path = write_fallback(
                directory,
                "invalid-type.json",
                {
                    "responses": [
                        {
                            "source_file_id": "file_ambiguous",
                            "page_start": 1,
                            "page_end": 1,
                            "document_type": "NOT_A_DOCUMENT_TYPE",
                        }
                    ]
                },
            )
            unknown_candidate_path = write_fallback(
                directory,
                "unknown-candidate.json",
                {
                    "responses": [
                        {
                            "source_file_id": "file_ambiguous",
                            "page_start": 1,
                            "page_end": 1,
                            "document_type": "UNKNOWN",
                            "candidate_document_types": ["UNKNOWN"],
                        }
                    ]
                },
            )

            for fallback_path in (invalid_type_path, unknown_candidate_path):
                with self.subTest(fallback_path=fallback_path.name):
                    with self.assertRaises(
                        ClassificationFallbackConfigurationError
                    ):
                        FileBackedClassificationAdapter.from_json_file(fallback_path)

    def test_rejects_an_unmatched_fallback_key(self) -> None:
        with TemporaryDirectory() as directory:
            fallback_path = write_fallback(
                directory,
                "unmatched.json",
                {
                    "responses": [
                        {
                            "source_file_id": "other_file",
                            "page_start": 1,
                            "page_end": 1,
                            "document_type": "UNKNOWN",
                        }
                    ]
                },
            )
            adapter = FileBackedClassificationAdapter.from_json_file(fallback_path)

            with self.assertRaisesRegex(
                ClassificationFallbackConfigurationError,
                "no classification fallback response matches",
            ):
                classify_document_unit(ambiguous_document_unit(), llm_adapter=adapter)

    def test_rejects_unused_fallback_response(self) -> None:
        adapter = FileBackedClassificationAdapter.from_json_file(FALLBACK_PATH)

        with self.assertRaisesRegex(
            ClassificationFallbackConfigurationError,
            "did not match an unresolved document",
        ):
            adapter.ensure_all_responses_used()


if __name__ == "__main__":
    unittest.main()
