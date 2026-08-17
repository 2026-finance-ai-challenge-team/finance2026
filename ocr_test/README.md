# ocr_test — 네이버 CLOVA OCR 연결 테스트

CLOVA OCR **General** API가 실제로 응답하는지, 통장사본에서 쓸 만한 텍스트가 나오는지
확인하기 위한 임시 폴더다. 본 파이프라인(`apps/web`)에 아직 연결하지 않았다.

여기서 하는 일은 **인식**까지다. 준비 상태 다섯 가지(`준비 완료`·`추가 필요`·`기한 만료`·
`정보 불일치`·`이번 업무에는 불필요`) 판정은 규칙 엔진의 몫이므로 이 폴더에 없다.

## 1. 준비

```bash
cd ocr_test
python -m venv .venv
# Windows PowerShell
.venv\Scripts\Activate.ps1
# macOS / Linux
# source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env      # PowerShell: copy .env.example .env
```

`.env`를 열어 NCP 콘솔에서 받은 두 값을 채운다.

| 키 | 값 | 콘솔 위치 |
| --- | --- | --- |
| `NCP_OCR_INVOKE_URL` | APIGW Invoke URL (`.../general`) | CLOVA OCR > 도메인 > 해당 도메인의 APIGW Invoke URL |
| `NCP_OCR_SECRET_KEY` | 도메인 Secret Key (`X-OCR-SECRET` 헤더값) | 같은 도메인의 Secret Key |

두 값은 **같은 도메인의 것**이어야 한다. 섞이면 401/403이 난다.

> Secret Key는 `.env`에만 둔다. 루트 `.gitignore`가 `.env`를 제외하므로 커밋되지 않는다.
> 코드·README·커밋 메시지에 키를 적지 않는다. 노출됐다면 콘솔에서 재발급한다.

## 2. 실행

```powershell
# 로컬 통장사본으로 테스트 (경로에 공백이 있으니 반드시 따옴표)
python run_ocr.py "E:\OneDrive\바탕 화면\뉴연뉴의 개인문서\국민은행 통장사본.jpg"

# 계좌번호를 가린 상태로 보고, 응답을 out/에 저장
python run_ocr.py "...\국민은행 통장사본.jpg" --mask --save

# 응답 JSON 원문까지 확인
python run_ocr.py "...\국민은행 통장사본.jpg" --raw
```

주요 옵션:

| 옵션 | 설명 |
| --- | --- |
| `--mask` | 계좌번호·주민번호로 보이는 숫자열을 가려서 출력·저장 |
| `--save` | 응답 JSON과 줄 단위 텍스트를 `out/`에 타임스탬프로 저장 |
| `--raw` | 응답 JSON 전체 출력 |
| `--lang ko` | 인식 언어 (기본 `ko`) |
| `--table` | `enableTableDetection` 활성화 |
| `--min-confidence 0.8` | 이 값 미만 신뢰도 필드를 따로 나열 |
| `--from-json PATH` | **API를 호출하지 않고** 저장된 응답만 다시 파싱 |

`--from-json`은 API 호출 수를 쓰지 않고 파싱·마스킹 로직만 손볼 때 쓴다.

```bash
python run_ocr.py --from-json fixtures/sample_general_response.json --mask
```

## 3. 오프라인 검증

```bash
python test_parse.py      # 또는: pytest test_parse.py
```

합성 응답(`fixtures/sample_general_response.json`)만 쓰고 네트워크를 타지 않는다.
9개 케이스가 줄 복원, 좌표 폴백, 마스킹, 필드 추출을 확인한다.

## 4. 요청·응답 구조 메모

**요청** — `multipart/form-data` 두 파트.

```
POST {NCP_OCR_INVOKE_URL}
X-OCR-SECRET: {NCP_OCR_SECRET_KEY}

message = {"version":"V2","requestId":"<uuid>","timestamp":<ms>,
           "lang":"ko","enableTableDetection":false,
           "images":[{"format":"jpg","name":"국민은행 통장사본"}]}
file    = <바이너리>
```

`images[].format`은 `jpg`·`png`·`pdf`·`tiff`만 받는다. `run_ocr.py`가 확장자를 정규화하고
(`.jpeg`→`jpg`, `.tif`→`tiff`) 지원하지 않는 확장자는 호출 전에 막는다.

**응답** — 필요한 부분만.

```
images[0].inferResult        "SUCCESS" | "FAILURE" | "ERROR"
images[0].fields[].inferText        인식된 문자열
images[0].fields[].inferConfidence  0.0 ~ 1.0
images[0].fields[].lineBreak        true면 그 줄의 마지막 필드
images[0].fields[].boundingPoly.vertices  꼭짓점 4개 (x, y)
```

`fields`는 줄 단위가 아니라 **어절 단위**로 쪼개져 온다. `clova_ocr.fields_to_lines()`가
`lineBreak`로 줄을 되붙이고, `lineBreak`가 없는 응답에서는 `boundingPoly`의 y 중심으로
묶는 방식으로 넘어간다.

## 5. 파일

| 파일 | 역할 |
| --- | --- |
| `clova_ocr.py` | API 클라이언트, 응답 파싱, PII 마스킹 |
| `bankbook.py` | 통장사본 필드 추출 — **정규식 휴리스틱(임시)** |
| `run_ocr.py` | CLI 데모 |
| `test_parse.py` | 오프라인 파싱 검증 |
| `fixtures/` | 합성 응답 샘플 |
| `out/` | 실행 결과 (gitignore) |

`bankbook.py`는 "OCR 텍스트가 쓸 만한가"를 눈으로 보려고 만든 자리 채우기다.
본선에서는 이 역할을 LLM 추출이 맡고, 결과는 사용자가 수정할 수 있어야 한다.
이 정규식 결과로 준비 상태를 결정하지 않는다.

## 6. 개인정보 주의

- **통장사본 원본과 `out/` 결과물을 커밋하지 않는다.** 이 폴더의 이미지 파일과 `out/`은
  `.gitignore`로 막아 뒀지만, `git add -f`로 우회하지 않는다.
- 저장소에 들어가는 샘플은 **합성 데이터만**(`fixtures/`의 이름·계좌번호는 가짜다).
- 실제 서비스 코드로 옮길 때는 `--mask` 없이 텍스트를 로그로 남기지 않는다.
  로그에 원문·주민번호·계좌번호를 남기지 않는 것이 `AGENTS.md`의 요구사항이다.
- 테스트가 끝나면 `out/`을 지운다.

## 7. 다음 단계 (아직 안 한 것)

- PDF 다중 페이지 처리: 내장 텍스트가 있는 페이지는 텍스트 추출로 처리하고, 없는 페이지만 OCR
- 같은 파일 결과 세션 내 재사용(중복 호출 방지)
- 문서 종류 분류 → 필드 추출을 LLM으로 이관
- 규칙 엔진 연결 및 다섯 상태 판정
