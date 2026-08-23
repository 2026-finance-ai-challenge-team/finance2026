# 파이프라인 계약

# 0. PoC Input

CLI가 읽는 `input.json`의 최상위 구조는 다음과 같다.

```json
{
  "application_context": {
    "corporation_name": "주식회사 하나테크",
    "business_registration_number": "1234567890",
    "representative_name": "김하나",
    "application_date": "2026-08-01"
  },
  "files": [
    {
      "file_id": "file_001",
      "pages": [...]
    }
  ]
}

# 1. OCR 입력

OCR 입력은 상위(upstream) OCR 서비스에서 생성된 데이터를 나타낸다.

예:

```json
{
  "file_id": "file_001",
  "pages": [
    {
      "page": 1,
      "blocks": [
        {
          "block_id": "b1",
          "text": "사업자등록증명",
          "bbox": [],
          "confidence": 0.99
        }
      ]
    }
  ]
}
```

OCR 텍스트는 원본 정보를 손실시키는 방식으로 수정해서는 안 된다.

---

## 1.1 NAVER CLOVA General OCR V2 Adapter

외부 CLOVA 응답은 canonical OCR 계약이 아니므로 `PocInput`으로 직접 검증하지
않는다. `hana_poc.ocr_adapters.convert_clova_v2_response()`가 한 물리 파일의
CLOVA 응답과 caller-provided `source_file_id`를 받아 `OcrFile`로 변환한다.

```text
CLOVA                                      Canonical OCR

images[]                                   OcrFile.pages[]
convertedImageInfo.pageIndex + 1           OcrPage.page
fields[]                                   OcrPage.blocks[]
inferText                                  OcrBlock.text
inferConfidence                            OcrBlock.confidence
boundingPoly.vertices                      OcrBlock.bbox
uid + pageIndex + field index              OcrBlock.block_id
```

페이지 번호는 CLOVA의 0-based `pageIndex`에 1을 더해 canonical 1-based 번호로
변환한다. 여러 `images[]`는 `pageIndex` 순으로 정렬하며 중복 page index는
입력 오류로 거부한다.

`bbox`는 CLOVA 꼭짓점 네 개를 provider가 제공한 순서대로 다음과 같이 평탄화한다.

```text
[x1, y1, x2, y2, x3, y3, x4, y4]
```

기존 synthetic fixture의 `bbox: []`도 계속 유효하므로 canonical schema 변경은
필요하지 않다.

`block_id` 형식은 다음과 같다. index는 CLOVA 응답 안에서의 0-based index다.

```text
clova:{image_uid}:p{page_index:04d}:f{field_index:04d}
```

ID에는 OCR text, 현재 시각, random UUID를 사용하지 않는다. CLOVA `uid`는 필수
non-blank 값이며 누락 시 fallback identity를 만들지 않고 입력 오류로 거부한다.

다음 provider metadata는 입력 모델이 허용하지만 canonical 출력에는 포함하지
않는다.

| CLOVA metadata | 처리 |
|---|---|
| `requestId`, `timestamp`, `version` | 응답 검증에만 사용 |
| `inferResult` | `SUCCESS` 검증에 사용 |
| `lineBreak`, `valueType`, `type` | 현재 downstream이 사용하지 않아 제외 |
| `validationResult`, image `message` | canonical 계약에 필요하지 않아 제외 |
| image `width`, `height` | 좌표를 변환하지 않으므로 출력에서 제외 |
| image `name` | stable physical file identity가 아니므로 제외 |

`inferResult != SUCCESS`, 잘못된 confidence, malformed field/vertices는 업무상
`UNKNOWN` 또는 `UNSATISFIED`로 바꾸지 않고 `ClovaOcrConversionError`로
거부한다.

CLOVA 응답에는 `application_context`와 안정적인 physical `file_id`가 없다.
호출자는 변환된 `OcrFile`을 별도 `ApplicationContext`와 결합해 `PocInput`을
만들어야 한다. 기존 normalized `input.json`과 CLI 계약은 변경하지 않는다.

---

# 2. DocumentUnit

하나의 논리적 문서를 나타낸다.

필드:

```text
document_id
source_file_id
page_start
page_end
blocks
```

하나의 원본 PDF에서 여러 개의 `DocumentUnit` 객체가 생성될 수 있다.

---

# 3. ClassifiedDocument

필드:

```text
document_id

document_type

classification_status:
- CONFIDENT
- AMBIGUOUS
- UNKNOWN

classification_method:
- RULE
- LLM
- USER

confidence

evidence_block_ids

candidate_document_types

blocks
```

`candidate_document_types`는 최종 `document_type = UNKNOWN` 분류 결과에만
선택적으로 포함되는 허용 enum 목록이다. 이는 확정 분류가 아니라 가능한
문서 유형 후보이며, `UNKNOWN` 자체를 후보로 포함해서는 안 된다. 후보가
없을 수도 있다.

---

# 4. ExtractedField

모든 필드는 다음과 같은 개념적 구조를 사용해야 한다.

```json
{
  "name": "corporation_name",
  "value": "주식회사 하나테크",
  "normalized_value": "주식회사하나테크",
  "status": "KNOWN",
  "confidence": 0.98,
  "extraction_method": "RULE",
  "evidence_block_ids": ["b3"]
}
```

`status`:

```text
KNOWN
UNKNOWN
```

알 수 없는 값을 빈 문자열(empty string)로 표현해서는 안 된다.

값은 `null`로 설정하고 상태는 `UNKNOWN`을 사용한다.

---

# 5. StructuredDocument

필드:

```text
document_id
document_type
classification
fields
issue_date
source_file_id
page_range
```

---

# 6. ConsistencyResult

예:

```json
{
  "check_id": "COMPANY_NAME_MATCH",
  "status": "SATISFIED",
  "participants": [
    {
      "document_id": "doc_001",
      "field": "corporation_name",
      "value": "주식회사 하나테크"
    },
    {
      "document_id": "doc_002",
      "field": "corporation_name",
      "value": "주식회사 하나테크"
    }
  ],
  "reason_code": "VALUES_MATCH"
}
```

`status`:

```text
SATISFIED
UNSATISFIED
UNKNOWN
```

---

# 7. RequirementResult

```json
{
  "requirement_id": "CORPORATE_REGISTRY_REQUIRED",
  "status": "SATISFIED",
  "blocking": true,
  "reason_code": "REQUIRED_DOCUMENT_PRESENT",
  "evidence": ["doc_002"]
}
```

---

# 8. Assessment

```json
{
  "overall_status": "READY",
  "requirements": [],
  "consistency_checks": []
}
```

`overall_status`:

```text
READY
ACTION_REQUIRED
REVIEW_REQUIRED
```
