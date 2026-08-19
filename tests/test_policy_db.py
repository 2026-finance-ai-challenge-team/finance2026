from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from modules.policy_db.database import (
    build_database,
    connect_database,
    database_summary,
    seed_database,
)
from modules.policy_db.repository import (
    find_requirements,
    list_document_signatures,
)


EXPECTED_COUNTS = {
    "banks": 1,
    "policy_versions": 1,
    "requirement_sets": 4,
    "documents": 10,
    "requirement_documents": 14,
    "preparations": 10,
    "policy_conditions": 4,
    "sources": 5,
}


class PolicyDatabaseTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "policy.db"
        build_database(self.db_path)
        self.connection = connect_database(self.db_path)

    def tearDown(self) -> None:
        self.connection.close()
        self.temp_dir.cleanup()

    def test_schema_has_only_the_eight_policy_tables(self) -> None:
        table_names = {
            row["name"]
            for row in self.connection.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
                """
            )
        }
        self.assertEqual(table_names, set(EXPECTED_COUNTS))
        self.assertEqual(
            self.connection.execute("PRAGMA foreign_keys").fetchone()[0],
            1,
        )

    def test_seed_counts_and_idempotence(self) -> None:
        self.assertEqual(database_summary(self.connection), EXPECTED_COUNTS)
        seed_database(self.connection)
        self.assertEqual(database_summary(self.connection), EXPECTED_COUNTS)

    def test_representative_branch_minimum_is_exact(self) -> None:
        result = find_requirements(
            self.connection,
            channel="branch",
            visitor_type="representative",
        )
        official = next(
            item
            for item in result["requirement_sets"]
            if item["requirement_level"] == "official_minimum"
        )
        self.assertEqual(
            [item["doc_type"] for item in official["documents"]],
            ["business_registration_certificate"],
        )
        self.assertEqual(
            [item["code"] for item in official["preparations"]],
            ["representative_identity_document", "account_seal"],
        )
        self.assertTrue(
            any(
                item["requirement_level"] == "recommended_additional"
                for item in result["requirement_sets"]
            )
        )

    def test_agent_branch_minimum_is_exact(self) -> None:
        result = find_requirements(
            self.connection,
            channel="branch",
            visitor_type="agent",
        )
        official = next(
            item
            for item in result["requirement_sets"]
            if item["requirement_level"] == "official_minimum"
        )
        self.assertEqual(
            [item["doc_type"] for item in official["documents"]],
            [
                "business_registration_certificate",
                "corporate_seal_certificate",
                "power_of_attorney",
            ],
        )
        self.assertEqual(
            [item["code"] for item in official["preparations"]],
            ["agent_identity_document", "account_seal"],
        )

    def test_non_face_to_face_alternatives_and_conditions(self) -> None:
        result = find_requirements(
            self.connection,
            channel="non_face_to_face",
            visitor_type="representative",
        )
        self.assertEqual(len(result["requirement_sets"]), 1)
        documents = result["requirement_sets"][0]["documents"]

        beneficial_owner_choices = {
            item["doc_type"]
            for item in documents
            if item["choice_group"] == "beneficial_owner_evidence"
        }
        self.assertEqual(
            beneficial_owner_choices,
            {"shareholder_registry", "share_change_statement"},
        )

        sales_choices = {
            item["doc_type"]
            for item in documents
            if item["choice_group"] == "sales_evidence"
        }
        self.assertEqual(
            sales_choices,
            {
                "vat_tax_base_certificate",
                "standard_financial_statement_certificate",
            },
        )
        self.assertEqual(len(result["policy_conditions"]), 4)

    def test_signatures_match_classifier_shape_and_remain_unverified(self) -> None:
        signatures = list_document_signatures(self.connection)
        self.assertEqual(len(signatures), 10)
        self.assertTrue(all(signature["verified"] is False for signature in signatures))

        business_registration = next(
            signature
            for signature in signatures
            if signature["doc_type"] == "business_registration_certificate"
        )
        self.assertIn(
            r"사업자\s*등록증명",
            business_registration["negative_anchors"],
        )
        self.assertIsNone(business_registration["validity_days"])

    def test_every_source_is_official_and_dated(self) -> None:
        rows = self.connection.execute(
            "SELECT publisher, url, checked_at FROM sources"
        ).fetchall()
        self.assertEqual(len(rows), 5)
        for row in rows:
            self.assertEqual(row["publisher"], "하나은행")
            self.assertIn(
                row["url"].split("/")[2],
                {"www.hanabank.com", "biz.kebhana.com", "biz.hanabank.com"},
            )
            self.assertEqual(row["checked_at"], "2026-08-20")


if __name__ == "__main__":
    unittest.main()
