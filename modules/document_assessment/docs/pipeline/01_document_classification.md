# 문서 분류

## 목표

OCR 페이지를 논리적인 문서 단위로 변환하고, 각 문서 단위에 허용된 문서 유형 중 하나를 할당한다.

---

## 입력

정규화된 OCR 파일 및 페이지.

---

## 출력

```text
ClassifiedDocument[]
```

---

# 처리 전략

문서 분류는 반드시 규칙 기반(rule-first) 방식을 우선해야 한다.

우선순위:

1. 결정론적 키워드 / 발급기관 / 문서 제목 규칙
2. LLM fallback
3. `UNKNOWN`

LLM fallback은 반드시 인터페이스 뒤에 격리되어야 한다.

이 PoC에서는 실제 운영 환경의 LLM 호출을 요구하지 않는다.

mock 구현이 가능해야 한다.

---

# 허용되는 문서 유형

```text
BUSINESS_REGISTRATION_CERTIFICATE

CORPORATE_REGISTRY

SHAREHOLDER_REGISTER

STOCK_CHANGE_STATEMENT

VAT_TAX_BASE_CERTIFICATE

STANDARD_FINANCIAL_STATEMENT_CERTIFICATE

UNKNOWN
```

---

# 규칙 기반 분류 예시

```text
"사업자등록증명"

→ BUSINESS_REGISTRATION_CERTIFICATE

"등기사항전부증명서"

→ CORPORATE_REGISTRY

"주주명부"

→ SHAREHOLDER_REGISTER

"주식등변동상황명세서"

→ STOCK_CHANGE_STATEMENT

"부가가치세과세표준증명"

→ VAT_TAX_BASE_CERTIFICATE

"표준재무제표증명"

→ STANDARD_FINANCIAL_STATEMENT_CERTIFICATE
```

---

# 다중 문서 파일

하나의 물리적 PDF 파일에 여러 개의 논리적 문서가 포함될 수 있다.

예:

```text
1~2페이지
사업자등록 관련 문서

3~4페이지
법인 등기사항증명서

5페이지
주주명부
```

분류기는 각각을 별도의 `DocumentUnit` 객체로 반환해야 한다.

---

# 모호성

결정론적 분류에 실패하면 fallback이 사용할 수 있는 후보를 만들 수 있다.
후보는 확정 문서 유형이 아니며, `candidate_document_types`에 허용된
`DocumentType`만 기록한다. `UNKNOWN`은 후보 유형으로 사용할 수 없다.

fallback 판단이 완료되지 않았거나 문서 유형을 확정할 수 없는 경우:

```text
document_type = UNKNOWN
classification_status = UNKNOWN
```

후보가 없을 수도 있다. `CONFIDENT` 분류에는 후보 정보가 필요하지 않다.

LLM adapter는 허용된 enum 중 하나를 확정 결과로 반환하거나, 확정할 수
없을 때 후보 유형 목록을 반환할 수 있다. 실제 LLM 호출은 이 PoC의
요구사항이 아니다.

임의로 추측해서는 안 된다.

---

# 근거(Evidence)

모든 분류 결과는 해당 판단을 뒷받침하는 block ID를 보존해야 한다.

---

# 승인 기준

- 알려진 문서 제목은 결정론적으로 분류되어야 한다.
- 분류 결과에는 허용된 enum만 사용되어야 한다.
- 여러 문서가 포함된 PDF에서 여러 개의 문서 객체를 생성할 수 있어야 한다.
- 모호한 문서에 임의의 문서 유형을 할당해서는 안 된다.
- `UNKNOWN` 상태를 명시적으로 표현할 수 있어야 한다.
- 규칙 기반 분류는 LLM 없이도 동작해야 한다.
- 근거 block ID가 보존되어야 한다.
