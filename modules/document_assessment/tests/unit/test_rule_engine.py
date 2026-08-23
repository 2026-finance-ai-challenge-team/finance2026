"""Unit tests for declarative YAML configuration and generic rule evaluation."""

from __future__ import annotations

import ast
from datetime import date
from pathlib import Path
from typing import Optional
import unittest

from hana_poc.classification import (
    LlmClassification,
    MaskedDocumentCandidate,
    classify_ocr_file,
)
from hana_poc.extraction import extract_structured_document
from hana_poc.rule_engine import (
    DOCUMENT_EXPIRED,
    DOCUMENT_TYPE_UNRESOLVED,
    REQUIRED_DOCUMENT_MISSING,
    REQUIRED_DOCUMENT_PRESENT,
    RuleConfigurationError,
    evaluate_requirements,
    load_rule_configuration,
    parse_rule_configuration,
)
from hana_poc.validation import validate_consistency
from schemas import DocumentType, FieldStatus, PocInput, RequirementStatus


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
RULES_PATH = (
    REPOSITORY_ROOT
    / "rules/HANA_BANK/CORPORATE_NON_FACE_TO_FACE_ACCOUNT_OPENING/poc-v1.yaml"
)


class CandidateClassificationAdapter:
    def __init__(self, candidate_document_types: tuple[DocumentType, ...]) -> None:
        self.candidate_document_types = candidate_document_types

    def classify(self, candidate: MaskedDocumentCandidate) -> LlmClassification:
        return LlmClassification(
            document_type=DocumentType.UNKNOWN,
            candidate_document_types=self.candidate_document_types,
        )


def load_pipeline_input(fixture_name: str, llm_adapter=None):
    poc_input = PocInput.model_validate_json(
        (REPOSITORY_ROOT / "fixtures" / fixture_name / "input.json").read_text()
    )
    documents = [
        extract_structured_document(classified)
        for ocr_file in poc_input.files
        for classified in classify_ocr_file(ocr_file, llm_adapter=llm_adapter)
    ]
    consistency_results = validate_consistency(documents, poc_input.application_context)
    return documents, consistency_results, poc_input.application_context


def document_presence_configuration(
    requirement_id: str,
    any_of: list[str],
    *,
    blocking: bool = True,
    max_age_days: Optional[int] = None,
):
    requirement = {
        "id": requirement_id,
        "blocking": blocking,
        "document_presence": {"any_of": any_of},
    }
    if max_age_days is not None:
        requirement["freshness"] = {"max_age_days": max_age_days}

    return parse_rule_configuration(
        {
            "workflow": {
                "bank": "TEST_BANK",
                "workflow": "TEST_WORKFLOW",
                "version": "v1",
            },
            "requirements": [requirement],
        }
    )


def consistency_configuration(requirement_id: str, check_id: str):
    return parse_rule_configuration(
        {
            "workflow": {
                "bank": "TEST_BANK",
                "workflow": "TEST_WORKFLOW",
                "version": "v1",
            },
            "requirements": [
                {
                    "id": requirement_id,
                    "blocking": True,
                    "consistency_check": {"check_id": check_id},
                }
            ],
        }
    )


class RuleConfigurationTests(unittest.TestCase):
    def test_loads_current_yaml_with_typed_metadata_and_freshness(self) -> None:
        configuration = load_rule_configuration(RULES_PATH)

        self.assertEqual(configuration.workflow.bank, "HANA_BANK")
        self.assertEqual(
            configuration.workflow.workflow,
            "CORPORATE_NON_FACE_TO_FACE_ACCOUNT_OPENING",
        )
        self.assertEqual(configuration.workflow.version, "poc-v1")
        self.assertEqual(len(configuration.requirements), 6)
        corporate_registry_requirement = next(
            requirement
            for requirement in configuration.requirements
            if requirement.id == "CORPORATE_REGISTRY_REQUIRED"
        )
        self.assertIsNotNone(corporate_registry_requirement.freshness)
        self.assertEqual(
            corporate_registry_requirement.freshness.max_age_days, 90
        )

    def test_malformed_configuration_is_rejected(self) -> None:
        valid_workflow = {
            "bank": "TEST_BANK",
            "workflow": "TEST_WORKFLOW",
            "version": "v1",
        }
        malformed_configurations = [
            {
                "workflow": valid_workflow,
                "requirements": [
                    {
                        "blocking": True,
                        "document_presence": {
                            "any_of": ["CORPORATE_REGISTRY"]
                        },
                    }
                ],
            },
            {
                "workflow": valid_workflow,
                "requirements": [
                    {
                        "id": "FRESHNESS_ON_CONSISTENCY",
                        "blocking": True,
                        "consistency_check": {"check_id": "COMPANY_NAME_MATCH"},
                        "freshness": {"max_age_days": 90},
                    }
                ],
            },
            {
                "workflow": valid_workflow,
                "requirements": [
                    {
                        "id": "WRONG_BLOCKING_TYPE",
                        "blocking": "true",
                        "document_presence": {
                            "any_of": ["CORPORATE_REGISTRY"]
                        },
                    }
                ],
            },
            {
                "workflow": valid_workflow,
                "requirements": [
                    {
                        "id": "UNSUPPORTED_RULE",
                        "blocking": True,
                        "field_presence": {"field": "corporation_name"},
                    }
                ],
            },
            {
                "workflow": valid_workflow,
                "requirements": [
                    {
                        "id": "EMPTY_ANY_OF",
                        "blocking": True,
                        "document_presence": {"any_of": []},
                    }
                ],
            },
            {
                "workflow": valid_workflow,
                "requirements": [
                    {
                        "id": "UNKNOWN_DOCUMENT_TYPE",
                        "blocking": True,
                        "document_presence": {"any_of": ["NOT_A_DOCUMENT_TYPE"]},
                    }
                ],
            },
            {
                "workflow": valid_workflow,
                "requirements": [
                    {
                        "id": "MISSING_CHECK_ID",
                        "blocking": True,
                        "consistency_check": {},
                    }
                ],
            },
            {
                "workflow": valid_workflow,
                "requirements": [
                    {
                        "id": "CONFLICTING_RULES",
                        "blocking": True,
                        "document_presence": {
                            "any_of": ["CORPORATE_REGISTRY"]
                        },
                        "consistency_check": {"check_id": "COMPANY_NAME_MATCH"},
                    }
                ],
            },
        ]

        for raw_configuration in malformed_configurations:
            with self.subTest(raw_configuration=raw_configuration):
                with self.assertRaises(RuleConfigurationError):
                    parse_rule_configuration(raw_configuration)


class DocumentPresenceEvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.documents, cls.consistency_results, cls.application_context = (
            load_pipeline_input("001_ready")
        )

    def test_any_of_is_satisfied_by_its_first_accepted_document_type(self) -> None:
        configuration = document_presence_configuration(
            "ARBITRARY_FIRST_ALTERNATIVE",
            ["SHAREHOLDER_REGISTER", "STOCK_CHANGE_STATEMENT"],
        )

        result = evaluate_requirements(
            configuration,
            self.documents,
            self.consistency_results,
            self.application_context,
        )[0]

        self.assertEqual(result.status, RequirementStatus.SATISFIED)
        self.assertEqual(result.reason_code, REQUIRED_DOCUMENT_PRESENT)
        self.assertEqual(result.evidence, [self.documents[2].document_id])

    def test_any_of_is_satisfied_by_its_second_accepted_document_type(self) -> None:
        configuration = document_presence_configuration(
            "ARBITRARY_SECOND_ALTERNATIVE",
            ["STOCK_CHANGE_STATEMENT", "SHAREHOLDER_REGISTER"],
        )

        result = evaluate_requirements(
            configuration,
            self.documents,
            self.consistency_results,
            self.application_context,
        )[0]

        self.assertEqual(result.status, RequirementStatus.SATISFIED)
        self.assertEqual(result.reason_code, REQUIRED_DOCUMENT_PRESENT)
        self.assertEqual(result.evidence, [self.documents[2].document_id])

    def test_missing_document_is_unsatisfied_without_fake_evidence(self) -> None:
        documents, consistency_results, application_context = load_pipeline_input(
            "002_missing_registry"
        )
        configuration = document_presence_configuration(
            "ARBITRARY_MISSING_DOCUMENT",
            ["CORPORATE_REGISTRY"],
        )

        result = evaluate_requirements(
            configuration,
            documents,
            consistency_results,
            application_context,
        )[0]

        self.assertEqual(result.status, RequirementStatus.UNSATISFIED)
        self.assertEqual(result.reason_code, REQUIRED_DOCUMENT_MISSING)
        self.assertEqual(result.evidence, [])

    def test_relevant_candidate_produces_unknown_without_requirement_id_branch(self) -> None:
        documents, consistency_results, application_context = load_pipeline_input(
            "006_ambiguous_document",
            CandidateClassificationAdapter((DocumentType.CORPORATE_REGISTRY,)),
        )
        configuration = document_presence_configuration(
            "RENAMED_CANDIDATE_REQUIREMENT",
            ["CORPORATE_REGISTRY"],
        )

        result = evaluate_requirements(
            configuration,
            documents,
            consistency_results,
            application_context,
        )[0]

        self.assertEqual(result.status, RequirementStatus.UNKNOWN)
        self.assertEqual(result.reason_code, DOCUMENT_TYPE_UNRESOLVED)
        self.assertEqual(result.evidence, ["file_ambiguous_document_001"])

    def test_unrelated_candidate_does_not_block_a_missing_document_result(self) -> None:
        documents, consistency_results, application_context = load_pipeline_input(
            "006_ambiguous_document",
            CandidateClassificationAdapter((DocumentType.SHAREHOLDER_REGISTER,)),
        )
        configuration = document_presence_configuration(
            "ARBITRARY_UNRELATED_CANDIDATE",
            ["CORPORATE_REGISTRY"],
        )

        result = evaluate_requirements(
            configuration,
            documents,
            consistency_results,
            application_context,
        )[0]

        self.assertEqual(result.status, RequirementStatus.UNSATISFIED)
        self.assertEqual(result.reason_code, REQUIRED_DOCUMENT_MISSING)

    def test_blocking_and_renamed_requirement_id_are_preserved_generically(self) -> None:
        configuration = document_presence_configuration(
            "RENAMED_REQUIREMENT_WITHOUT_EVALUATOR_BRANCH",
            ["BUSINESS_REGISTRATION_CERTIFICATE"],
            blocking=False,
        )

        result = evaluate_requirements(
            configuration,
            self.documents,
            self.consistency_results,
            self.application_context,
        )[0]

        self.assertEqual(
            result.requirement_id, "RENAMED_REQUIREMENT_WITHOUT_EVALUATOR_BRANCH"
        )
        self.assertFalse(result.blocking)
        self.assertEqual(result.status, RequirementStatus.SATISFIED)
        self.assertEqual(result.evidence, [self.documents[0].document_id])


class FreshnessEvaluationTests(unittest.TestCase):
    def test_document_within_requirement_freshness_window_is_satisfied(self) -> None:
        documents, consistency_results, application_context = load_pipeline_input(
            "001_ready"
        )
        configuration = document_presence_configuration(
            "RENAMED_FRESHNESS_REQUIREMENT",
            ["CORPORATE_REGISTRY"],
            max_age_days=90,
        )

        result = evaluate_requirements(
            configuration,
            documents,
            consistency_results,
            application_context,
        )[0]

        self.assertEqual(result.status, RequirementStatus.SATISFIED)
        self.assertEqual(result.reason_code, REQUIRED_DOCUMENT_PRESENT)

    def test_expired_document_is_unsatisfied_with_document_expired_reason(self) -> None:
        documents, consistency_results, application_context = load_pipeline_input(
            "008_expired_document"
        )
        configuration = document_presence_configuration(
            "ARBITRARY_EXPIRY_REQUIREMENT",
            ["CORPORATE_REGISTRY"],
            max_age_days=90,
        )

        result = evaluate_requirements(
            configuration,
            documents,
            consistency_results,
            application_context,
        )[0]

        self.assertEqual(result.status, RequirementStatus.UNSATISFIED)
        self.assertEqual(result.reason_code, DOCUMENT_EXPIRED)
        self.assertEqual(result.evidence, ["file_registry_document_001"])

    def test_unknown_issue_date_propagates_unknown(self) -> None:
        documents, consistency_results, application_context = load_pipeline_input(
            "001_ready"
        )
        registry = next(
            document
            for document in documents
            if document.document_type is DocumentType.CORPORATE_REGISTRY
        )
        unknown_issue_date = registry.issue_date.model_copy(
            update={
                "value": None,
                "normalized_value": None,
                "status": FieldStatus.UNKNOWN,
            }
        )
        unknown_registry = registry.model_copy(
            update={
                "issue_date": unknown_issue_date,
                "fields": {**registry.fields, "issue_date": unknown_issue_date},
            }
        )
        documents_with_unknown_date = [
            unknown_registry if document.document_id == registry.document_id else document
            for document in documents
        ]
        configuration = document_presence_configuration(
            "ARBITRARY_UNKNOWN_DATE_REQUIREMENT",
            ["CORPORATE_REGISTRY"],
            max_age_days=90,
        )

        result = evaluate_requirements(
            configuration,
            documents_with_unknown_date,
            consistency_results,
            application_context,
        )[0]

        self.assertEqual(result.status, RequirementStatus.UNKNOWN)
        self.assertEqual(result.reason_code, "FIELD_UNKNOWN")
        self.assertEqual(result.evidence, [registry.document_id])

    def test_application_date_is_used_instead_of_the_system_clock(self) -> None:
        documents, consistency_results, application_context = load_pipeline_input(
            "001_ready"
        )
        registry = next(
            document
            for document in documents
            if document.document_type is DocumentType.CORPORATE_REGISTRY
        )
        historical_issue_date = registry.issue_date.model_copy(
            update={"value": "2020-01-01", "normalized_value": "2020-01-01"}
        )
        historical_registry = registry.model_copy(
            update={
                "issue_date": historical_issue_date,
                "fields": {
                    **registry.fields,
                    "issue_date": historical_issue_date,
                },
            }
        )
        historical_context = application_context.model_copy(
            update={"application_date": date(2020, 1, 5)}
        )
        documents_with_historical_registry = [
            historical_registry if document.document_id == registry.document_id else document
            for document in documents
        ]
        configuration = document_presence_configuration(
            "ARBITRARY_APPLICATION_DATE_REQUIREMENT",
            ["CORPORATE_REGISTRY"],
            max_age_days=90,
        )

        result = evaluate_requirements(
            configuration,
            documents_with_historical_registry,
            consistency_results,
            historical_context,
        )[0]

        self.assertEqual(result.status, RequirementStatus.SATISFIED)
        self.assertEqual(result.reason_code, REQUIRED_DOCUMENT_PRESENT)


class ConsistencyEvaluationTests(unittest.TestCase):
    def test_consistency_status_reason_and_evidence_are_propagated(self) -> None:
        cases = [
            ("001_ready", "COMPANY_NAME_MATCH", RequirementStatus.SATISFIED),
            (
                "004_company_name_mismatch",
                "COMPANY_NAME_MATCH",
                RequirementStatus.UNSATISFIED,
            ),
            (
                "005_unknown_representative",
                "REPRESENTATIVE_NAME_MATCH",
                RequirementStatus.UNKNOWN,
            ),
        ]

        for fixture_name, check_id, expected_status in cases:
            with self.subTest(fixture_name=fixture_name):
                documents, consistency_results, application_context = load_pipeline_input(
                    fixture_name
                )
                configuration = consistency_configuration(
                    "RENAMED_CONSISTENCY_REQUIREMENT", check_id
                )
                source_result = next(
                    result
                    for result in consistency_results
                    if result.check_id == check_id
                )

                result = evaluate_requirements(
                    configuration,
                    documents,
                    consistency_results,
                    application_context,
                )[0]

                self.assertEqual(result.status, expected_status)
                self.assertEqual(result.reason_code, source_result.reason_code)
                self.assertEqual(result.evidence, source_result.evidence_document_ids)

    def test_identical_inputs_produce_identical_results(self) -> None:
        documents, consistency_results, application_context = load_pipeline_input(
            "001_ready"
        )
        configuration = load_rule_configuration(RULES_PATH)

        first = evaluate_requirements(
            configuration,
            documents,
            consistency_results,
            application_context,
        )
        second = evaluate_requirements(
            configuration,
            documents,
            consistency_results,
            application_context,
        )

        self.assertEqual(
            [result.model_dump(mode="json") for result in first],
            [result.model_dump(mode="json") for result in second],
        )


class RuleEngineDependencyTests(unittest.TestCase):
    def test_rule_engine_has_no_llm_client_import(self) -> None:
        package_path = REPOSITORY_ROOT / "src/hana_poc/rule_engine"
        imported_modules: set[str] = set()

        for source_path in package_path.glob("*.py"):
            syntax_tree = ast.parse(source_path.read_text())
            for node in ast.walk(syntax_tree):
                if isinstance(node, ast.Import):
                    imported_modules.update(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module is not None:
                    imported_modules.add(node.module)

        self.assertFalse(
            any("llm" in module.lower() or "openai" in module.lower() for module in imported_modules)
        )


if __name__ == "__main__":
    unittest.main()
