"""Build an LLM-safe explanation payload from an immutable assessment result."""

from __future__ import annotations

from typing import TypedDict

from schemas import Assessment, OverallStatus


class PromptRequirement(TypedDict):
    requirement_id: str
    status: str
    blocking: bool
    reason_code: str
    evidence: list[str]


class PromptConsistencyCheck(TypedDict):
    check_id: str
    status: str
    reason_code: str
    evidence: list[str]


class PromptAssessment(TypedDict):
    overall_status: str
    requirements: list[PromptRequirement]
    consistency_checks: list[PromptConsistencyCheck]


class ExplanationPromptPayload(TypedDict):
    task: str
    language: str
    constraints: list[str]
    assessment: PromptAssessment


_BASE_CONSTRAINTS = (
    "어떠한 규칙 상태도 변경하지 않는다.",
    "추가적인 은행 업무 요구사항을 임의로 생성하지 않는다.",
    "제공된 심사 결과만 설명한다.",
    "UNKNOWN을 거절로 설명하지 않는다.",
    "필요한 다음 조치를 명확하게 설명한다.",
    "현재 제출된 서류 기준의 PoC 검증 결과로만 설명한다.",
    "실제 은행의 최종 승인, 계좌 개설 승인 또는 규제·컴플라이언스 최종 승인을 주장하지 않는다.",
)

_STATUS_CONSTRAINTS = {
    OverallStatus.READY: (
        "모든 blocking 요구사항이 충족되었음을 설명하되, 실제 은행 승인으로 표현하지 않는다.",
    ),
    OverallStatus.ACTION_REQUIRED: (
        "UNSATISFIED requirement와 해당 reason_code를 결정론적으로 충족되지 않은 사항으로 설명한다.",
        "UNKNOWN requirement를 UNSATISFIED requirement처럼 설명하지 않는다.",
    ),
    OverallStatus.REVIEW_REQUIRED: (
        "추가 확인 필요: UNKNOWN은 현재 evidence만으로 결정하기에 정보가 부족한 상태이며 거절이나 실패가 아님을 설명한다.",
    ),
}


def build_explanation_prompt(assessment: Assessment) -> ExplanationPromptPayload:
    """Project only allowlisted, LLM-safe assessment data into a JSON payload."""

    return {
        "task": "explain_document_assessment",
        "language": "ko",
        "constraints": [
            *_BASE_CONSTRAINTS,
            *_STATUS_CONSTRAINTS[assessment.overall_status],
        ],
        "assessment": {
            "overall_status": assessment.overall_status.value,
            "requirements": [
                {
                    "requirement_id": requirement.requirement_id,
                    "status": requirement.status.value,
                    "blocking": requirement.blocking,
                    "reason_code": requirement.reason_code,
                    "evidence": list(requirement.evidence),
                }
                for requirement in assessment.requirements
            ],
            "consistency_checks": [
                {
                    "check_id": consistency_check.check_id,
                    "status": consistency_check.status.value,
                    "reason_code": consistency_check.reason_code,
                    "evidence": list(consistency_check.evidence_document_ids),
                }
                for consistency_check in assessment.consistency_checks
            ],
        },
    }
