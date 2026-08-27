# 심사

## 목표

`RequirementResult` 객체들을 하나의 전체 파이프라인 상태로 변환한다.

AI는 사용하지 않는다.

---

# 전체 상태

허용되는 값:

```text
READY

ACTION_REQUIRED

REVIEW_REQUIRED
```

---

# 판정 알고리즘

blocking 요구사항 중 하나라도 `UNSATISFIED`인 경우:

```text
overall_status = ACTION_REQUIRED
```

그렇지 않고, blocking 요구사항 중 하나라도 `UNKNOWN`인 경우:

```text
overall_status = REVIEW_REQUIRED
```

그 외의 경우:

```text
overall_status = READY
```

---

# 중요 사항

`UNKNOWN`은 실패를 의미하지 않는다.

`UNKNOWN`은 판정을 내리기에 근거가 충분하지 않음을 의미한다.

따라서:

```text
UNKNOWN
```

은 절대로 직접적으로:

```text
ACTION_REQUIRED
```

를 발생시켜서는 안 된다.

---

# 출력

예:

```json
{
  "overall_status": "REVIEW_REQUIRED",
  "requirements": [...],
  "consistency_checks": [...]
}
```

---

# 승인 기준

```text
blocking UNSATISFIED가 하나 존재
→ ACTION_REQUIRED

blocking UNSATISFIED가 여러 개 존재
→ ACTION_REQUIRED

UNSATISFIED가 없고 UNKNOWN이 하나 존재
→ REVIEW_REQUIRED

모든 blocking 요구사항이 SATISFIED
→ READY
```

추가로 다음 조건을 만족해야 한다.

- 출력은 결정론적이어야 한다.