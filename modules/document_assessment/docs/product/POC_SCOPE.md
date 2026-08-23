# PoC 범위

## 목적

이 PoC는 비대면 법인 업무에서 구조화된 OCR 결과를 입력받아
문서 분류, 필드 추출, 문서 간 검증, 규칙 평가 및 최종 심사 상태를
생성하는 post-OCR 문서 심사 파이프라인을 검증한다.

이 저장소는 실제 하나은행의 운영 시스템을 구현하거나 복제하는 것을
목적으로 하지 않는다.

---

## 지원 워크플로

PoC는 하나 이상의 업무별 rule set을 사용할 수 있다.

각 rule set은 다음 식별자를 가진다.

```text
bank
workflow
version
```

초기 PoC에서 사용하는 rule set은 다음과 같다.

```text
bank: HANA_BANK
workflow: CORPORATE_NON_FACE_TO_FACE_ACCOUNT_OPENING
version: poc-v1
```

구체적인 업무별 문서 요구사항, 대체 가능 문서, 일관성 검사,
blocking 여부 및 문서 최신성 기준은 `rules/` 아래의 rule set에서 정의한다.

업무 정책의 source of truth는 해당 rule set이다.

---

## 시작 지점

OCR은 이미 성공적으로 완료된 상태를 전제로 한다.

OCR 구현은 이 저장소의 범위에 포함되지 않는다.

입력 fixture는 정규화된 OCR 출력을 나타낸다.

---

## 비즈니스 규칙 범위

이 PoC에서 사용하는 업무 규칙은 공개적으로 확인 가능한 업무 절차
정보를 바탕으로 PoC 목적에 맞게 단순화한 표현이다.

이 규칙들을 하나은행의 전체 내부 적격성 심사, 컴플라이언스 규칙,
실제 계좌 개설 승인 정책 또는 운영 규정으로 해석해서는 안 된다.

구체적인 업무 규칙은 Python 코드에 하드코딩하지 않고
`rules/` 아래의 선언적 rule set으로 관리한다.

동일한 workflow에 여러 정책 버전이 존재할 수 있다.

예:

```text
HANA_BANK
└── CORPORATE_NON_FACE_TO_FACE_ACCOUNT_OPENING
    ├── poc-v1
    └── poc-v2
```

서로 다른 workflow는 별도의 rule set을 사용한다.

---

## 지원 문서 유형

시스템이 인식할 수 있는 초기 문서 유형 enum은 다음과 같다.

```text
BUSINESS_REGISTRATION_CERTIFICATE

CORPORATE_REGISTRY

SHAREHOLDER_REGISTER

STOCK_CHANGE_STATEMENT

VAT_TAX_BASE_CERTIFICATE

STANDARD_FINANCIAL_STATEMENT_CERTIFICATE

UNKNOWN
```

이 목록은 특정 workflow의 필수 제출 문서 목록을 의미하지 않는다.

어떤 문서가 특정 workflow에서 필수인지, 어떤 문서를 대체 문서로
인정하는지는 해당 workflow의 rule set에서 정의한다.

명세에서 요구하지 않는 한 새로운 문서 유형을 추가하지 않는다.

새로운 workflow가 기존 enum에 없는 문서 유형을 필요로 하는 경우,
해당 문서 유형에 대한 schema, classification, extraction 및 test
영향을 검토한 후 명시적으로 추가한다.

---

## 신청 컨텍스트

파이프라인은 OCR 외부에서 이미 수집된 구조화된 정보를 입력받을 수 있다.

예:

```json
{
  "corporation_name": "...",
  "business_registration_number": "...",
  "representative_name": "...",
  "application_date": "YYYY-MM-DD"
}
```

PoC에 제공되지 않은 값은 임의로 생성하거나 추정해서는 안 된다.

---

## 제외 범위

다음 항목은 이 PoC의 범위에 포함되지 않는다.

- OCR 구현
- 이미지 전처리
- 파일 업로드 UI
- 프론트엔드
- 실제 본인 확인
- 인증 시스템
- 운영용 데이터베이스
- 실제 하나은행 API 연동
- 실제 은행 업무상의 승인
- 실제 고객 데이터
- 명시적으로 요청되지 않은 실제 운영 LLM 호출

---

## 안전성

fixture에는 합성된 가상 기업과 가상 인물 정보만 사용한다.

실제 고객 정보를 사용해서는 안 된다.

실제 고객 개인정보(PII)를 fixture, test 또는 예제 데이터에 포함해서는 안 된다.
