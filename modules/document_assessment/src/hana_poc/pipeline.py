"""Composition of the deterministic post-OCR assessment pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

from pydantic import ValidationError

from hana_poc.assessment import assess
from hana_poc.classification import (
    LlmClassificationAdapter,
    classify_ocr_file,
)
from hana_poc.explanation import ExplanationPromptPayload, build_explanation_prompt
from hana_poc.extraction import extract_structured_document
from hana_poc.rule_engine import (
    RuleConfiguration,
    evaluate_requirements,
)
from hana_poc.validation import validate_consistency
from schemas import (
    Assessment,
    ClassifiedDocument,
    ConsistencyResult,
    PocInput,
    RequirementResult,
    StructuredDocument,
)


DEFAULT_RULES_PATH = (
    Path(__file__).resolve().parents[2]
    / "rules/HANA_BANK/CORPORATE_NON_FACE_TO_FACE_ACCOUNT_OPENING/poc-v1.yaml"
)


class PipelineInputError(ValueError):
    """Raised when a pipeline input cannot be read or match the PoC contract."""


@dataclass(frozen=True)
class PipelineResult:
    """Structured outputs from each pipeline stage, without presentation side effects."""

    input: PocInput
    classification: list[ClassifiedDocument]
    extraction: list[StructuredDocument]
    consistency: list[ConsistencyResult]
    rule_results: list[RequirementResult]
    assessment: Assessment
    llm_prompt: ExplanationPromptPayload


def load_poc_input(input_path: Path) -> PocInput:
    """Read and validate an input JSON file at the typed pipeline boundary."""

    try:
        input_json = input_path.read_text(encoding="utf-8")
    except OSError as error:
        raise PipelineInputError(f"unable to read input file {input_path}: {error}") from error

    try:
        return PocInput.model_validate_json(input_json)
    except ValidationError as error:
        raise PipelineInputError(f"invalid PoC input {input_path}: {error}") from error


def run_pipeline(
    poc_input: PocInput,
    rule_configuration: RuleConfiguration,
    classification_adapter: Optional[LlmClassificationAdapter] = None,
) -> PipelineResult:
    """Run the existing stages in dependency order without adding business rules."""

    classification = [
        classified_document
        for ocr_file in poc_input.files
        for classified_document in classify_ocr_file(
            ocr_file,
            llm_adapter=classification_adapter,
        )
    ]
    extraction = [
        extract_structured_document(classified_document)
        for classified_document in classification
    ]
    consistency = validate_consistency(extraction, poc_input.application_context)
    rule_results = evaluate_requirements(
        rule_configuration,
        extraction,
        consistency,
        poc_input.application_context,
    )
    assessment = assess(rule_results, consistency)
    llm_prompt = build_explanation_prompt(assessment)

    return PipelineResult(
        input=poc_input,
        classification=classification,
        extraction=extraction,
        consistency=consistency,
        rule_results=rule_results,
        assessment=assessment,
        llm_prompt=llm_prompt,
    )
