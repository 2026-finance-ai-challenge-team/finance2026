# 필드 추출

## 목표

`ClassifiedDocument` 객체를 타입이 명시된 `StructuredDocument` 객체로 변환한다.

---

# 일반 규칙

구조화된 정부 발급 문서에 대해서는 결정론적 추출 방식을 우선한다.

레이아웃이나 문구를 충분히 예측하기 어려운 경우에만 LLM 기반 추출을 사용한다.

추출된 모든 값은 반드시 근거(evidence)를 포함해야 한다.

알 수 없는 값은 반드시 `UNKNOWN` 상태로 유지해야 한다.

---

# 공통 필드

해당되는 경우 다음 필드를 사용한다.

```text
corporation_name

business_registration_number

corporate_registration_number

representative_name

issue_date

issuer
```

---

# 문서별 필드

## BUSINESS_REGISTRATION_CERTIFICATE

필수 후보 필드:

```text
corporation_name
business_registration_number
representative_name
issue_date
```

---

## CORPORATE_REGISTRY

후보 필드:

```text
corporation_name
corporate_registration_number
representative_name
head_office_address
issue_date
```

---

## SHAREHOLDER_REGISTER

후보 필드:

```text
corporation_name
issue_date

shareholders:
- name
- ownership_ratio
```

---

## STOCK_CHANGE_STATEMENT

후보 필드:

```text
corporation_name
shareholders
issue_date
```

---

## VAT_TAX_BASE_CERTIFICATE

후보 필드:

```text
corporation_name
business_registration_number
sales_amount
issue_date
```

---

## STANDARD_FINANCIAL_STATEMENT_CERTIFICATE

후보 필드:

```text
corporation_name
business_registration_number
sales_amount
issue_date
```

---

# 정규화

정규화(normalization)는 반드시 결정론적으로 수행되어야 한다.

예:

사업자등록번호:

```text
123-45-67890
→ 1234567890
```

안전한 경우 공백 차이를 제거할 수 있다.

법인명의 경우 다음과 같이 명백하게 동등한 표현을 정규화할 수 있다.

```text
㈜
주식회사
```

두 법인명이 동일하다고 암묵적으로 판정하기 위해 퍼지 문자열 유사도(fuzzy string similarity)를 사용해서는 안 된다.

---

# 알 수 없는 필드

신뢰할 수 있는 수준으로 필드를 추출할 수 없는 경우:

```json
{
  "value": null,
  "status": "UNKNOWN"
}
```

값을 임의로 생성해서는 안 된다.

---

# LLM 추출 경계

LLM 기반 추출은 반드시 다음 조건을 충족해야 한다.

- 마스킹된 텍스트를 입력받는다.
- 지정된 schema에 해당하는 결과만 반환한다.
- 근거가 되는 block을 식별한다.
- 근거가 충분하지 않은 경우 `UNKNOWN`을 반환한다.

---

# 승인 기준

- 알려진 fixture에서 결정론적으로 추출 가능한 필드가 정상적으로 추출되어야 한다.
- 정규화는 결정론적이어야 한다.
- 추출 과정 이후에도 근거(evidence)가 보존되어야 한다.
- 누락된 값은 `UNKNOWN`이 되어야 한다.
- 잘못된 형식의 값이 입력되어도 파이프라인이 중단되어서는 안 된다.
- LLM fallback을 mock 구현으로 대체할 수 있어야 한다.