"""Synthetic demo adapter that never promotes sample classifications to READY."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from .contracts import (
    AnalysisResponse,
    DocumentResult,
    DocumentStatus,
    OverallStatus,
    RequirementResult,
    SourceReference,
    TaskSummary,
)


_DEMO_TASK_ID = "kakaobank.limit_account_release"


def build_demo_result(repo_root: Path, task: TaskSummary) -> AnalysisResponse:
    if task.task_id != _DEMO_TASK_ID:
        raise LookupError(task.task_id)

    sample_path = (
        repo_root
        / "modules"
        / "doc_classify"
        / "examples"
        / "classify-result.sample.json"
    )
    sample = json.loads(sample_path.read_text(encoding="utf-8"))

    documents: list[DocumentResult] = []
    for raw_document in sample["documents"]:
        relevance_status = raw_document["relevance"]["status"]
        classification = raw_document["classification"]
        if relevance_status == "이번 업무에는 불필요":
            status = DocumentStatus.UNNECESSARY
            reason_code = "NOT_REQUIRED_FOR_TASK"
        elif raw_document.get("needs_user_confirm"):
            status = DocumentStatus.REVIEW_REQUIRED
            reason_code = "LOW_CLASSIFICATION_CONFIDENCE"
        else:
            status = DocumentStatus.REVIEW_REQUIRED
            reason_code = "UNVERIFIED_POLICY_OR_SIGNATURE"

        documents.append(
            DocumentResult(
                document_id=raw_document["file_id"],
                source_name=raw_document["source_name"],
                doc_type=classification.get("doc_type"),
                label_ko=classification.get("label_ko"),
                confidence=classification["confidence"],
                status=status,
                reason_code=reason_code,
                needs_user_confirm=bool(raw_document.get("needs_user_confirm")),
            )
        )

    source = SourceReference(
        url=task.source_url,
        as_of=task.as_of,
        last_checked=task.last_checked,
        verified=task.verified,
    )
    requirements = [
        RequirementResult(
            requirement_id=doc_type,
            label_ko=doc_type,
            status=DocumentStatus.MISSING,
            blocking=True,
            reason_code="SYNTHETIC_DEMO_REQUIRED_DOCUMENT_NOT_FOUND",
            source=source,
        )
        for doc_type in sample.get("missing", {}).get("required", [])
    ]

    return AnalysisResponse(
        session_id=uuid4(),
        task=task,
        overall_status=OverallStatus.REVIEW_REQUIRED,
        checked_at=AnalysisResponse.checked_now(),
        documents=documents,
        requirements=requirements,
        warnings=[
            "이 결과는 합성 샘플이며 문서 자동 식별 패턴은 아직 표본 검증 전입니다."
        ],
    )
