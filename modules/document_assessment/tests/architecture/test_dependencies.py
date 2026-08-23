"""Architecture invariants enforced with lightweight Python AST inspection."""

from __future__ import annotations

import ast
import importlib
from pathlib import Path
import unittest

from hana_poc.pipeline import DEFAULT_RULES_PATH


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCHEMAS_ROOT = REPOSITORY_ROOT / "schemas"
HANA_POC_ROOT = REPOSITORY_ROOT / "src/hana_poc"
OCR_ADAPTERS_ROOT = HANA_POC_ROOT / "ocr_adapters"
RULES_PATH = (
    REPOSITORY_ROOT
    / "rules/HANA_BANK/CORPORATE_NON_FACE_TO_FACE_ACCOUNT_OPENING/poc-v1.yaml"
)

STAGE_ROOTS = {
    "classification": HANA_POC_ROOT / "classification",
    "extraction": HANA_POC_ROOT / "extraction",
    "validation": HANA_POC_ROOT / "validation",
    "rule_engine": HANA_POC_ROOT / "rule_engine",
    "assessment": HANA_POC_ROOT / "assessment",
    "explanation": HANA_POC_ROOT / "explanation",
}
PROVIDER_MODULE_ROOTS = {
    "anthropic",
    "boto3",
    "botocore",
    "cohere",
    "google.genai",
    "google.generativeai",
    "httpx",
    "llm",
    "litellm",
    "mistralai",
    "ollama",
    "openai",
    "requests",
    "vertexai",
}


def _source_files(directory: Path) -> list[Path]:
    return sorted(directory.rglob("*.py"))


def _module_name(source_path: Path) -> str:
    if source_path.is_relative_to(SCHEMAS_ROOT):
        parts = ["schemas", *source_path.relative_to(SCHEMAS_ROOT).parts]
    else:
        parts = list(source_path.relative_to(REPOSITORY_ROOT / "src").parts)
    if parts[-1] == "__init__.py":
        parts.pop()
    else:
        parts[-1] = Path(parts[-1]).stem
    return ".".join(parts)


def _package_name(source_path: Path) -> str:
    module_name = _module_name(source_path)
    if source_path.name == "__init__.py":
        return module_name
    return module_name.rpartition(".")[0]


def _resolve_from_import(source_path: Path, node: ast.ImportFrom) -> str:
    if node.level == 0:
        return node.module or ""

    package_parts = _package_name(source_path).split(".")
    anchor = package_parts[: len(package_parts) - (node.level - 1)]
    if node.module:
        anchor.extend(node.module.split("."))
    return ".".join(anchor)


def _imported_modules(source_path: Path) -> set[str]:
    syntax_tree = ast.parse(source_path.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(syntax_tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = _resolve_from_import(source_path, node)
            if module:
                imported.add(module)
                if module in {"hana_poc", "schemas"}:
                    imported.update(
                        f"{module}.{alias.name}"
                        for alias in node.names
                        if alias.name != "*"
                    )
    return imported


def _is_within(module_name: str, package_name: str) -> bool:
    return module_name == package_name or module_name.startswith(f"{package_name}.")


def _forbidden_imports(directory: Path, forbidden_packages: set[str]) -> dict[Path, list[str]]:
    violations: dict[Path, list[str]] = {}
    for source_path in _source_files(directory):
        matches = sorted(
            module
            for module in _imported_modules(source_path)
            if any(_is_within(module, package) for package in forbidden_packages)
        )
        if matches:
            violations[source_path.relative_to(REPOSITORY_ROOT)] = matches
    return violations


class DependencyDirectionTests(unittest.TestCase):
    def test_ocr_adapters_depend_on_no_pipeline_stage(self) -> None:
        stage_packages = {f"hana_poc.{stage}" for stage in STAGE_ROOTS}

        self.assertEqual(
            _forbidden_imports(OCR_ADAPTERS_ROOT, stage_packages),
            {},
        )

    def test_stage_dependency_matrix_uses_only_schema_contracts(self) -> None:
        forbidden_by_package = {
            "schemas": {"hana_poc"},
            "classification": {
                "hana_poc.assessment",
                "hana_poc.explanation",
                "hana_poc.extraction",
                "hana_poc.rule_engine",
                "hana_poc.validation",
            },
            "extraction": {
                "hana_poc.assessment",
                "hana_poc.explanation",
                "hana_poc.rule_engine",
                "hana_poc.validation",
            },
            "validation": {
                "hana_poc.assessment",
                "hana_poc.explanation",
                "hana_poc.rule_engine",
            },
            "rule_engine": {"hana_poc.assessment", "hana_poc.explanation"},
            "assessment": {"hana_poc.explanation"},
        }
        roots = {"schemas": SCHEMAS_ROOT, **STAGE_ROOTS}

        for package_name, forbidden_packages in forbidden_by_package.items():
            with self.subTest(package=package_name):
                self.assertEqual(
                    _forbidden_imports(roots[package_name], forbidden_packages),
                    {},
                )

    def test_only_pipeline_and_cli_orchestrate_multiple_pipeline_stages(self) -> None:
        orchestration_sources = {
            HANA_POC_ROOT / "pipeline.py",
            HANA_POC_ROOT / "cli.py",
        }
        stage_packages = {f"hana_poc.{stage}" for stage in STAGE_ROOTS}

        for source_path in _source_files(HANA_POC_ROOT):
            imported_stages = {
                stage
                for stage in stage_packages
                if any(
                    _is_within(module, stage)
                    for module in _imported_modules(source_path)
                )
            }
            if len(imported_stages) > 1:
                with self.subTest(source=source_path.relative_to(REPOSITORY_ROOT)):
                    self.assertIn(source_path, orchestration_sources)


class AiBoundaryTests(unittest.TestCase):
    def test_production_code_has_no_llm_provider_imports(self) -> None:
        production_sources = _source_files(SCHEMAS_ROOT) + _source_files(HANA_POC_ROOT)
        violations: dict[Path, list[str]] = {}
        for source_path in production_sources:
            matches = sorted(
                module
                for module in _imported_modules(source_path)
                if any(
                    _is_within(module, provider_root)
                    for provider_root in PROVIDER_MODULE_ROOTS
                )
            )
            if matches:
                violations[source_path.relative_to(REPOSITORY_ROOT)] = matches
        self.assertEqual(violations, {})

    def test_deterministic_core_has_no_ai_or_explanation_dependencies(self) -> None:
        forbidden_by_package = {
            "validation": {"hana_poc.explanation", *PROVIDER_MODULE_ROOTS},
            "rule_engine": {
                "hana_poc.classification.adapters",
                "hana_poc.explanation",
                *PROVIDER_MODULE_ROOTS,
            },
            "assessment": {"hana_poc.explanation", *PROVIDER_MODULE_ROOTS},
        }
        for package_name, forbidden_packages in forbidden_by_package.items():
            with self.subTest(package=package_name):
                self.assertEqual(
                    _forbidden_imports(STAGE_ROOTS[package_name], forbidden_packages),
                    {},
                )

    def test_deterministic_core_imports_without_llm_runtime_dependencies(self) -> None:
        for module_name in (
            "hana_poc.validation",
            "hana_poc.rule_engine",
            "hana_poc.assessment",
        ):
            with self.subTest(module=module_name):
                self.assertIsNotNone(importlib.import_module(module_name))


class RuleSourceOfTruthTests(unittest.TestCase):
    def test_cli_default_uses_the_rule_source_of_truth(self) -> None:
        self.assertEqual(DEFAULT_RULES_PATH, RULES_PATH)
        self.assertTrue(RULES_PATH.is_file())


if __name__ == "__main__":
    unittest.main()
