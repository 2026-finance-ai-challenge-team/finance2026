# 문서 간 일관성 검증

## 목표

추출된 사실이 여러 문서 및 신청 컨텍스트(application context) 간에 서로 일치하는지 판정한다.

검증은 결정론적으로 수행되어야 한다.

LLM을 사용해서는 안 된다.

---

# 필수 초기 검사

```text
COMPANY_NAME_MATCH

BUSINESS_REGISTRATION_NUMBER_MATCH

REPRESENTATIVE_NAME_MATCH
```

---

# 3값 논리

모든 검사는 반드시 다음 세 가지 상태 중 정확히 하나를 반환한다.

```text
SATISFIED

UNSATISFIED

UNKNOWN
```

---

## SATISFIED

비교에 필요한 모든 값이 `KNOWN` 상태이며, 허용된 결정론적 정규화를 적용한 후 서로 동등한 경우이다.

---

## UNSATISFIED

비교에 필요한 값 중 최소 두 개가 `KNOWN` 상태이고 서로 충돌하는 경우이다.

예:

```text
사업자등록증:
representative = 김하나

법인 등기사항증명서:
representative = 박하나
```

결과:

```text
UNSATISFIED
```

`reason_code`:

```text
KNOWN_VALUES_CONFLICT
```

---

## UNKNOWN

시스템이 필요한 필드를 신뢰할 수 있는 수준으로 비교할 수 없는 경우이다.

예:

```text
사업자등록증:
representative = 김하나

법인 등기사항증명서:
representative = UNKNOWN
```

결과:

```text
UNKNOWN
```

이를 `UNSATISFIED`로 변환해서는 안 된다.

---

# 신청 컨텍스트 비교

신청 컨텍스트에 다음 값이 포함되어 있는 경우:

```text
corporation_name
business_registration_number
representative_name
```

동일한 3값 논리를 사용하여 해당 값과 문서에서 추출된 값을 비교한다.

---

# 퍼지 매칭 금지

법적 식별 필드(legal identity fields)를 비교할 때 다음 방법을 사용해서는 안 된다.

- LLM 기반 유사도
- 임베딩(embedding) 기반 유사도
- 근사 편집 거리(approximate edit distance)를 이용한 일치 판정

명시적으로 정의된 결정론적 정규화만 허용된다.

---

# 출력

각 검증 결과는 반드시 다음 정보를 포함해야 한다.

```text
check_id
status
reason_code
participating values
evidence document IDs
```

---

# 승인 기준

```text
동일한 KNOWN 값
→ SATISFIED

서로 충돌하는 KNOWN 값
→ UNSATISFIED

필수 값 누락
→ UNKNOWN
```

추가로 다음 조건을 만족해야 한다.

- 정규화된 사업자등록번호가 올바르게 비교되어야 한다.
- LLM에 대한 의존성이 존재해서는 안 된다.