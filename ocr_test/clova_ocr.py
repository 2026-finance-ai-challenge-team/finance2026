"""네이버 CLOVA OCR General API 최소 클라이언트 (테스트용).

- 제품 페이지: https://www.ncloud.com/product/aiService/ocr
- 인증: 요청 헤더 `X-OCR-SECRET` (OCR 도메인별 Secret Key)
- 엔드포인트: 도메인 생성 시 발급되는 APIGW Invoke URL (`.../general`)

여기서는 인식(텍스트 추출)만 한다. 준비 상태 판정(다섯 상태)은 규칙 엔진의 몫이므로
이 모듈에 넣지 않는다.
"""

from __future__ import annotations

import json
import mimetypes
import os
import re
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

import requests

# CLOVA OCR General API가 받는 이미지 포맷
SUPPORTED_FORMATS = {"jpg", "jpeg", "png", "pdf", "tiff", "tif"}

ENV_SECRET_KEY = "NCP_OCR_SECRET_KEY"
ENV_INVOKE_URL = "NCP_OCR_INVOKE_URL"


class ClovaOcrError(RuntimeError):
    """요청 구성 실패, HTTP 오류, inferResult 실패를 함께 표현한다."""


# ---------------------------------------------------------------------------
# 설정 로딩
# ---------------------------------------------------------------------------


def load_dotenv(path: str | os.PathLike[str]) -> dict[str, str]:
    """`KEY=VALUE` 형식의 .env를 읽어 os.environ에 채운다(기존 값 우선).

    python-dotenv 의존성을 추가하지 않기 위한 최소 구현. 따옴표와 `export ` 접두사,
    `#` 주석만 처리한다.
    """
    loaded: dict[str, str] = {}
    env_path = Path(path)
    if not env_path.is_file():
        return loaded

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'\"")
        if not key:
            continue
        loaded[key] = value
        os.environ.setdefault(key, value)
    return loaded


@dataclass(frozen=True)
class OcrConfig:
    invoke_url: str
    secret_key: str
    timeout: float = 30.0

    @classmethod
    def from_env(cls, timeout: float = 30.0) -> "OcrConfig":
        invoke_url = (os.environ.get(ENV_INVOKE_URL) or "").strip()
        secret_key = (os.environ.get(ENV_SECRET_KEY) or "").strip()

        missing = [
            name
            for name, value in ((ENV_INVOKE_URL, invoke_url), (ENV_SECRET_KEY, secret_key))
            if not value
        ]
        if missing:
            raise ClovaOcrError(
                "환경변수가 비어 있습니다: "
                + ", ".join(missing)
                + "\nocr_test/.env.example을 ocr_test/.env로 복사한 뒤 값을 채우세요."
            )
        if not invoke_url.startswith("https://"):
            raise ClovaOcrError(f"{ENV_INVOKE_URL}가 https URL이 아닙니다: {invoke_url!r}")
        return cls(invoke_url=invoke_url, secret_key=secret_key, timeout=timeout)


# ---------------------------------------------------------------------------
# 요청
# ---------------------------------------------------------------------------


def image_format_of(path: Path) -> str:
    """확장자를 API가 요구하는 `images[].format` 값으로 정규화한다."""
    ext = path.suffix.lower().lstrip(".")
    if ext == "tif":
        ext = "tiff"
    if ext == "jpeg":
        ext = "jpg"
    if ext not in SUPPORTED_FORMATS:
        raise ClovaOcrError(
            f"지원하지 않는 확장자입니다: {path.suffix!r} "
            f"(가능: {', '.join(sorted(SUPPORTED_FORMATS))})"
        )
    return ext


def build_message(
    *,
    image_name: str,
    image_format: str,
    lang: str = "ko",
    enable_table_detection: bool = False,
    request_id: str | None = None,
) -> dict[str, Any]:
    """multipart의 `message` 파트에 실릴 JSON을 만든다."""
    return {
        "version": "V2",
        "requestId": request_id or str(uuid.uuid4()),
        "timestamp": int(time.time() * 1000),
        "lang": lang,
        "enableTableDetection": enable_table_detection,
        "images": [{"format": image_format, "name": image_name}],
    }


def call_general_ocr(
    image_path: str | os.PathLike[str],
    config: OcrConfig,
    *,
    lang: str = "ko",
    enable_table_detection: bool = False,
    session: requests.Session | None = None,
) -> tuple[dict[str, Any], float]:
    """이미지 한 장을 General OCR에 보내고 (응답 JSON, 소요 초)를 돌려준다."""
    path = Path(image_path).expanduser()
    if not path.is_file():
        raise ClovaOcrError(f"파일을 찾을 수 없습니다: {path}")

    image_format = image_format_of(path)
    message = build_message(
        image_name=path.stem or "image",
        image_format=image_format,
        lang=lang,
        enable_table_detection=enable_table_detection,
    )

    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    payload = path.read_bytes()

    http = session or requests
    started = time.perf_counter()
    try:
        response = http.post(
            config.invoke_url,
            headers={"X-OCR-SECRET": config.secret_key},
            data={"message": json.dumps(message, ensure_ascii=False)},
            files={"file": (path.name, payload, mime)},
            timeout=config.timeout,
        )
    except requests.RequestException as exc:  # 네트워크/타임아웃
        raise ClovaOcrError(f"요청 실패: {exc}") from exc
    elapsed = time.perf_counter() - started

    if response.status_code != 200:
        raise ClovaOcrError(
            f"HTTP {response.status_code}: {_summarize_error(response)}\n"
            "401/403이면 Secret Key와 Invoke URL이 같은 도메인의 것인지 확인하세요."
        )

    try:
        body = response.json()
    except ValueError as exc:
        raise ClovaOcrError(f"JSON이 아닌 응답: {response.text[:300]!r}") from exc

    images = body.get("images") or []
    if not images:
        raise ClovaOcrError(f"images가 비어 있습니다: {json.dumps(body, ensure_ascii=False)[:300]}")

    infer_result = images[0].get("inferResult")
    if infer_result != "SUCCESS":
        raise ClovaOcrError(
            f"inferResult={infer_result!r} message={images[0].get('message')!r}"
        )
    return body, elapsed


def _summarize_error(response: requests.Response) -> str:
    """APIGW / OCR 양쪽 오류 본문 형태를 한 줄로 정리한다."""
    try:
        body = response.json()
    except ValueError:
        return response.text[:300]

    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict):
            return f"{error.get('errorCode')} {error.get('message')}"
        if "code" in body or "message" in body:
            return f"{body.get('code')} {body.get('message')}"
    return json.dumps(body, ensure_ascii=False)[:300]


# ---------------------------------------------------------------------------
# 응답 파싱
# ---------------------------------------------------------------------------


def iter_fields(response: dict[str, Any]) -> list[dict[str, Any]]:
    """모든 이미지의 fields를 순서대로 이어 붙인다."""
    fields: list[dict[str, Any]] = []
    for image in response.get("images") or []:
        fields.extend(image.get("fields") or [])
    return fields


def _vertical_center(field: dict[str, Any]) -> float:
    vertices = ((field.get("boundingPoly") or {}).get("vertices")) or []
    ys = [float(v.get("y", 0.0)) for v in vertices]
    return sum(ys) / len(ys) if ys else 0.0


def _horizontal_start(field: dict[str, Any]) -> float:
    vertices = ((field.get("boundingPoly") or {}).get("vertices")) or []
    xs = [float(v.get("x", 0.0)) for v in vertices]
    return min(xs) if xs else 0.0


def fields_to_lines(fields: Sequence[dict[str, Any]]) -> list[str]:
    """필드 목록을 줄 단위 텍스트로 복원한다.

    General OCR은 줄의 마지막 필드에 `lineBreak: true`를 붙여준다. 그 값이 아예 없는
    응답(구버전/일부 도메인)에서는 boundingPoly의 y 중심으로 묶는 방식으로 넘어간다.
    """
    if not fields:
        return []

    if any("lineBreak" in field for field in fields):
        lines: list[str] = []
        current: list[str] = []
        for field in fields:
            text = (field.get("inferText") or "").strip()
            if text:
                current.append(text)
            if field.get("lineBreak"):
                if current:
                    lines.append(" ".join(current))
                current = []
        if current:
            lines.append(" ".join(current))
        return lines

    return _lines_by_geometry(fields)


def _lines_by_geometry(fields: Sequence[dict[str, Any]]) -> list[str]:
    heights: list[float] = []
    for field in fields:
        vertices = ((field.get("boundingPoly") or {}).get("vertices")) or []
        ys = [float(v.get("y", 0.0)) for v in vertices]
        if len(ys) >= 2:
            heights.append(max(ys) - min(ys))
    tolerance = (sum(heights) / len(heights) * 0.6) if heights else 10.0

    rows: list[list[dict[str, Any]]] = []
    for field in sorted(fields, key=_vertical_center):
        center = _vertical_center(field)
        if rows and abs(center - _vertical_center(rows[-1][-1])) <= tolerance:
            rows[-1].append(field)
        else:
            rows.append([field])

    lines: list[str] = []
    for row in rows:
        texts = [
            (field.get("inferText") or "").strip()
            for field in sorted(row, key=_horizontal_start)
        ]
        line = " ".join(text for text in texts if text)
        if line:
            lines.append(line)
    return lines


def plain_text(response: dict[str, Any]) -> str:
    return "\n".join(fields_to_lines(iter_fields(response)))


def low_confidence_fields(
    response: dict[str, Any], threshold: float = 0.8
) -> list[tuple[str, float]]:
    """신뢰도가 낮은 필드를 (텍스트, 신뢰도)로 돌려준다.

    사용자에게 짧은 확인을 요청할 후보를 고르는 데 쓴다.
    """
    result: list[tuple[str, float]] = []
    for field in iter_fields(response):
        confidence = field.get("inferConfidence")
        if isinstance(confidence, (int, float)) and confidence < threshold:
            result.append(((field.get("inferText") or "").strip(), float(confidence)))
    return sorted(result, key=lambda item: item[1])


# ---------------------------------------------------------------------------
# 마스킹
# ---------------------------------------------------------------------------

_RRN_RE = re.compile(r"(?<!\d)(\d{6})[-\s]?([1-8])\d{6}(?!\d)")
_ACCOUNT_RE = re.compile(r"(?<![\d-])(\d{2,6})([-\s]\d{2,6}){1,3}(?![\d-])")
_DIGIT_RUN_RE = re.compile(r"(?<!\d)(\d{10,})(?!\d)")
# 날짜(2019-06-24 / 2019.6.24)는 계좌번호로 오인하지 않는다
_DATE_LIKE_RE = re.compile(r"^\d{4}[-.\s/]\d{1,2}[-.\s/]\d{1,2}$")
# 국내 계좌번호는 숫자 10자리 이상이다. 그보다 짧으면 가리지 않는다.
_MIN_ACCOUNT_DIGITS = 10


def mask_pii(text: str) -> str:
    """주민등록번호·계좌번호로 보이는 숫자열을 가린다.

    로그·외부 전송·화면 캡처에 원문을 남기지 않기 위한 최소 장치다. 완전한 비식별화가
    아니므로 이 함수만 믿고 원문을 어디든 보내면 안 된다.
    """

    def mask_rrn(match: re.Match[str]) -> str:
        return f"{match.group(1)}-{match.group(2)}******"

    def mask_grouped(match: re.Match[str]) -> str:
        whole = match.group(0)
        if _DATE_LIKE_RE.match(whole):
            return whole
        if len(re.sub(r"\D", "", whole)) < _MIN_ACCOUNT_DIGITS:
            return whole
        head, tail = whole[:3], whole[-3:]
        return head + "*" * (len(whole) - 6) + tail

    def mask_run(match: re.Match[str]) -> str:
        digits = match.group(1)
        return digits[:3] + "*" * (len(digits) - 6) + digits[-3:]

    masked = _RRN_RE.sub(mask_rrn, text)
    masked = _ACCOUNT_RE.sub(mask_grouped, masked)
    return _DIGIT_RUN_RE.sub(mask_run, masked)


def mask_lines(lines: Iterable[str]) -> list[str]:
    return [mask_pii(line) for line in lines]
