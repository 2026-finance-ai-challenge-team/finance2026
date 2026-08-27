# 규칙 엔진

## 목표

구조화된 근거(evidence)를 선언적으로 정의된 비즈니스 요구사항과 비교하여 평가한다.

규칙 엔진은 완전히 결정론적으로 동작해야 한다.

---

# 금지된 의존성

규칙 엔진은 다음 항목을 import하거나 호출해서는 안 된다.

- LLM 클라이언트
- 프롬프트 빌더
- 설명(explanation) 모듈

---

# 규칙 소스

규칙은 Python 구현 코드 외부에 저장되어야 한다.

PoC의 주요 규칙 파일:

```text
rules/HANA_BANK/CORPORATE_NON_FACE_TO_FACE_ACCOUNT_OPENING/poc-v1.yaml
```

---

# 결과 값

각 요구사항은 반드시 다음 세 가지 상태 중 정확히 하나를 반환해야 한다.

```text
SATISFIED

UNSATISFIED

UNKNOWN
```

---

# 핵심 요구사항

## BUSINESS_REGISTRATION_REQUIRED

허용 문서:

```text
BUSINESS_REGISTRATION_CERTIFICATE
```

---

## CORPORATE_REGISTRY_REQUIRED

허용 문서:

```text
CORPORATE_REGISTRY
```

---

## SHAREHOLDER_INFORMATION_REQUIRED

다음 문서 중 하나를 허용한다.

```text
SHAREHOLDER_REGISTER

또는

STOCK_CHANGE_STATEMENT
```

---

## SALES_EVIDENCE_REQUIRED

다음 문서 중 하나를 허용한다.

```text
VAT_TAX_BASE_CERTIFICATE

또는

STANDARD_FINANCIAL_STATEMENT_CERTIFICATE
```

---

# 모호한 문서에 대한 규칙

`document_presence.any_of`와 확정 문서의 `document_type`이 교집합을 가지면
요구사항은 `SATISFIED`가 된다.

확정 문서가 없고, `UNKNOWN` 문서의
`classification.candidate_document_types`와 `any_of`가 교집합을 가지면
요구사항은 다음과 같다.

```text
UNKNOWN
DOCUMENT_TYPE_UNRESOLVED
```

관련 후보가 없는 경우에만 `UNSATISFIED / REQUIRED_DOCUMENT_MISSING`을
반환한다. 후보 평가는 requirement ID가 아니라 YAML의 `any_of`만 사용한다.

---

# 문서 유효기간

최신성은 전역 기본값이 아니라 해당 `document_presence` requirement에
선언한다.

```yaml
- id: EXAMPLE_REQUIREMENT
  blocking: true
  document_presence:
    any_of:
      - CORPORATE_REGISTRY
  freshness:
    max_age_days: 90
```

다음 조건을 사용한다.

```text
application_date - issue_date <= 설정된 최대 허용 기간
```

하나 이상의 accepted document가 기간 이내면 `SATISFIED`가 된다.

모든 accepted document의 `issue_date`가 `KNOWN`이고 허용 기간을 초과한 경우:

```text
UNSATISFIED
DOCUMENT_EXPIRED
```

기간 이내 문서가 없고 `issue_date` 또는 `application_date`가 UNKNOWN인 경우:

```text
UNKNOWN
FIELD_UNKNOWN
```

관련 unresolved candidate가 있으면 `DOCUMENT_TYPE_UNRESOLVED`가 된다.
최신성은 반드시 `application_context.application_date`를 기준으로 하며,
현재 시스템 시간을 사용하지 않는다.

---

# 일관성 검사 의존성

요구사항은 일관성 검사(consistency check) 결과에 의존할 수 있다.

예:

```text
CORPORATION_IDENTITY_CONSISTENT
```

는 다음 조건을 요구한다.

```text
COMPANY_NAME_MATCH == SATISFIED
```

일관성 검사 결과가:

```text
UNSATISFIED
```

인 경우 요구사항 결과도:

```text
UNSATISFIED
```

가 된다.

일관성 검사 결과가:

```text
UNKNOWN
```

인 경우 요구사항 결과도:

```text
UNKNOWN
```

이 된다.

---

# 근거(Evidence)

각 규칙 평가 결과는 반드시 다음 정보를 포함해야 한다.

```text
requirement_id
status
blocking
reason_code
evidence
```

---

# Reason Code

다음과 같은 enum 사용을 우선한다.

```text
REQUIRED_DOCUMENT_PRESENT

REQUIRED_DOCUMENT_MISSING

DOCUMENT_TYPE_UNRESOLVED

FIELD_UNKNOWN

DOCUMENT_EXPIRED

KNOWN_VALUES_CONFLICT

CONSISTENCY_CONFIRMED
```

---

# 승인 기준

- 동일한 입력은 항상 동일한 결과를 생성해야 한다.
- LLM에 대한 의존성이 존재해서는 안 된다.
- evaluator 로직을 수정하지 않고도 규칙을 변경할 수 있어야 한다.
- `UNKNOWN` 상태가 올바르게 전파되어야 한다.
- 모든 평가 결과에는 근거(evidence)가 포함되어야 한다.
- 필수 근거가 누락된 경우 결정론적인 reason code가 생성되어야 한다.
