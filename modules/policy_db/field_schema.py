"""Validate and store versioned OCR extraction-field schemas in PostgreSQL."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from modules.policy_db.database import _json_text, initialize_schema
from modules.policy_db.runtime import connect_database


ALLOWED_FIELD_TYPES = {
    "amount",
    "date",
    "date_range",
    "enum",
    "integer",
    "object",
    "object_array",
    "string",
    "string_array",
}
STRUCTURED_FIELD_TYPES = {"object", "object_array"}
EXCLUDED_DOCUMENT_TYPES = {
    "business_website_evidence",
    "storefront_photo",
    "portal_roadview_evidence",
}


def _duplicate_values(values: list[str]) -> list[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return sorted(duplicates)


def validate_document_field_schema(
    payload: dict[str, Any],
    *,
    expected_document_types: set[str] | None = None,
) -> dict[str, int]:
    """Validate the extraction schema and optionally match it to DB documents."""
    documents = payload.get("documents")
    object_schemas = payload.get("object_schemas")
    if not isinstance(documents, list):
        raise ValueError("documents는 배열이어야 합니다.")
    if not isinstance(object_schemas, dict):
        raise ValueError("object_schemas는 객체여야 합니다.")

    document_types = [document.get("document_type") for document in documents]
    if not all(isinstance(value, str) and value for value in document_types):
        raise ValueError("모든 문서에는 document_type 문자열이 필요합니다.")
    duplicates = _duplicate_values(document_types)
    if duplicates:
        raise ValueError(f"중복 document_type입니다: {duplicates}")
    excluded = sorted(set(document_types) & EXCLUDED_DOCUMENT_TYPES)
    if excluded:
        raise ValueError(f"제외하기로 한 문서가 포함되어 있습니다: {excluded}")

    field_count = 0
    structured_count = 0
    for document in documents:
        document_type = document["document_type"]
        if not isinstance(document.get("korean_name"), str):
            raise ValueError(f"{document_type}: korean_name이 필요합니다.")
        fields = document.get("fields")
        if not isinstance(fields, list):
            raise ValueError(f"{document_type}: fields는 배열이어야 합니다.")
        field_names = [field.get("name") for field in fields]
        if not all(isinstance(value, str) and value for value in field_names):
            raise ValueError(f"{document_type}: 모든 필드에 name이 필요합니다.")
        field_duplicates = _duplicate_values(field_names)
        if field_duplicates:
            raise ValueError(
                f"{document_type}: 중복 필드명입니다: {field_duplicates}"
            )
        for field in fields:
            field_count += 1
            field_type = field.get("type")
            if field_type not in ALLOWED_FIELD_TYPES:
                raise ValueError(
                    f"{document_type}.{field['name']}: 지원하지 않는 type={field_type}"
                )
            item_schema = field.get("item_schema")
            if field_type in STRUCTURED_FIELD_TYPES:
                structured_count += 1
                if item_schema not in object_schemas:
                    raise ValueError(
                        f"{document_type}.{field['name']}: "
                        f"object_schemas에 {item_schema!r}가 없습니다."
                    )
            elif item_schema is not None:
                raise ValueError(
                    f"{document_type}.{field['name']}: "
                    "구조형 필드가 아닌데 item_schema가 있습니다."
                )
            semantics = field.get("date_semantics")
            if semantics is not None and (
                not isinstance(semantics, dict)
                or not isinstance(semantics.get("role"), str)
                or not isinstance(semantics.get("subject"), str)
            ):
                raise ValueError(
                    f"{document_type}.{field['name']}: date_semantics가 잘못되었습니다."
                )

    for schema_name, fields in object_schemas.items():
        if not isinstance(fields, list):
            raise ValueError(f"object_schemas.{schema_name}는 배열이어야 합니다.")
        names = [field.get("name") for field in fields]
        if not all(isinstance(value, str) and value for value in names):
            raise ValueError(f"object_schemas.{schema_name}: 필드 name이 필요합니다.")
        duplicates = _duplicate_values(names)
        if duplicates:
            raise ValueError(
                f"object_schemas.{schema_name}: 중복 필드명입니다: {duplicates}"
            )

    if expected_document_types is not None:
        unknown = sorted(set(document_types) - expected_document_types)
        if unknown:
            raise ValueError(f"documents 테이블에 없는 document_type입니다: {unknown}")

    return {
        "documents": len(documents),
        "fields": field_count,
        "object_schemas": len(object_schemas),
        "structured_fields": structured_count,
    }


def import_document_field_schema(
    connection: Any,
    schema_path: Path | str,
    *,
    version: int,
    status: str = "draft",
    notes: str | None = None,
) -> dict[str, Any]:
    """Validate and upsert one complete extraction schema version atomically."""
    if version <= 0:
        raise ValueError("version은 1 이상이어야 합니다.")
    if status not in {"draft", "published", "retired"}:
        raise ValueError("status는 draft, published, retired 중 하나여야 합니다.")

    path = Path(schema_path)
    raw_bytes = path.read_bytes()
    payload = json.loads(raw_bytes.decode("utf-8"))

    initialize_schema(connection)
    rows = connection.execute("SELECT doc_type FROM documents").fetchall()
    database_document_types = {str(row["doc_type"]) for row in rows}
    summary = validate_document_field_schema(
        payload,
        expected_document_types=database_document_types,
    )
    if summary["documents"] != 47:
        raise ValueError(
            f"문서 스키마는 47종이어야 합니다: 현재 {summary['documents']}종"
        )

    source_sha256 = hashlib.sha256(raw_bytes).hexdigest()
    with connection:
        connection.execute(
            """
            INSERT INTO document_field_schema_versions (
                version, status, schema_json, source_filename,
                source_sha256, notes, published_at
            )
            VALUES (
                ?, ?, ?, ?, ?, ?,
                CASE WHEN ? = 'published' THEN NOW() ELSE NULL END
            )
            ON CONFLICT(version) DO UPDATE SET
                status = excluded.status,
                schema_json = excluded.schema_json,
                source_filename = excluded.source_filename,
                source_sha256 = excluded.source_sha256,
                notes = excluded.notes,
                updated_at = NOW(),
                published_at = CASE
                    WHEN excluded.status = 'published'
                    THEN COALESCE(
                        document_field_schema_versions.published_at,
                        NOW()
                    )
                    ELSE NULL
                END
            """,
            (
                version,
                status,
                _json_text(payload),
                path.name,
                source_sha256,
                notes,
                status,
            ),
        )

    return {
        "version": version,
        "status": status,
        "source_filename": path.name,
        "source_sha256": source_sha256,
        **summary,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="OCR 문서 필드 스키마 JSON을 PostgreSQL에 적재합니다."
    )
    parser.add_argument("schema_path", type=Path)
    parser.add_argument("--version", type=int, required=True)
    parser.add_argument(
        "--status",
        choices=("draft", "published", "retired"),
        default="draft",
    )
    parser.add_argument("--notes", default=None)
    args = parser.parse_args()

    connection = connect_database()
    try:
        result = import_document_field_schema(
            connection,
            args.schema_path,
            version=args.version,
            status=args.status,
            notes=args.notes,
        )
    finally:
        connection.close()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
