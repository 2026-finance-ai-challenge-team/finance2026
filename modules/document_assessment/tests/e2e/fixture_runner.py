"""Generic partial-assertion runner for executable PoC fixtures."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from hana_poc.classification import FileBackedClassificationAdapter
from hana_poc.pipeline import PipelineResult, load_poc_input, run_pipeline
from hana_poc.rule_engine import RuleConfiguration, load_rule_configuration
from schemas import DocumentType, OverallStatus, RequirementStatus


class FixtureExpectedValidationError(ValueError):
    """Raised when an expected.json file does not match the fixture contract."""


class FixtureAssertionError(AssertionError):
    """Raised when a typed pipeline result misses a fixture partial assertion."""


class _ExpectedResultFields(BaseModel):
    """Partial fields shared by requirement and consistency assertions."""

    model_config = ConfigDict(extra="forbid")

    status: Optional[RequirementStatus] = None
    reason_code: Optional[str] = None
    blocking: Optional[bool] = None

    @field_validator("reason_code")
    @classmethod
    def requires_non_empty_reason_code_when_present(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and not value.strip():
            raise ValueError("reason_code must not be empty")
        return value

    @model_validator(mode="after")
    def requires_at_least_one_assertion(self) -> "_ExpectedResultFields":
        if not self.model_fields_set:
            raise ValueError("assertion must contain at least one supported field")
        if any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("assertion values cannot be null")
        return self


class _ExpectedClassificationDocument(BaseModel):
    """Partial classification fields compared by deterministic output index."""

    model_config = ConfigDict(extra="forbid")

    document_type: Optional[DocumentType] = None
    page_start: Optional[int] = Field(default=None, ge=1)
    page_end: Optional[int] = Field(default=None, ge=1)

    @model_validator(mode="after")
    def requires_valid_partial_document_assertion(
        self,
    ) -> "_ExpectedClassificationDocument":
        if not self.model_fields_set:
            raise ValueError("classification document assertion cannot be empty")
        if any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("classification document assertion values cannot be null")
        if (
            self.page_start is not None
            and self.page_end is not None
            and self.page_end < self.page_start
        ):
            raise ValueError("page_end must be greater than or equal to page_start")
        return self


class _ExpectedClassification(BaseModel):
    """Partial assertions for classified document output."""

    model_config = ConfigDict(extra="forbid")

    has_unresolved_document: Optional[bool] = None
    documents: list[_ExpectedClassificationDocument] = Field(default_factory=list)

    @model_validator(mode="after")
    def requires_at_least_one_assertion(self) -> "_ExpectedClassification":
        if not self.model_fields_set:
            raise ValueError("classification must contain an assertion")
        if (
            "has_unresolved_document" in self.model_fields_set
            and self.has_unresolved_document is None
        ):
            raise ValueError("has_unresolved_document cannot be null")
        return self


class _ExpectedAssertions(BaseModel):
    """Root partial assertion sections supported by fixture expected.json files."""

    model_config = ConfigDict(extra="forbid")

    overall_status: Optional[OverallStatus] = None
    requirements: dict[str, _ExpectedResultFields] = Field(default_factory=dict)
    consistency_checks: dict[str, _ExpectedResultFields] = Field(default_factory=dict)
    classification: Optional[_ExpectedClassification] = None

    @model_validator(mode="after")
    def rejects_null_sections(self) -> "_ExpectedAssertions":
        if (
            "overall_status" in self.model_fields_set
            and self.overall_status is None
        ):
            raise ValueError("overall_status cannot be null")
        if "classification" in self.model_fields_set and self.classification is None:
            raise ValueError("classification cannot be null")
        return self


class ExpectedFixture(BaseModel):
    """Validated expected.json container; this is deliberately not a snapshot."""

    model_config = ConfigDict(extra="forbid")

    expected: _ExpectedAssertions


@dataclass(frozen=True)
class FixturePaths:
    """Paths belonging to one executable fixture directory."""

    directory: Path

    @property
    def input_path(self) -> Path:
        return self.directory / "input.json"

    @property
    def expected_path(self) -> Path:
        return self.directory / "expected.json"

    @property
    def classification_fallback_path(self) -> Path:
        return self.directory / "classification_fallback.json"


def discover_fixtures(fixtures_root: Path) -> list[FixturePaths]:
    """Discover every directory with both required executable-fixture files."""

    return [
        FixturePaths(path)
        for path in sorted(fixtures_root.iterdir())
        if path.is_dir()
        and (path / "input.json").is_file()
        and (path / "expected.json").is_file()
    ]


def load_expected_fixture(expected_path: Path) -> ExpectedFixture:
    """Read and strictly validate one partial-assertion expected.json file."""

    try:
        content = expected_path.read_text(encoding="utf-8")
    except OSError as error:
        raise FixtureExpectedValidationError(
            f"unable to read expected fixture {expected_path}: {error}"
        ) from error

    try:
        return ExpectedFixture.model_validate_json(content)
    except ValidationError as error:
        raise FixtureExpectedValidationError(
            f"invalid expected fixture {expected_path}: {error}"
        ) from error


def run_fixture(
    fixture: FixturePaths,
    rule_configuration: RuleConfiguration,
) -> PipelineResult:
    """Run a fixture through the typed pipeline and its partial assertions."""

    adapter = (
        FileBackedClassificationAdapter.from_json_file(
            fixture.classification_fallback_path
        )
        if fixture.classification_fallback_path.is_file()
        else None
    )
    result = run_pipeline(
        load_poc_input(fixture.input_path),
        rule_configuration,
        classification_adapter=adapter,
    )
    if adapter is not None:
        adapter.ensure_all_responses_used()
    if not result.llm_prompt:
        raise FixtureAssertionError(f"{fixture.directory.name}: llm_prompt is missing")

    assert_expected_fixture(fixture.directory.name, load_expected_fixture(fixture.expected_path), result)
    return result


def assert_expected_fixture(
    fixture_name: str,
    expected_fixture: ExpectedFixture,
    result: PipelineResult,
) -> None:
    """Compare only fields explicitly declared in one expected.json fixture."""

    expected = expected_fixture.expected
    if "overall_status" in expected.model_fields_set:
        _assert_equal(
            fixture_name,
            "assessment.overall_status",
            expected.overall_status,
            result.assessment.overall_status,
        )

    if "requirements" in expected.model_fields_set:
        _assert_result_assertions(
            fixture_name,
            "requirements",
            expected.requirements,
            {item.requirement_id: item for item in result.rule_results},
        )

    if "consistency_checks" in expected.model_fields_set:
        _assert_result_assertions(
            fixture_name,
            "consistency_checks",
            expected.consistency_checks,
            {item.check_id: item for item in result.consistency},
        )

    if "classification" in expected.model_fields_set:
        _assert_classification(
            fixture_name,
            expected.classification,
            result,
        )


def _assert_result_assertions(
    fixture_name: str,
    section_name: str,
    expected_by_id: dict[str, _ExpectedResultFields],
    actual_by_id: dict[str, object],
) -> None:
    for result_id, expected_fields in expected_by_id.items():
        actual = actual_by_id.get(result_id)
        if actual is None:
            _raise_assertion(
                fixture_name,
                f"{section_name}.{result_id}",
                "present",
                "missing",
            )
        for field in expected_fields.model_fields_set:
            _assert_equal(
                fixture_name,
                f"{section_name}.{result_id}.{field}",
                getattr(expected_fields, field),
                getattr(actual, field),
            )


def _assert_classification(
    fixture_name: str,
    expected: _ExpectedClassification,
    result: PipelineResult,
) -> None:
    if "has_unresolved_document" in expected.model_fields_set:
        actual_has_unresolved = any(
            document.document_type is DocumentType.UNKNOWN
            for document in result.classification
        )
        _assert_equal(
            fixture_name,
            "classification.has_unresolved_document",
            expected.has_unresolved_document,
            actual_has_unresolved,
        )

    if "documents" in expected.model_fields_set:
        for index, expected_document in enumerate(expected.documents):
            if index >= len(result.classification):
                _raise_assertion(
                    fixture_name,
                    f"classification.documents[{index}]",
                    "present",
                    "missing",
                )
            actual_document = result.classification[index]
            for field in expected_document.model_fields_set:
                _assert_equal(
                    fixture_name,
                    f"classification.documents[{index}].{field}",
                    getattr(expected_document, field),
                    getattr(actual_document, field),
                )


def _assert_equal(
    fixture_name: str,
    field_path: str,
    expected: object,
    actual: object,
) -> None:
    if expected != actual:
        _raise_assertion(fixture_name, field_path, expected, actual)


def _raise_assertion(
    fixture_name: str,
    field_path: str,
    expected: object,
    actual: object,
) -> None:
    raise FixtureAssertionError(
        f"{fixture_name}: {field_path}\n"
        f"expected: {_render_value(expected)}\n"
        f"actual: {_render_value(actual)}"
    )


def _render_value(value: object) -> str:
    if isinstance(value, Enum):
        return value.value
    return str(value)
