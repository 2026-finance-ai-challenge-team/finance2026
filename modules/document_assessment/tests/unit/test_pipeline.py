"""Unit tests for typed pipeline input handling and orchestration."""

from __future__ import annotations

import ast
from contextlib import ExitStack
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from hana_poc import pipeline
from hana_poc.classification import (
    FileBackedClassificationAdapter,
    LlmClassification,
    MaskedDocumentCandidate,
)
from hana_poc.rule_engine import (
    DOCUMENT_TYPE_UNRESOLVED,
    RuleConfigurationError,
    load_rule_configuration,
)
from schemas import DocumentType, OverallStatus, RequirementStatus


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
FALLBACK_PATH = (
    REPOSITORY_ROOT
    / "fixtures/006_ambiguous_document/classification_fallback.json"
)


class CandidateClassificationAdapter:
    def classify(self, candidate: MaskedDocumentCandidate) -> LlmClassification:
        return LlmClassification(
            document_type=DocumentType.UNKNOWN,
            candidate_document_types=(DocumentType.CORPORATE_REGISTRY,),
        )


class PipelineInputLoadingTests(unittest.TestCase):
    def test_loads_valid_fixture_input(self) -> None:
        poc_input = pipeline.load_poc_input(
            REPOSITORY_ROOT / "fixtures/001_ready/input.json"
        )

        self.assertEqual(len(poc_input.files), 4)

    def test_rejects_invalid_json(self) -> None:
        with TemporaryDirectory() as directory:
            input_path = Path(directory) / "invalid.json"
            input_path.write_text("{invalid json", encoding="utf-8")

            with self.assertRaises(pipeline.PipelineInputError):
                pipeline.load_poc_input(input_path)

    def test_rejects_schema_invalid_input(self) -> None:
        with TemporaryDirectory() as directory:
            input_path = Path(directory) / "invalid-schema.json"
            input_path.write_text(
                '{"application_context": {}, "files": []}', encoding="utf-8"
            )

            with self.assertRaises(pipeline.PipelineInputError):
                pipeline.load_poc_input(input_path)

    def test_rejects_missing_input_file(self) -> None:
        with self.assertRaises(pipeline.PipelineInputError):
            pipeline.load_poc_input(REPOSITORY_ROOT / "fixtures/missing-input.json")

    def test_loads_default_rule_yaml_and_rejects_invalid_or_missing_rule_file(self) -> None:
        configuration = load_rule_configuration(pipeline.DEFAULT_RULES_PATH)
        self.assertEqual(configuration.workflow.version, "poc-v1")

        with self.assertRaises(RuleConfigurationError):
            load_rule_configuration(REPOSITORY_ROOT / "rules/missing.yaml")

        with TemporaryDirectory() as directory:
            invalid_rules_path = Path(directory) / "invalid.yaml"
            invalid_rules_path.write_text("workflow: [", encoding="utf-8")

            with self.assertRaises(RuleConfigurationError):
                load_rule_configuration(invalid_rules_path)


class PipelineOrchestrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rule_configuration = load_rule_configuration(pipeline.DEFAULT_RULES_PATH)

    def test_pipeline_calls_existing_stages_in_dependency_order(self) -> None:
        poc_input = pipeline.load_poc_input(
            REPOSITORY_ROOT / "fixtures/001_ready/input.json"
        )
        stage_calls: list[str] = []

        def tracked(stage_name: str, original):
            def wrapped(*args, **kwargs):
                if stage_name not in stage_calls:
                    stage_calls.append(stage_name)
                return original(*args, **kwargs)

            return wrapped

        targets = [
            ("classify_ocr_file", "classification"),
            ("extract_structured_document", "extraction"),
            ("validate_consistency", "validation"),
            ("evaluate_requirements", "rule_engine"),
            ("assess", "assessment"),
            ("build_explanation_prompt", "explanation"),
        ]
        with ExitStack() as stack:
            for attribute, stage_name in targets:
                original = getattr(pipeline, attribute)
                stack.enter_context(
                    patch.object(
                        pipeline,
                        attribute,
                        side_effect=tracked(stage_name, original),
                    )
                )
            pipeline.run_pipeline(poc_input, self.rule_configuration)

        self.assertEqual(
            stage_calls,
            [
                "classification",
                "extraction",
                "validation",
                "rule_engine",
                "assessment",
                "explanation",
            ],
        )

    def test_pipeline_result_exposes_all_stage_outputs(self) -> None:
        poc_input = pipeline.load_poc_input(
            REPOSITORY_ROOT / "fixtures/001_ready/input.json"
        )

        result = pipeline.run_pipeline(poc_input, self.rule_configuration)

        self.assertEqual(result.input, poc_input)
        self.assertEqual(len(result.classification), 4)
        self.assertEqual(len(result.extraction), 4)
        self.assertTrue(result.consistency)
        self.assertTrue(result.rule_results)
        self.assertEqual(result.assessment.overall_status, OverallStatus.READY)
        self.assertEqual(result.llm_prompt["assessment"]["overall_status"], "READY")

    def test_action_required_and_review_required_are_normal_pipeline_results(self) -> None:
        cases = {
            "002_missing_registry": OverallStatus.ACTION_REQUIRED,
            "005_unknown_representative": OverallStatus.REVIEW_REQUIRED,
        }
        for fixture_name, expected_status in cases.items():
            with self.subTest(fixture_name=fixture_name):
                poc_input = pipeline.load_poc_input(
                    REPOSITORY_ROOT / "fixtures" / fixture_name / "input.json"
                )

                result = pipeline.run_pipeline(poc_input, self.rule_configuration)

                self.assertEqual(result.assessment.overall_status, expected_status)

    def test_pipeline_accepts_an_injected_classification_adapter(self) -> None:
        poc_input = pipeline.load_poc_input(
            REPOSITORY_ROOT / "fixtures/006_ambiguous_document/input.json"
        )

        result = pipeline.run_pipeline(
            poc_input,
            self.rule_configuration,
            classification_adapter=CandidateClassificationAdapter(),
        )

        self.assertEqual(result.assessment.overall_status, OverallStatus.REVIEW_REQUIRED)

    def test_file_backed_fallback_makes_fixture_006_requirement_unresolved(self) -> None:
        poc_input = pipeline.load_poc_input(
            REPOSITORY_ROOT / "fixtures/006_ambiguous_document/input.json"
        )
        adapter = FileBackedClassificationAdapter.from_json_file(FALLBACK_PATH)

        result = pipeline.run_pipeline(
            poc_input,
            self.rule_configuration,
            classification_adapter=adapter,
        )
        adapter.ensure_all_responses_used()
        registry_requirement = next(
            requirement
            for requirement in result.rule_results
            if requirement.requirement_id == "CORPORATE_REGISTRY_REQUIRED"
        )

        self.assertEqual(registry_requirement.status, RequirementStatus.UNKNOWN)
        self.assertEqual(
            registry_requirement.reason_code, DOCUMENT_TYPE_UNRESOLVED
        )
        self.assertEqual(result.assessment.overall_status, OverallStatus.REVIEW_REQUIRED)

    def test_same_file_backed_fallback_produces_same_pipeline_result(self) -> None:
        poc_input = pipeline.load_poc_input(
            REPOSITORY_ROOT / "fixtures/006_ambiguous_document/input.json"
        )

        results = []
        for _ in range(2):
            adapter = FileBackedClassificationAdapter.from_json_file(FALLBACK_PATH)
            result = pipeline.run_pipeline(
                poc_input,
                self.rule_configuration,
                classification_adapter=adapter,
            )
            adapter.ensure_all_responses_used()
            results.append(result)

        self.assertEqual(results[0], results[1])


class PipelineDependencyTests(unittest.TestCase):
    def test_orchestration_and_cli_have_no_actual_llm_client_import(self) -> None:
        imported_modules: set[str] = set()
        for source_path in (
            REPOSITORY_ROOT / "src/hana_poc/pipeline.py",
            REPOSITORY_ROOT / "src/hana_poc/cli.py",
        ):
            syntax_tree = ast.parse(source_path.read_text())
            for node in ast.walk(syntax_tree):
                if isinstance(node, ast.Import):
                    imported_modules.update(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module is not None:
                    imported_modules.add(node.module)

        self.assertFalse(
            any("openai" in module.lower() for module in imported_modules)
        )


if __name__ == "__main__":
    unittest.main()
