# doc_classify — 문서 분류 모듈

담당: 연우 · 설계 근거: [`docs/DOC_CLASSIFY.md`](../../docs/DOC_CLASSIFY.md)

사용자가 올린 파일이 **무슨 문서인지** 결정해 다음 단계로 넘긴다.
다섯 상태 판정(`준비 완료` 등)은 하지 않는다. 규칙 엔진의 몫이다.

## 실행

저장소 루트에서 실행한다.

```bash
# 자체 검증 — 합성 데이터만 쓰고 API를 호출하지 않는다
python modules/doc_classify/test_doc_classify.py

# 분류 실행 (폴더를 주면 지원 확장자를 모두 처리)
python -m modules.doc_classify.cli <파일_또는_폴더>

# API 호출 없이 (텍스트 레이어 있는 PDF만 처리됨)
python -m modules.doc_classify.cli <경로> --no-ocr

# 결과 JSON 저장
python -m modules.doc_classify.cli <경로> --json out.json
```

`.env`에 `NCP_OCR_INVOKE_URL`, `NCP_OCR_SECRET_KEY`가 있어야 OCR 경로가 동작한다.
발급 방법은 루트 `README.md`의 **API 키 발급 방법** 토글에 있다.

## 구성

| 파일 | 단계 | 하는 일 |
|---|---|---|
| `extract.py` | 0~1 | magic bytes로 형식 판별 → PDF는 내장 텍스트 우선, 텍스트 없는 페이지만 OCR |
| `classify.py` | 2~3, 5 | 신호 수집 → 시그니처 대조 → 업무 관련성 판정 |
| `cli.py` | — | 실행 진입점 |
| `signatures/*.json` | — | 문서 서식 시그니처. **찬형 DB 연동 전 임시값** |
| `tasks/*.json` | — | 업무별 필요 서류. **임시값** |

공개 API는 `classify_files(paths, task_id)` 하나다.

## 지금 상태에서 믿어도 되는 것과 아닌 것

**믿어도 되는 것**

- 형식 판별과 페이지별 텍스트 확보 (실제 문서 9건으로 확인)
- 헷갈리는 쌍의 분리 — 등본/초본, 종합소득세/개인지방소득세/접수증
- 분류 실패를 `이번 업무에는 불필요`로 넘기지 않는 것

**믿으면 안 되는 것**

- `signatures/`와 `tasks/`의 내용. 전부 `"verified": false`이고 공식 출처가 없다.
  **이 값으로 사용자에게 준비 완료를 말하면 안 된다.** 찬형 조사 결과로 교체한다.
- 사문서(재직증명서 등) 분류. 서식이 제각각이라 현재 패턴으로는 잘 안 잡힌다.

## 아직 안 만든 것

- **QR·바코드 판독** — 설계상 1순위 신호인데 빠져 있다. 정부24 발급물의 QR을 읽으면
  분류가 확정되고 OCR도 필요 없다. 의존성(`opencv-python` 또는 `pyzbar`)이 필요해서
  실제 표본에 QR이 있는지 확인한 뒤 넣는다.
- **AI 분류 (4단계)** — 1~3순위 신호로 얼마나 걷히는지 보고 결정한다.
- **레이아웃 지문** — 같은 이유로 보류.

## 알려진 한계

- `TITLE_HEAD_CHARS = 500` — 제목을 문서 상단 500자에서만 찾는다. OCR이 줄 순서를
  크게 흐트러뜨리면 제목을 놓칠 수 있다. 좌표 기반 상단 영역이 정확하지만 bbox가 필요하다.
- `negative_anchors`는 문서 전체에서 찾는다. 안내문에 다른 서류 이름이 있으면
  정상 문서가 탈락할 수 있다. 탈락은 `판단 불가`로 이어지므로 오분류보다는 안전한 실패다.
- `MIN_CHARS_PER_PAGE = 30` — 이 값 미만인 페이지를 OCR로 넘긴다. 실제 표본으로 조정해야 한다.
