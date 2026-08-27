# 승인 기준

# A. End-to-End

CLI에서 다음 명령이 정상적으로 실행되어야 한다.

```bash
python -m hana_poc.cli fixtures/001_ready/input.json
```

출력에는 다음 항목이 포함되어야 한다.

```text
CLASSIFICATION
EXTRACTION
CONSISTENCY
RULE RESULTS
ASSESSMENT
LLM PROMPT
```

---

# B. 결정론적 동작

동일한 fixture를 두 번 실행하면 결정론적 파이프라인 결과가 동일하게 생성되어야 한다.

LLM mock의 출력은 결정론적인 텍스트 생성 요구사항에서는 제외되지만, 규칙 평가 결과에는 영향을 주어서는 안 된다.

---

# C. 3값 논리

시스템은 다음 세 가지 상태를 명확하게 구분해야 한다.

```text
SATISFIED

UNSATISFIED

UNKNOWN
```

어떠한 코드 경로에서도 `UNKNOWN`을 `UNSATISFIED`로 축소하거나 변환해서는 안 된다.

---

# D. 아키텍처

다음 의존성은 금지한다.

```text
rule_engine -> explanation
```

다음 의존성 역시 금지한다.

```text
rule_engine -> LLM client
```

모든 LLM adapter가 비활성화된 상태에서도 규칙 엔진은 정상적으로 동작해야 한다.

---

# E. 근거(Evidence)

모든 분류 결과에는 근거가 되는 block ID가 포함되어야 한다.

모든 `KNOWN` 상태의 추출 필드에는 근거(evidence)가 포함되어야 한다.

모든 규칙 평가 결과에는 reason code가 포함되어야 한다.

---

# F. Fixture 예상 결과

```text
001_ready
→ READY

002_missing_registry
→ ACTION_REQUIRED

003_missing_sales_evidence
→ ACTION_REQUIRED

004_company_name_mismatch
→ ACTION_REQUIRED

005_unknown_representative
→ REVIEW_REQUIRED

006_ambiguous_document
→ REVIEW_REQUIRED

007_multi_document_pdf
→ READY

008_expired_document
→ ACTION_REQUIRED
```

---

# G. 테스트

다음 테스트가 필요하다.

```text
unit tests

integration tests

architecture tests

end-to-end fixture tests
```

---

# H. 실제 개인정보 사용 금지

테스트와 fixture에는 합성된 가상 신원 정보만 포함되어야 한다.

실제 개인정보(PII)를 사용해서는 안 된다.

---

# I. 운영 환경 연동 금지

PoC의 테스트 suite를 통과하기 위해 다음 항목을 필요로 해서는 안 된다.

```text
실제 OCR API

실제 은행 API

운영용 데이터베이스

실제 LLM 인증 정보(credentials)
```