"""분류 결과 JSON의 계약(스키마).

이 모듈의 출력은 **웹 화면과 규칙 엔진이 함께 쓰는 계약**이다. 지금은 파이썬이
파일로 뱉지만, 나중에 HTTP 응답이 되어도 모양은 같아야 한다. 그래야 데모를
실제 백엔드에 붙일 때 화면 코드를 다시 쓰지 않는다.

바꿀 때 규칙 두 가지.

1. 필드를 **더하는 것**은 SCHEMA_VERSION의 minor를 올린다. 읽는 쪽이 안 깨진다.
2. 필드를 **빼거나 의미를 바꾸는 것**은 major를 올리고, 영민(파이프라인)·
   찬우(검증)에게 알린다. 조용히 바꾸면 화면이 깨진다.

`validate()`는 의존성 없이 도는 최소 검사다. 스키마 위반을 조기에 잡는 게 목적이지
JSON Schema 전체를 구현하려는 게 아니다.
"""

from __future__ import annotations

from typing import Any

SCHEMA_VERSION = "1.0"

# 문서 하나의 관련성. 이 셋 외의 값은 쓰지 않는다.
RELEVANCE_VALUES = {"관련", "이번 업무에는 불필요", "판단 불가"}

# 최종 판정 다섯 상태는 규칙 엔진의 것이다. 이 모듈은 내보내지 않는다.
FIVE_STATUSES = {"준비 완료", "추가 필요", "기한 만료", "정보 불일치", "이번 업무에는 불필요"}


class SchemaError(ValueError):
    """출력이 계약을 어겼다."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SchemaError(message)


def validate(result: dict[str, Any]) -> dict[str, Any]:
    """분류 결과가 계약을 지키는지 확인한다. 어기면 SchemaError."""
    for key in ("schema_version", "task_id", "checked_at", "documents"):
        _require(key in result, f"최상위에 '{key}'가 없습니다")

    _require(
        str(result["schema_version"]).split(".")[0] == SCHEMA_VERSION.split(".")[0],
        f"스키마 major 버전이 다릅니다: {result['schema_version']} != {SCHEMA_VERSION}",
    )
    _require(isinstance(result["documents"], list), "documents는 배열이어야 합니다")

    for i, doc in enumerate(result["documents"]):
        where = f"documents[{i}]"
        for key in ("file_id", "source_name", "media", "classification", "relevance"):
            _require(key in doc, f"{where}에 '{key}'가 없습니다")

        classification = doc["classification"]
        for key in ("doc_type", "confidence", "evidence"):
            _require(key in classification, f"{where}.classification에 '{key}'가 없습니다")

        _require(
            classification["doc_type"] is None or isinstance(classification["doc_type"], str),
            f"{where}.classification.doc_type은 문자열이거나 null입니다",
        )
        _require(
            0.0 <= float(classification["confidence"]) <= 1.0,
            f"{where}.classification.confidence는 0~1 사이여야 합니다",
        )

        status = doc["relevance"].get("status")
        _require(
            status in RELEVANCE_VALUES,
            f"{where}.relevance.status가 계약 밖의 값입니다: {status!r}",
        )

        # 분류 실패를 '불필요'로 내보내면 서류 누락이 조용히 통과한다.
        _require(
            not (classification["doc_type"] is None and status == "이번 업무에는 불필요"),
            f"{where}: 분류 실패는 '판단 불가'여야 합니다. '불필요'로 내보내면 안 됩니다",
        )

        # 이 모듈은 다섯 상태를 판정하지 않는다. 섞여 들어오면 경계가 무너진 것이다.
        _require(
            status not in (FIVE_STATUSES - {"이번 업무에는 불필요"}),
            f"{where}: 다섯 상태 판정은 규칙 엔진의 몫입니다",
        )

        # 개인정보: 출력에 원문 텍스트를 담지 않는다.
        _require(
            "text" not in doc and "full_text" not in doc,
            f"{where}: 출력에 원문 텍스트를 담지 않습니다",
        )

    return result
