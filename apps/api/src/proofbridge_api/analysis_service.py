"""Replaceable boundary between HTTP uploads and document analysis."""

from __future__ import annotations

from datetime import date, timedelta
from functools import partial
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Protocol, Sequence
from uuid import uuid4

from fastapi import UploadFile
from starlette.concurrency import run_in_threadpool

from modules.doc_classify.classify import classify_files, load_signatures
from modules.doc_classify.extract import detect_kind
from modules.doc_classify.openai_classifier import OpenAIDocumentClassifier

from .config import Settings
from .contracts import (
    AcquisitionGuide,
    AnalysisResponse,
    CompletionDocumentGuide,
    CompletionPlan,
    DocumentMetadata,
    DocumentResult,
    DocumentStatus,
    PreparationGuide,
    SourceReference,
    SubmissionGuide,
    TaskSummary,
)
from .policy_service import PolicyContext, PostgreSQLPolicyService


_WRITE_CHUNK_BYTES = 1024 * 1024
_SUPPORTED_MAGIC_KINDS = {"pdf", "jpg", "png"}
_SUBMISSION_LABELS = {
    "original": "원본 지참",
    "original_or_copy": "원본 또는 사본",
    "photo_or_pdf": "사진 또는 PDF 제출",
    "printed_original_photo": "원본 문서 사진 제출",
    "auto_submit": "공식 자동 제출 경로",
}
_SYNTHETIC_DEMO_TYPES = {
    "합성_전기요금청구서": "utility_bill",
    "합성_관리비고지서": "management_fee_notice",
    "합성_주민등록표등본": "resident_registration_copy",
    "합성_세금고지서": "tax_bill",
    "합성_건강보험자격득실확인서": "health_insurance_certificate",
    "합성_근로계약서": "employment_contract",
    "합성_사업자등록증": "business_registration_certificate",
    "합성_휴대폰요금납부확인서": "mobile_phone_payment_certificate",
}


class UploadBoundaryError(ValueError):
    def __init__(self, *, code: str, message: str, recovery: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.recovery = recovery


class AnalysisPipeline(Protocol):
    async def analyze(
        self,
        *,
        task: TaskSummary,
        files: Sequence[UploadFile],
        expected_owner_name: str | None = None,
    ) -> AnalysisResponse: ...


class DocumentClassificationPipeline:
    """Run extraction and classification while failing closed on final judgment.

    OCR cache data and uploaded sources live under one request-scoped temporary
    directory. The directory is removed before this method returns, including
    error paths. Only the PII-minimized public result survives in SessionStore.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._policy_service = PostgreSQLPolicyService(settings.database_url)
        self._llm_classifier = (
            OpenAIDocumentClassifier(
                api_key=settings.openai_api_key or "",
                base_url=settings.openai_base_url,
                model=settings.openai_model,
                timeout_seconds=settings.llm_timeout_seconds,
                min_confidence=settings.llm_min_confidence,
            )
            if settings.llm_configured
            else None
        )

    async def analyze(
        self,
        *,
        task: TaskSummary,
        files: Sequence[UploadFile],
        expected_owner_name: str | None = None,
    ) -> AnalysisResponse:
        self._settings.session_temp_root.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(
            prefix="analysis-",
            dir=self._settings.session_temp_root,
        ) as temporary_directory:
            request_root = Path(temporary_directory)
            paths, source_names = await self._save_uploads(files, request_root)
            policy_context = await run_in_threadpool(self._policy_service.load, task)
            signatures = _merge_signatures(
                fallback=load_signatures(),
                policy_signatures=policy_context.signatures,
            )
            classify = partial(
                classify_files,
                paths,
                task.task_id,
                task_definition=policy_context.policy,
                use_ocr=self._settings.ocr_configured,
                signatures=signatures,
                cache_dir=request_root / "ocr-cache",
                ocr_timeout=self._settings.ocr_timeout_seconds,
                llm_classifier=self._llm_classifier,
                expected_owner_name=expected_owner_name,
            )
            raw_result = await run_in_threadpool(classify)
            return _to_analysis_response(
                raw_result=raw_result,
                task=task,
                source_names=source_names,
                ocr_configured=self._settings.ocr_configured,
                policy_service=self._policy_service,
                policy_context=policy_context,
            )

    async def _save_uploads(
        self,
        files: Sequence[UploadFile],
        request_root: Path,
    ) -> tuple[list[Path], list[str]]:
        paths: list[Path] = []
        source_names: list[str] = []
        for index, upload in enumerate(files, start=1):
            target = request_root / f"file-{index:03d}.upload"
            total_bytes = 0
            with target.open("wb") as output:
                while chunk := await upload.read(_WRITE_CHUNK_BYTES):
                    total_bytes += len(chunk)
                    if total_bytes > self._settings.max_upload_bytes:
                        raise UploadBoundaryError(
                            code="FILE_TOO_LARGE",
                            message="업로드 파일의 허용 크기를 초과했습니다.",
                            recovery=(
                                f"각 파일을 {self._settings.max_upload_bytes}바이트 "
                                "이하로 줄여주세요."
                            ),
                        )
                    output.write(chunk)

            if total_bytes == 0:
                raise UploadBoundaryError(
                    code="EMPTY_FILE",
                    message="빈 파일은 분석할 수 없습니다.",
                    recovery="내용이 있는 PDF, JPG 또는 PNG 파일을 사용해주세요.",
                )
            detected_kind = detect_kind(target)
            if detected_kind not in _SUPPORTED_MAGIC_KINDS:
                raise UploadBoundaryError(
                    code="INVALID_FILE_SIGNATURE",
                    message="파일 내용과 지원 형식이 일치하지 않습니다.",
                    recovery="정상적인 PDF, JPG 또는 PNG 파일을 사용해주세요.",
                )

            # Downstream extraction still validates the content with magic bytes,
            # while CLOVA General OCR requires a supported filename extension to
            # build images[].format. Keep the untrusted source name out of the
            # temporary path and assign an extension from the detected bytes.
            detected_target = target.with_suffix(f".{detected_kind}")
            target.rename(detected_target)
            target = detected_target

            paths.append(target)
            source_names.append(_safe_source_name(upload.filename, index))
        return paths, source_names


def _safe_source_name(filename: str | None, index: int) -> str:
    if not filename:
        return f"document-{index:03d}"
    return Path(filename).name[:255] or f"document-{index:03d}"


def _merge_signatures(
    *,
    fallback: list[dict],
    policy_signatures: list[dict],
) -> list[dict]:
    """Prefer PostgreSQL definitions while retaining known extra document types."""
    by_type = {signature["doc_type"]: signature for signature in fallback}
    by_type.update(
        {signature["doc_type"]: signature for signature in policy_signatures}
    )
    return [by_type[doc_type] for doc_type in sorted(by_type)]


def _issued_within_days(context: PolicyContext, doc_type: str | None) -> int | None:
    if not doc_type:
        return None
    limits = [
        int(rule["issued_within_days"])
        for requirement_set in context.policy["requirement_sets"]
        for rule in requirement_set["documents"]
        if rule["doc_type"] == doc_type and rule.get("issued_within_days") is not None
    ]
    # A document can appear in more than one alternative bundle. Applying the
    # strictest task-specific rule prevents a false READY result.
    return min(limits) if limits else None


def _document_status(
    document: dict,
    *,
    policy_context: PolicyContext | None = None,
    today: date | None = None,
) -> tuple[DocumentStatus, str]:
    relevance = document["relevance"]["status"]
    classification = document["classification"]
    metadata = document.get("metadata") or {}
    today = today or date.today()

    if classification.get("doc_type") == "UNRELATED":
        return DocumentStatus.UNNECESSARY, "CLEARLY_UNRELATED_DOCUMENT"
    if relevance == "이번 업무에는 불필요":
        return DocumentStatus.UNNECESSARY, "NOT_REQUIRED_FOR_TASK"
    if classification.get("doc_type") is None:
        return DocumentStatus.REVIEW_REQUIRED, "DOCUMENT_TYPE_UNKNOWN"
    if document.get("needs_user_confirm"):
        if classification.get("decided_by") == "openai":
            return DocumentStatus.REVIEW_REQUIRED, "AI_CLASSIFICATION_NEEDS_CONFIRMATION"
        return DocumentStatus.REVIEW_REQUIRED, "LOW_CLASSIFICATION_CONFIDENCE"

    metadata_type = metadata.get("document_type") or {}
    if metadata_type.get("status") in {"AMBIGUOUS", "NOT_FOUND"}:
        return DocumentStatus.REVIEW_REQUIRED, "DOCUMENT_TYPE_EVIDENCE_INCOMPLETE"
    if metadata_type.get("status") == "CONFIRMED" and (
        metadata_type.get("value") != classification.get("doc_type")
    ):
        return DocumentStatus.REVIEW_REQUIRED, "DOCUMENT_TYPE_EVIDENCE_CONFLICT"

    owner_match = (metadata.get("owner_match") or {}).get("status")
    if owner_match == "MISMATCH":
        return DocumentStatus.MISMATCH, "OWNER_NAME_MISMATCH"
    if owner_match in {"POSSIBLE_MATCH", "UNKNOWN"}:
        return DocumentStatus.REVIEW_REQUIRED, "OWNER_NAME_NEEDS_REVIEW"

    explicit_expiry = metadata.get("expires_at") or {}
    if explicit_expiry.get("status") == "AMBIGUOUS":
        return DocumentStatus.REVIEW_REQUIRED, "EXPLICIT_EXPIRY_AMBIGUOUS"
    if explicit_expiry.get("status") == "CONFIRMED" and explicit_expiry.get("value"):
        if date.fromisoformat(explicit_expiry["value"]) < today:
            return DocumentStatus.EXPIRED, "EXPLICIT_DOCUMENT_EXPIRY_PASSED"

    issued_limit = (
        _issued_within_days(policy_context, classification.get("doc_type"))
        if policy_context is not None
        else None
    )
    if issued_limit is not None:
        issued_at = metadata.get("issued_at") or {}
        if issued_at.get("status") != "CONFIRMED" or not issued_at.get("value"):
            return DocumentStatus.REVIEW_REQUIRED, "ISSUE_DATE_NOT_CONFIRMED"
        if date.fromisoformat(issued_at["value"]) + timedelta(days=issued_limit) < today:
            return DocumentStatus.EXPIRED, "TASK_ISSUE_DATE_LIMIT_PASSED"

    if classification.get("unverified_signature"):
        return DocumentStatus.REVIEW_REQUIRED, "UNVERIFIED_DOCUMENT_SIGNATURE"
    return DocumentStatus.READY, "DOCUMENT_CLASSIFIED"


def _synthetic_demo_hint(source_name: str, task: TaskSummary) -> str | None:
    """Recognize only our explicitly named synthetic fixtures without OCR.

    This is a fail-safe demo path, not a production document classifier. The
    resulting document still requires user confirmation and can never become
    READY from its filename alone.
    """
    if not task.demo_available:
        return None
    stem = Path(source_name).stem
    if stem.endswith("_스캔"):
        stem = stem.removesuffix("_스캔")
    return _SYNTHETIC_DEMO_TYPES.get(stem)


def _to_analysis_response(
    *,
    raw_result: dict,
    task: TaskSummary,
    source_names: list[str],
    ocr_configured: bool,
    policy_service: PostgreSQLPolicyService,
    policy_context: PolicyContext,
) -> AnalysisResponse:
    documents: list[DocumentResult] = []
    comparison_tokens: dict[str, dict[str, str]] = {}
    used_synthetic_demo_hint = False
    for index, document in enumerate(raw_result["documents"]):
        classification = document["classification"]
        hinted_doc_type = None
        if classification.get("doc_type") is None and not ocr_configured:
            hinted_doc_type = _synthetic_demo_hint(source_names[index], task)

        if hinted_doc_type:
            used_synthetic_demo_hint = True
            signature = next(
                (
                    item
                    for item in policy_context.signatures
                    if item["doc_type"] == hinted_doc_type
                ),
                None,
            )
            classification = {
                **classification,
                "doc_type": hinted_doc_type,
                "label_ko": (
                    signature.get("label_ko") if signature else hinted_doc_type
                ),
                "confidence": 0.5,
            }
            document_for_status = {
                **document,
                "classification": classification,
                "relevance": {"status": "관련", "matched_rule": "demo_hint"},
                "needs_user_confirm": True,
            }
            document_status = DocumentStatus.REVIEW_REQUIRED
            reason_code = "SYNTHETIC_SAMPLE_FILENAME_HINT"
        else:
            document_for_status = document
            document_status, reason_code = _document_status(
                document_for_status,
                policy_context=policy_context,
            )
        metadata = DocumentMetadata.model_validate(document.get("metadata"))
        documents.append(
            DocumentResult(
                document_id=document["file_id"],
                source_name=source_names[index],
                doc_type=classification.get("doc_type"),
                label_ko=classification.get("label_ko"),
                confidence=classification["confidence"],
                status=document_status,
                reason_code=reason_code,
                needs_user_confirm=bool(
                    document_for_status.get("needs_user_confirm")
                ),
                classification_method=(
                    "demo_hint"
                    if hinted_doc_type
                    else classification.get("decided_by") or "unknown"
                ),
                metadata=metadata,
            )
        )
        comparison_tokens[document["file_id"]] = dict(
            (document.get("fields") or {}).get("comparison_tokens") or {}
        )

    assessment = policy_service.assess(
        context=policy_context,
        task=task,
        documents=documents,
        comparison_tokens=comparison_tokens,
    )
    completion_plan = _build_completion_plan(
        context=policy_context,
        task=task,
        requirements=assessment.requirements,
        documents=documents,
    )
    warnings = list(assessment.warnings)
    if not ocr_configured:
        warnings.append(
            "OCR이 설정되지 않아 텍스트가 없는 이미지·스캔 PDF는 사용자 확인이 필요합니다."
        )
    if used_synthetic_demo_hint:
        warnings.append(
            "테스트용 합성 샘플은 OCR 미설정 상태에서 샘플 파일명 힌트로 분류했으며, "
            "실제 문서 판정이나 준비 완료 근거로 사용하지 않습니다."
        )
    if raw_result.get("llm_calls_total", 0):
        warnings.append(
            "규칙과 OCR만으로 확정되지 않은 문서에 OpenAI 보조 분류를 사용했습니다. "
            "최종 준비 상태는 PostgreSQL의 공식 출처 기반 규칙으로 판정합니다."
        )

    return AnalysisResponse(
        session_id=uuid4(),
        task=task,
        overall_status=assessment.overall_status,
        checked_at=AnalysisResponse.checked_now(),
        documents=documents,
        requirements=assessment.requirements,
        completion_plan=completion_plan,
        warnings=warnings,
    )


def apply_user_classification(
    *,
    current: AnalysisResponse,
    document_id: str,
    doc_type: str,
    settings: Settings,
) -> AnalysisResponse:
    """Apply a user's type confirmation without treating it as document proof.

    The uploaded source is already gone at this point. A user confirmation can
    correct the type used for policy matching, but it cannot verify authenticity,
    extracted fields, issue dates, or a document signature. It therefore remains
    REVIEW_REQUIRED and can never create a false READY result by itself.
    """
    policy_service = PostgreSQLPolicyService(settings.database_url)
    context = policy_service.load(current.task)
    signature = next(
        (item for item in context.signatures if item["doc_type"] == doc_type),
        None,
    )
    if signature is None:
        raise LookupError(doc_type)

    found = False
    documents: list[DocumentResult] = []
    for document in current.documents:
        if document.document_id != document_id:
            documents.append(document)
            continue
        found = True
        documents.append(
            document.model_copy(
                update={
                    "doc_type": doc_type,
                    "label_ko": signature.get("label_ko") or doc_type,
                    "status": DocumentStatus.REVIEW_REQUIRED,
                    "reason_code": "USER_CONFIRMED_DOCUMENT_TYPE",
                    "needs_user_confirm": False,
                    "classification_method": "user_confirmed",
                }
            )
        )
    if not found:
        raise KeyError(document_id)

    assessment = policy_service.assess(
        context=context,
        task=current.task,
        documents=documents,
        comparison_tokens=None,
    )
    completion_plan = _build_completion_plan(
        context=context,
        task=current.task,
        requirements=assessment.requirements,
        documents=documents,
    )
    warnings = [
        *assessment.warnings,
        "사용자가 문서 종류를 확인했습니다. 진위·발급일·내용 검증이 아니므로 원문 확인이 계속 필요합니다.",
    ]
    return current.model_copy(
        update={
            "overall_status": assessment.overall_status,
            "checked_at": AnalysisResponse.checked_now(),
            "documents": documents,
            "requirements": assessment.requirements,
            "completion_plan": completion_plan,
            "warnings": list(dict.fromkeys(warnings)),
        }
    )


def _build_completion_plan(
    *,
    context: PolicyContext,
    task: TaskSummary,
    requirements: list,
    documents: list[DocumentResult],
) -> CompletionPlan | None:
    if not requirements:
        return None
    requirement = next((item for item in requirements if item.blocking), requirements[0])
    if not requirement.bundles:
        return None
    bundle = next(
        (
            item
            for item in requirement.bundles
            if item.bundle_code == requirement.matched_bundle_code
        ),
        None,
    )
    if bundle is None:
        bundle = sorted(
            requirement.bundles,
            key=lambda item: (
                -len(item.evidence_document_ids),
                len(item.missing_document_types),
                item.bundle_code,
            ),
        )[0]

    requirement_set = next(
        (
            item
            for item in context.policy["requirement_sets"]
            if requirement.requirement_id.startswith(
                f"{item['requirement_code']}:"
            )
        ),
        context.policy["requirement_sets"][0],
    )
    rules = [
        rule
        for rule in requirement_set["documents"]
        if (rule.get("bundle_code") or rule["doc_type"]) == bundle.bundle_code
    ]
    signatures = {
        signature["doc_type"]: signature for signature in context.signatures
    }
    documents_by_type = {
        document.doc_type: document
        for document in documents
        if document.doc_type is not None
    }
    source = requirement.source
    document_guides: list[CompletionDocumentGuide] = []
    for rule in rules:
        doc_type = rule["doc_type"]
        signature = signatures.get(doc_type, {})
        current = documents_by_type.get(doc_type)
        status = current.status if current else DocumentStatus.MISSING
        acquisition_payload = (
            rule.get("acquisition")
            or signature.get("acquisition")
            or {}
        )
        acquisition_source = SourceReference(
            title=acquisition_payload.get("source_title") or source.title,
            url=acquisition_payload.get("source_url") or source.url,
            last_checked=acquisition_payload.get("last_checked") or source.last_checked,
            verified=bool(acquisition_payload.get("verified", False)),
        )
        issuer = signature.get("issuer") or "발급·제공 기관"
        acquisition = AcquisitionGuide(
            title=acquisition_payload.get("title") or f"{issuer}에서 서류 확보",
            channel=acquisition_payload.get("channel") or "issuer_direct",
            description=acquisition_payload.get("description")
            or "발급·제공 기관에 최신 서류의 확보 방법을 확인하세요.",
            steps=acquisition_payload.get("steps")
            or [
                f"{issuer}에 해당 서류의 발급 또는 제공을 요청합니다.",
                "명의, 주소와 발급일 등 이번 업무에 필요한 정보를 확인합니다.",
                "선택한 은행의 공식 안내에 맞는 제출 형태로 준비합니다.",
            ],
            url=acquisition_payload.get("url"),
            action_label=acquisition_payload.get("action_label"),
            source=acquisition_source,
        )
        if current is None:
            reason = "아직 업로드한 문서에서 찾지 못해 먼저 준비해야 합니다."
        elif current.status is DocumentStatus.READY:
            reason = "공개 기준에서 사용할 문서로 확인했습니다."
        else:
            reason = "문서는 찾았지만 자동 판정을 확정할 수 없어 원문 확인이 필요합니다."
        checklist = ["문서의 명의와 현재 정보가 일치하는지 확인"]
        if rule["submission_method"] == "original":
            checklist.append("발급된 원본을 훼손하지 않고 지참")
        elif rule["submission_method"] == "printed_original_photo":
            checklist.append("원본 문서 전체가 보이도록 촬영해 제출")
        elif rule["submission_method"] == "auto_submit":
            checklist.append("공식 전자 제출 경로에서 직접 전송")
        else:
            checklist.append("공식 안내가 허용한 사본·사진·PDF 형식을 확인")
        if rule.get("notes"):
            checklist.append(rule["notes"])
        document_guides.append(
            CompletionDocumentGuide(
                doc_type=doc_type,
                label_ko=signature.get("label_ko") or doc_type,
                status=status,
                reason=reason,
                acquisition=acquisition,
                submission_method=rule["submission_method"],
                submission_label=_SUBMISSION_LABELS.get(
                    rule["submission_method"], rule["submission_method"]
                ),
                checklist=checklist,
            )
        )

    preparations = [
        PreparationGuide(
            code=item["code"],
            label_ko=item["label_ko"],
            notes=item.get("notes"),
        )
        for item in requirement_set["preparations"]
    ]
    expected_review = next(
        (
            condition["description"]
            for condition in context.policy.get("policy_conditions", [])
            if condition["result_code"] == "bank_review_2_to_3_business_days"
        ),
        None,
    )
    bank_name = task.bank_name_ko or task.label_ko.split()[0]
    if task.channel == "non_face_to_face":
        submission_title = f"{bank_name} 공식 앱·웹에서 신청"
        submission_description = (
            "공식 안내에서 지정한 디지털 채널과 파일 형식으로 제출합니다."
        )
        submission_steps = [
            f"{bank_name} 공식 안내 링크에서 해당 업무의 신청 메뉴를 확인합니다.",
            "선택한 증빙 묶음의 모든 문서와 비문서 준비물을 확인합니다.",
            "원본·출력·사진·PDF 중 정책에 표시된 제출 형식으로 제출합니다.",
        ]
    else:
        submission_title = f"{bank_name} 영업점에서 신청"
        submission_description = (
            "원본 지참 여부와 대리인·대표자 준비물을 확인한 뒤 영업점을 방문합니다."
        )
        submission_steps = [
            f"{bank_name} 공식 안내에서 담당 영업점과 방문 가능 시간을 확인합니다.",
            "선택한 증빙 묶음의 원본·사본과 비문서 준비물을 함께 챙깁니다.",
            f"창구에서 ‘{task.label_ko}’ 업무를 요청하고 추가 확인에 응답합니다.",
        ]
    return CompletionPlan(
        bundle_code=bundle.bundle_code,
        bundle_label=bundle.label_ko,
        status=requirement.status,
        documents=document_guides,
        preparations=preparations,
        submission=SubmissionGuide(
            title=submission_title,
            description=submission_description,
            steps=submission_steps,
            url=source.url,
            action_label=f"{bank_name} 공식 안내 보기",
            expected_review=expected_review,
            source=source,
        ),
    )
