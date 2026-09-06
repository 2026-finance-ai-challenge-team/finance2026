from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from modules.doc_classify.classify import classify_files, load_signatures
from modules.doc_classify.openai_classifier import (
    LlmClassificationDecision,
    OpenAIDocumentClassifier,
    UNRELATED_DOC_TYPE,
    build_redacted_signals,
)


class _FakeResponses:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(output_text=json.dumps(self.payload))


class _FakeClient:
    def __init__(self, payload: dict) -> None:
        self.responses = _FakeResponses(payload)


def _signature() -> dict:
    return {
        "doc_type": "resident_registration_copy",
        "label_ko": "주민등록표 등본",
        "issuer": "행정안전부",
        "issuer_aliases": ["정부24"],
    }


def test_redacted_signals_remove_common_personal_information() -> None:
    signals = build_redacted_signals(
        title_text="주민등록표 등본",
        text=(
            "성명\n홍길동\n주소: 서울특별시 중구 세종대로 1\n"
            "주민등록번호 900101-1234567\n전화 010-1234-5678\n"
            "이메일 gildong@example.com"
        ),
    )
    serialized = json.dumps(signals, ensure_ascii=False)

    assert "홍길동" not in serialized
    assert "세종대로" not in serialized
    assert "900101-1234567" not in serialized
    assert "010-1234-5678" not in serialized
    assert "gildong@example.com" not in serialized
    assert "[PERSON_REDACTED]" in serialized
    assert "[ADDRESS_REDACTED]" in serialized


def test_openai_classifier_uses_structured_output_and_store_false() -> None:
    client = _FakeClient(
        {
            "doc_type": "resident_registration_copy",
            "confidence": 0.93,
            "evidence_signal_ids": ["s01", "s02"],
            "candidate_doc_types": ["resident_registration_copy"],
        }
    )
    classifier = OpenAIDocumentClassifier(
        api_key="",
        model="gpt-5.4-mini",
        timeout_seconds=10,
        min_confidence=0.85,
        client=client,
    )

    decision = classifier.classify(
        title_text="주민등록표 등본",
        text="정부24\n성명: 홍길동\n주소: 서울특별시 중구",
        signatures=[_signature()],
    )

    assert decision is not None
    assert decision.doc_type == "resident_registration_copy"
    request = client.responses.calls[0]
    assert request["store"] is False
    assert request["text"]["format"]["strict"] is True
    serialized_input = json.dumps(request["input"], ensure_ascii=False)
    assert "홍길동" not in serialized_input
    assert "서울특별시" not in serialized_input


def test_openai_classifier_passes_compatible_proxy_base_url() -> None:
    with patch("openai.OpenAI") as constructor:
        OpenAIDocumentClassifier(
            api_key="synthetic-proxy-key",
            base_url="http://127.0.0.1:8317/v1",
            model="proxy-model",
            timeout_seconds=10,
            min_confidence=0.85,
        )

    constructor.assert_called_once_with(
        api_key="synthetic-proxy-key",
        base_url="http://127.0.0.1:8317/v1/",
        timeout=10,
    )


def test_openai_classifier_rejects_low_confidence_or_unknown_evidence() -> None:
    client = _FakeClient(
        {
            "doc_type": "resident_registration_copy",
            "confidence": 0.7,
            "evidence_signal_ids": ["not-sent"],
            "candidate_doc_types": ["resident_registration_copy"],
        }
    )
    classifier = OpenAIDocumentClassifier(
        api_key="",
        model="gpt-5.4-mini",
        timeout_seconds=10,
        min_confidence=0.85,
        client=client,
    )

    assert (
        classifier.classify(
            title_text="주민등록표 등본",
            text="정부24",
            signatures=[_signature()],
        )
        is None
    )


def test_openai_classifier_accepts_explicit_unrelated_decision() -> None:
    client = _FakeClient(
        {
            "doc_type": UNRELATED_DOC_TYPE,
            "confidence": 0.96,
            "evidence_signal_ids": ["s01"],
            "candidate_doc_types": [],
        }
    )
    classifier = OpenAIDocumentClassifier(
        api_key="",
        model="gpt-5.4-mini",
        timeout_seconds=10,
        min_confidence=0.85,
        client=client,
    )

    decision = classifier.classify(
        title_text="동아리 행사 결과 보고서",
        text="동아리 행사 결과 보고서\n참가 인원과 만족도 조사",
        signatures=[_signature()],
    )

    assert decision is not None
    assert decision.doc_type == UNRELATED_DOC_TYPE


class _CountingClassifier:
    def __init__(self, decision: LlmClassificationDecision | None = None) -> None:
        self.calls = 0
        self.decision = decision

    def classify(self, **kwargs):
        self.calls += 1
        return self.decision


def test_explicit_unrelated_decision_is_not_user_review() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    signature = {
        **_signature(),
        "title_patterns": [r"절대일치하지않는제목"],
        "required_anchors": [],
        "negative_anchors": [],
        "verified": True,
    }
    classifier = _CountingClassifier(
        LlmClassificationDecision(
            doc_type=UNRELATED_DOC_TYPE,
            confidence=0.96,
            evidence_signal_ids=("s01",),
            candidate_doc_types=(),
        )
    )

    result = classify_files(
        [repo_root / "demo_docs" / "합성_전기요금청구서.pdf"],
        "kakaobank.limit_account_release",
        use_ocr=False,
        signatures=[signature],
        llm_classifier=classifier,
    )

    document = result["documents"][0]
    assert document["classification"]["doc_type"] == UNRELATED_DOC_TYPE
    assert document["relevance"]["status"] == "이번 업무에는 불필요"
    assert document["needs_user_confirm"] is False


def test_rule_classification_skips_llm_call() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    classifier = _CountingClassifier()

    result = classify_files(
        [repo_root / "demo_docs" / "합성_전기요금청구서.pdf"],
        "kakaobank.limit_account_release",
        use_ocr=False,
        llm_classifier=classifier,
    )

    assert classifier.calls == 0
    assert result["llm_calls_total"] == 0


def test_ambiguous_rule_result_can_use_llm_classification() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    signature = {
        **_signature(),
        "doc_type": "utility_bill",
        "label_ko": "전기요금 청구서",
        "title_patterns": [r"절대일치하지않는제목"],
        "required_anchors": [],
        "negative_anchors": [],
        "verified": True,
    }
    classifier = _CountingClassifier(
        LlmClassificationDecision(
            doc_type="utility_bill",
            confidence=0.92,
            evidence_signal_ids=("s01",),
            candidate_doc_types=("utility_bill",),
        )
    )

    result = classify_files(
        [repo_root / "demo_docs" / "합성_전기요금청구서.pdf"],
        "kakaobank.limit_account_release",
        use_ocr=False,
        signatures=[signature],
        llm_classifier=classifier,
    )

    assert classifier.calls == 1
    assert result["llm_calls_total"] == 1
    assert result["documents"][0]["classification"]["decided_by"] == "openai"
    assert result["documents"][0]["classification"]["doc_type"] == "utility_bill"
    assert result["documents"][0]["needs_user_confirm"] is True
