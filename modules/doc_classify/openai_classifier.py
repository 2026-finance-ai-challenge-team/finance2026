"""Privacy-minimized OpenAI fallback for ambiguous document classification.

This module never sends the source file or full extracted text. It sends a
small set of redacted, numbered text signals and accepts only a strict JSON
decision. The caller remains responsible for policy/rule evaluation.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

_MAX_SIGNALS = 40
_MAX_SIGNAL_CHARS = 160
UNRELATED_DOC_TYPE = "UNRELATED"

_EMAIL = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)
_PHONE = re.compile(r"(?<!\d)(?:\+?82[- ]?)?0\d{1,2}[- ]?\d{3,4}[- ]?\d{4}(?!\d)")
_RESIDENT_NUMBER = re.compile(r"(?<!\d)\d{6}\s*[- ]?\s*[1-8]\d{6}(?!\d)")
_LONG_NUMBER = re.compile(r"(?<!\d)\d(?:[- ]?\d){5,}(?!\d)")
_ADDRESS_LINE = re.compile(r"(주소|소재지|거주지|사용장소|사업장)", re.IGNORECASE)
_PERSON_LABEL = re.compile(
    r"^(성명|이름|대표자|세대주(?:\s*성명)?|가입자(?:명|\s*성명)?|"
    r"입주자명|근로자|납세자|고객명)\s*[:：]?\s*(.+)$"
)
_PERSON_LABEL_ONLY = re.compile(
    r"^(성명|이름|대표자|세대주(?:\s*성명)?|가입자(?:명|\s*성명)?|"
    r"입주자명|근로자|납세자|고객명)\s*[:：]?$"
)
_ADDRESS_LABEL_ONLY = re.compile(r"^(주소|소재지|거주지|사용장소|사업장)\s*[:：]?$", re.IGNORECASE)
_POSSIBLE_PERSON_NAME = re.compile(r"^[가-힣]{2,4}$")


@dataclass(frozen=True)
class LlmClassificationDecision:
    doc_type: str
    confidence: float
    evidence_signal_ids: tuple[str, ...]
    candidate_doc_types: tuple[str, ...]


class OpenAIDocumentClassifier:
    """Responses API client with Structured Outputs and fail-closed parsing."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str | None = None,
        model: str,
        timeout_seconds: float,
        min_confidence: float,
        client: Any | None = None,
    ) -> None:
        if not api_key.strip() and client is None:
            raise ValueError("OpenAI API key is required")
        if not 0.0 < min_confidence <= 1.0:
            raise ValueError("min_confidence must be in (0, 1]")
        if client is None:
            from openai import OpenAI

            client_options: dict[str, Any] = {
                "api_key": api_key,
                "timeout": timeout_seconds,
            }
            if base_url:
                client_options["base_url"] = base_url.rstrip("/") + "/"
            client = OpenAI(**client_options)
        self._client = client
        self._model = model
        self._min_confidence = min_confidence

    def classify(
        self,
        *,
        text: str,
        title_text: str,
        signatures: list[dict[str, Any]],
    ) -> LlmClassificationDecision | None:
        allowed_types = sorted(
            {
                str(signature["doc_type"])
                for signature in signatures
                if signature.get("doc_type")
            }
        )
        if not allowed_types:
            return None

        signals = build_redacted_signals(text=text, title_text=title_text)
        if not signals:
            return None

        catalog = [
            {
                "doc_type": signature["doc_type"],
                "label_ko": signature.get("label_ko"),
                "issuer": signature.get("issuer"),
            }
            for signature in signatures
            if signature.get("doc_type") in allowed_types
        ]
        schema = _response_schema(allowed_types)
        response = self._client.responses.create(
            model=self._model,
            store=False,
            input=[
                {
                    "role": "system",
                    "content": [
                        {
                            "type": "input_text",
                            "text": (
                                "You classify Korean administrative and financial documents. "
                                "Use only the provided redacted signals. Do not infer personal "
                                "data. Return UNRELATED only when the signals clearly identify a "
                                "document outside the provided catalog. Return UNKNOWN when the "
                                "document is unreadable, evidence is insufficient, or the choice "
                                "is ambiguous."
                            ),
                        }
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": json.dumps(
                                {"document_catalog": catalog, "signals": signals},
                                ensure_ascii=False,
                            ),
                        }
                    ],
                },
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "proofbridge_document_classification",
                    "strict": True,
                    "schema": schema,
                }
            },
        )
        return self._parse_response(
            response=response,
            allowed_types=set(allowed_types),
            allowed_signal_ids={signal["signal_id"] for signal in signals},
        )

    def _parse_response(
        self,
        *,
        response: Any,
        allowed_types: set[str],
        allowed_signal_ids: set[str],
    ) -> LlmClassificationDecision | None:
        output_text = getattr(response, "output_text", "")
        if not output_text:
            return None
        try:
            payload = json.loads(output_text)
            doc_type = str(payload["doc_type"])
            confidence = float(payload["confidence"])
            evidence_ids = tuple(str(item) for item in payload["evidence_signal_ids"])
            candidates = tuple(str(item) for item in payload["candidate_doc_types"])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return None

        if doc_type == "UNKNOWN":
            return None
        if doc_type not in {*allowed_types, UNRELATED_DOC_TYPE}:
            return None
        if not 0.0 <= confidence <= 1.0 or confidence < self._min_confidence:
            return None
        if not evidence_ids or not set(evidence_ids).issubset(allowed_signal_ids):
            return None
        if not set(candidates).issubset(allowed_types):
            return None
        return LlmClassificationDecision(
            doc_type=doc_type,
            confidence=confidence,
            evidence_signal_ids=evidence_ids,
            candidate_doc_types=candidates,
        )


def build_redacted_signals(*, text: str, title_text: str = "") -> list[dict[str, str]]:
    """Return bounded signals with common Korean PII removed."""
    candidates: list[str] = []
    if title_text.strip():
        candidates.append(title_text.strip())
    candidates.extend(line.strip() for line in text.splitlines() if line.strip())

    signals: list[dict[str, str]] = []
    seen: set[str] = set()
    redact_next_as: str | None = None
    for candidate in candidates:
        if redact_next_as is not None:
            redacted = redact_next_as
            redact_next_as = None
        else:
            redacted = _redact(candidate)
            if _PERSON_LABEL_ONLY.match(candidate):
                redact_next_as = "[PERSON_REDACTED]"
            elif _ADDRESS_LABEL_ONLY.match(candidate):
                redact_next_as = "[ADDRESS_REDACTED]"
        redacted = re.sub(r"\s+", " ", redacted).strip()[:_MAX_SIGNAL_CHARS]
        if not redacted or redacted in seen:
            continue
        seen.add(redacted)
        signals.append(
            {"signal_id": f"s{len(signals) + 1:02d}", "text": redacted}
        )
        if len(signals) >= _MAX_SIGNALS:
            break
    return signals


def _redact(value: str) -> str:
    if _ADDRESS_LINE.search(value):
        label = _ADDRESS_LINE.search(value)
        return f"{label.group(1)}: [ADDRESS_REDACTED]" if label else "[ADDRESS_REDACTED]"
    person = _PERSON_LABEL.match(value.strip())
    if person:
        return f"{person.group(1)}: [PERSON_REDACTED]"
    if _POSSIBLE_PERSON_NAME.match(value.strip()):
        return "[POSSIBLE_PERSON_REDACTED]"
    value = _EMAIL.sub("[EMAIL_REDACTED]", value)
    value = _PHONE.sub("[PHONE_REDACTED]", value)
    value = _RESIDENT_NUMBER.sub("[ID_REDACTED]", value)
    return _LONG_NUMBER.sub("[NUMBER_REDACTED]", value)


def _response_schema(allowed_types: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "doc_type": {
                "type": "string",
                "enum": [*allowed_types, UNRELATED_DOC_TYPE, "UNKNOWN"],
            },
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "evidence_signal_ids": {
                "type": "array",
                "items": {"type": "string"},
            },
            "candidate_doc_types": {
                "type": "array",
                "items": {"type": "string", "enum": allowed_types},
            },
        },
        "required": [
            "doc_type",
            "confidence",
            "evidence_signal_ids",
            "candidate_doc_types",
        ],
    }
