"""Command-line entry point for the deterministic document assessment PoC."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Optional, Sequence

from hana_poc.classification import (
    ClassificationFallbackConfigurationError,
    FileBackedClassificationAdapter,
)
from hana_poc.pipeline import DEFAULT_RULES_PATH, PipelineInputError, load_poc_input, run_pipeline
from hana_poc.rule_engine import RuleConfigurationError, load_rule_configuration


def build_parser() -> argparse.ArgumentParser:
    """Create the narrow CLI interface without embedding business requirements."""

    parser = argparse.ArgumentParser(
        description="Run the Hana corporate account document assessment PoC."
    )
    parser.add_argument(
        "--rules",
        type=Path,
        default=DEFAULT_RULES_PATH,
        help="Path to a declarative YAML rule set.",
    )
    parser.add_argument(
        "--classification-fallback",
        type=Path,
        help="Path to deterministic JSON classification fallback responses.",
    )
    parser.add_argument("input_path", type=Path, help="Path to a PoC input.json file.")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Run the pipeline and return a process exit code without calling an LLM."""

    args = build_parser().parse_args(argv)
    try:
        poc_input = load_poc_input(args.input_path)
        rule_configuration = load_rule_configuration(args.rules)
        classification_adapter = (
            FileBackedClassificationAdapter.from_json_file(
                args.classification_fallback
            )
            if args.classification_fallback is not None
            else None
        )
        result = run_pipeline(
            poc_input,
            rule_configuration,
            classification_adapter=classification_adapter,
        )
        if classification_adapter is not None:
            classification_adapter.ensure_all_responses_used()
    except (
        ClassificationFallbackConfigurationError,
        PipelineInputError,
        RuleConfigurationError,
    ) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    _print_result(result)
    return 0


def _print_result(result) -> None:
    sections = [
        ("INPUT", result.input.model_dump(mode="json")),
        (
            "CLASSIFICATION",
            [document.model_dump(mode="json") for document in result.classification],
        ),
        (
            "EXTRACTION",
            [document.model_dump(mode="json") for document in result.extraction],
        ),
        (
            "CONSISTENCY",
            [result_item.model_dump(mode="json") for result_item in result.consistency],
        ),
        (
            "RULE RESULTS",
            [result_item.model_dump(mode="json") for result_item in result.rule_results],
        ),
        ("ASSESSMENT", result.assessment.model_dump(mode="json")),
        ("LLM PROMPT", result.llm_prompt),
    ]
    for index, (name, value) in enumerate(sections, start=1):
        print(f"[{index}] {name}")
        print(json.dumps(value, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    raise SystemExit(main())
