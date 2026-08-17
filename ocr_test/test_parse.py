"""응답 파싱·마스킹 오프라인 검증.

API를 호출하지 않는다. 합성 응답(fixtures/sample_general_response.json)만 쓴다.

    python test_parse.py      # 또는  pytest test_parse.py
"""

from __future__ import annotations

import json
from pathlib import Path

import clova_ocr
from bankbook import extract_bankbook_fields

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "sample_general_response.json"


def load_fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_build_message_shape() -> None:
    message = clova_ocr.build_message(image_name="통장사본", image_format="jpg")
    assert message["version"] == "V2"
    assert message["images"] == [{"format": "jpg", "name": "통장사본"}]
    assert isinstance(message["timestamp"], int)
    assert len(message["requestId"]) == 36


def test_image_format_normalization() -> None:
    assert clova_ocr.image_format_of(Path("a.JPEG")) == "jpg"
    assert clova_ocr.image_format_of(Path("a.tif")) == "tiff"
    assert clova_ocr.image_format_of(Path("a.pdf")) == "pdf"
    try:
        clova_ocr.image_format_of(Path("a.heic"))
    except clova_ocr.ClovaOcrError:
        pass
    else:  # pragma: no cover
        raise AssertionError("heic는 거부해야 합니다")


def test_lines_from_line_break_flag() -> None:
    lines = clova_ocr.fields_to_lines(clova_ocr.iter_fields(load_fixture()))
    assert lines[0] == "KB나라사랑우대통장"
    assert lines[1] == "홍길동 님"
    assert lines[2] == "계좌번호 123456-78-901234"
    assert lines[-1] == "SWIFT CODE : CZNBKRSE KB 국민은행"
    assert len(lines) == 8


def test_lines_fallback_by_geometry() -> None:
    """lineBreak가 없는 응답에서도 좌표로 같은 줄 구성을 복원해야 한다."""
    fields = clova_ocr.iter_fields(load_fixture())
    stripped = [{k: v for k, v in field.items() if k != "lineBreak"} for field in fields]
    assert clova_ocr.fields_to_lines(stripped) == clova_ocr.fields_to_lines(fields)


def test_low_confidence_fields_sorted() -> None:
    low = clova_ocr.low_confidence_fields(load_fixture(), threshold=0.8)
    assert [text for text, _ in low] == ["가양역", "결산일 2,5,8,11월 제2금요일"]
    assert low[0][1] < low[1][1]


def test_mask_pii() -> None:
    assert clova_ocr.mask_pii("계좌번호 123456-78-901234") == "계좌번호 123**********234"
    assert clova_ocr.mask_pii("900101-1234567") == "900101-1******"
    # 하이픈이 없어도 13자리 주민번호 형태는 같은 규칙으로 잡는다
    assert clova_ocr.mask_pii("9001011234567") == "900101-1******"
    # 주민번호 형태가 아닌 긴 숫자열은 앞뒤 3자리만 남긴다
    assert clova_ocr.mask_pii("99887766554433") == "998********433"
    # 날짜와 짧은 숫자는 건드리지 않는다
    assert clova_ocr.mask_pii("신규가입일 2019.06.24") == "신규가입일 2019.06.24"
    assert clova_ocr.mask_pii("신규가입일 2019-06-24") == "신규가입일 2019-06-24"
    assert clova_ocr.mask_pii("제2금요일 2,5,8,11월") == "제2금요일 2,5,8,11월"
    # 계좌번호 판정 경계: 숫자 10자리부터 가린다
    assert clova_ocr.mask_pii("112-233-445") == "112-233-445"
    assert clova_ocr.mask_pii("112-233-4455") == "112******455"


def test_extract_bankbook_fields() -> None:
    lines = clova_ocr.fields_to_lines(clova_ocr.iter_fields(load_fixture()))
    fields = extract_bankbook_fields(lines)
    assert fields.bank == "KB국민은행"
    assert fields.product_name == "KB나라사랑우대통장"
    assert fields.holder == "홍길동"
    assert fields.account_number == "123456-78-901234"
    assert fields.opened_at == "2019-06-24"
    assert fields.branch == "가양역"
    assert fields.swift_code == "CZNBKRSE"
    assert fields.missing() == []


def test_extract_reports_missing_fields() -> None:
    fields = extract_bankbook_fields(["국민은행", "발급 확인용"])
    assert fields.missing() == ["예금주", "계좌번호"]
    assert any("예금주" in note for note in fields.notes)


class _StubResponse:
    status_code = 200

    def __init__(self, body: dict) -> None:
        self._body = body
        self.text = json.dumps(body)

    def json(self) -> dict:
        return self._body


class _StubSession:
    """requests.Session 대신 넣어 실제 전송 내용을 들여다본다."""

    def __init__(self, body: dict) -> None:
        self.body = body
        self.captured: dict = {}

    def post(self, url, **kwargs):
        self.captured = {"url": url, **kwargs}
        return _StubResponse(self.body)


def test_call_general_ocr_request_shape() -> None:
    """헤더·message·file 파트가 API가 요구하는 형태로 나가는지 확인한다."""
    import tempfile

    session = _StubSession(load_fixture())
    config = clova_ocr.OcrConfig(
        invoke_url="https://example.apigw.ntruss.com/custom/v1/0/abc/general",
        secret_key="dummy-secret",
    )

    with tempfile.TemporaryDirectory() as tmp:
        image = Path(tmp) / "국민은행 통장사본.jpg"
        image.write_bytes(b"\xff\xd8\xff\xe0fake-jpeg-bytes")
        response, elapsed = clova_ocr.call_general_ocr(image, config, session=session)

    sent = session.captured
    assert sent["url"] == config.invoke_url
    assert sent["headers"] == {"X-OCR-SECRET": "dummy-secret"}
    assert sent["timeout"] == config.timeout

    message = json.loads(sent["data"]["message"])
    assert message["version"] == "V2"
    assert message["lang"] == "ko"
    assert message["enableTableDetection"] is False
    assert message["images"] == [{"format": "jpg", "name": "국민은행 통장사본"}]

    filename, payload, mime = sent["files"]["file"]
    assert filename == "국민은행 통장사본.jpg"
    assert payload == b"\xff\xd8\xff\xe0fake-jpeg-bytes"
    assert mime == "image/jpeg"

    assert response["images"][0]["inferResult"] == "SUCCESS"
    assert elapsed >= 0


def test_call_general_ocr_rejects_failed_infer() -> None:
    body = {"images": [{"inferResult": "FAILURE", "message": "ERROR_IMAGE_FORMAT"}]}
    session = _StubSession(body)
    config = clova_ocr.OcrConfig(invoke_url="https://example.apigw.ntruss.com/x", secret_key="s")

    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        image = Path(tmp) / "a.png"
        image.write_bytes(b"x")
        try:
            clova_ocr.call_general_ocr(image, config, session=session)
        except clova_ocr.ClovaOcrError as exc:
            assert "FAILURE" in str(exc)
        else:  # pragma: no cover
            raise AssertionError("inferResult 실패는 예외로 올려야 합니다")


def test_config_requires_env() -> None:
    import os

    saved = {key: os.environ.pop(key, None) for key in (clova_ocr.ENV_INVOKE_URL, clova_ocr.ENV_SECRET_KEY)}
    try:
        clova_ocr.OcrConfig.from_env()
    except clova_ocr.ClovaOcrError as exc:
        assert clova_ocr.ENV_INVOKE_URL in str(exc)
        assert clova_ocr.ENV_SECRET_KEY in str(exc)
    else:  # pragma: no cover
        raise AssertionError("환경변수가 없으면 예외를 올려야 합니다")
    finally:
        for key, value in saved.items():
            if value is not None:
                os.environ[key] = value


def test_load_dotenv_parsing(tmp_path_factory=None) -> None:
    import os
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        env_file = Path(tmp) / ".env"
        env_file.write_text(
            "# 주석\n"
            "export TEST_OCR_A=value-a\n"
            'TEST_OCR_B="value b"\n'
            "잘못된줄\n",
            encoding="utf-8",
        )
        loaded = clova_ocr.load_dotenv(env_file)
        assert loaded == {"TEST_OCR_A": "value-a", "TEST_OCR_B": "value b"}
        assert os.environ["TEST_OCR_B"] == "value b"
        del os.environ["TEST_OCR_A"], os.environ["TEST_OCR_B"]

    assert clova_ocr.load_dotenv(Path(tmp) / "없는파일") == {}


def main() -> int:
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    failures = 0
    for test in tests:
        try:
            test()
        except AssertionError as exc:
            failures += 1
            print(f"FAIL {test.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"ERROR {test.__name__}: {type(exc).__name__}: {exc}")
        else:
            print(f"ok   {test.__name__}")
    print(f"\n{len(tests) - failures}/{len(tests)} 통과")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
