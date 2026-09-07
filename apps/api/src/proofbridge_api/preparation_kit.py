"""Build a privacy-minimized preparation guide ZIP from an analysis result.

The analysis pipeline deletes uploaded originals before returning. Therefore this
archive intentionally contains guidance and structured results only; it must not
be presented as a digital-submission archive containing source documents.
"""

from __future__ import annotations

from io import BytesIO
import json
from zipfile import ZIP_DEFLATED, ZipFile

from .contracts import AnalysisResponse


_STATUS_LABELS = {
    "READY": "준비 완료",
    "MISSING": "추가 필요",
    "EXPIRED": "기한 만료",
    "MISMATCH": "정보 불일치",
    "UNNECESSARY": "이번 업무에는 불필요",
    "REVIEW_REQUIRED": "확인 필요",
    "ACTION_REQUIRED": "보완 필요",
}


def _status_label(value: object) -> str:
    raw = getattr(value, "value", value)
    return _STATUS_LABELS.get(str(raw), str(raw))


def _markdown(result: AnalysisResponse) -> str:
    lines = [
        "# FORM:E 준비 안내",
        "",
        f"- 업무: {result.task.label_ko}",
        f"- 전체 상태: {_status_label(result.overall_status)}",
        f"- 점검 시각(UTC): {result.checked_at.isoformat()}",
        f"- 정책 기준일: {result.task.as_of or '확인 필요'}",
        "",
        "> 이 결과는 은행의 승인·통과를 보장하지 않는 공개 기준 사전 점검입니다.",
        "> 업로드 원본은 분석 응답 전에 삭제되므로 이 ZIP에는 원본 문서가 없습니다.",
        "",
        "## 인식한 문서",
        "",
    ]
    if result.documents:
        for document in result.documents:
            label = document.label_ko or "문서 종류 확인 필요"
            lines.append(f"- {label}: {_status_label(document.status)}")
    else:
        lines.append("- 인식한 문서 없음")

    plan = result.completion_plan
    if plan is not None:
        lines.extend(["", f"## 권장 증빙 조합: {plan.bundle_label}", ""])
        for guide in plan.documents:
            lines.extend(
                [
                    f"### {guide.label_ko} — {_status_label(guide.status)}",
                    "",
                    guide.reason,
                    "",
                    f"- 준비 경로: {guide.acquisition.title}",
                    f"- 제출 방식: {guide.submission_label}",
                ]
            )
            if guide.acquisition.url:
                lines.append(f"- 공식 링크: {guide.acquisition.url}")
            for index, step in enumerate(guide.acquisition.steps, start=1):
                lines.append(f"  {index}. {step}")
            for item in guide.checklist:
                lines.append(f"  - [ ] {item}")

        if plan.preparations:
            lines.extend(["", "## 함께 챙길 준비물", ""])
            for item in plan.preparations:
                suffix = f" — {item.notes}" if item.notes else ""
                lines.append(f"- [ ] {item.label_ko}{suffix}")

        lines.extend(["", "## 제출 순서", "", plan.submission.description, ""])
        for index, step in enumerate(plan.submission.steps, start=1):
            lines.append(f"{index}. {step}")
        if plan.submission.url:
            lines.extend(["", f"공식 제출 안내: {plan.submission.url}"])

    if result.warnings:
        lines.extend(["", "## 확인할 제한사항", ""])
        lines.extend(f"- {warning}" for warning in result.warnings)
    lines.append("")
    return "\n".join(lines)


def _structured_result(result: AnalysisResponse) -> dict[str, object]:
    """Exclude source filenames and any raw extracted text from the archive."""
    return {
        "schema_version": "1.0",
        "session_id": str(result.session_id),
        "checked_at": result.checked_at.isoformat(),
        "task": result.task.model_dump(mode="json"),
        "overall_status": result.overall_status.value,
        "documents": [
            {
                "document_id": document.document_id,
                "doc_type": document.doc_type,
                "label_ko": document.label_ko,
                "confidence": document.confidence,
                "status": document.status.value,
                "reason_code": document.reason_code,
                "needs_user_confirm": document.needs_user_confirm,
                "classification_method": document.classification_method,
            }
            for document in result.documents
        ],
        "requirements": [item.model_dump(mode="json") for item in result.requirements],
        "completion_plan": (
            result.completion_plan.model_dump(mode="json")
            if result.completion_plan is not None
            else None
        ),
        "warnings": result.warnings,
        "contains_uploaded_originals": False,
    }


def build_preparation_kit(result: AnalysisResponse) -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("README.md", _markdown(result).encode("utf-8"))
        archive.writestr(
            "analysis-result.json",
            json.dumps(
                _structured_result(result),
                ensure_ascii=False,
                indent=2,
            ).encode("utf-8"),
        )
    return buffer.getvalue()
