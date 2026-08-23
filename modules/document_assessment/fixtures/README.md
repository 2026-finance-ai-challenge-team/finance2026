# Fixture

Fixture는 실행 가능한 명세(executable specification)이다.

각 fixture 디렉터리는 다음 파일을 포함한다.

```text
input.json
expected.json
```

`input.json`은 정규화된 synthetic OCR 입력과 application context를 포함한다.

`expected.json`은 전체 파이프라인 출력을 복제하지 않는다.
대신 해당 fixture가 검증하려는 핵심 deterministic assertion만 정의한다.

E2E fixture test는 `expected.json`에 명시된 모든 assertion이 실제
파이프라인 결과에서 충족되는지 검증한다.

`expected.json`에 명시되지 않은 파이프라인 출력 필드는 fixture의
성공 여부를 판단하는 비교 대상이 아니다.

Fixture에는 반드시 합성 데이터(synthetic data)만 사용해야 한다.

선택적 runtime artifact인 `classification_fallback.json`이 fixture 디렉터리에
있으면 E2E runner는 이를 결정론적 file-backed classification adapter로
주입한다. 이 규약은 모든 fixture에 동일하게 적용되며 실제 LLM 호출은 없다.

---

# Fixture 001 - READY

모든 필수 문서가 존재한다.

필수로 추출되어야 하는 모든 필드가 `KNOWN` 상태이다.

문서 간 신원 및 식별 정보가 모두 일치한다.

예상 결과:

```text
READY
```

---

# Fixture 002 - 법인 등기사항증명서 누락

법인 등기사항증명서가 존재하지 않는다.

누락된 법인 등기사항증명서일 가능성이 있는 모호한 문서도 존재하지 않는다.

예상 요구사항 결과:

```text
CORPORATE_REGISTRY_REQUIRED
= UNSATISFIED
```

예상 심사 결과:

```text
ACTION_REQUIRED
```

---

# Fixture 003 - 매출 증빙 누락

허용되는 매출 증빙 문서가 존재하지 않는다.

예상 결과:

```text
SALES_EVIDENCE_REQUIRED
= UNSATISFIED
```

전체 심사 결과:

```text
ACTION_REQUIRED
```

---

# Fixture 004 - 법인명 불일치

사업자등록증:

```text
주식회사 하나테크
```

법인 등기사항증명서:

```text
주식회사 다른테크
```

예상 결과:

```text
COMPANY_NAME_MATCH
= UNSATISFIED
```

전체 심사 결과:

```text
ACTION_REQUIRED
```

---

# Fixture 005 - 대표자 정보 UNKNOWN

사업자등록증:

```text
김하나
```

법인 등기사항증명서의 대표자 필드:

```text
UNKNOWN
```

예상 결과:

```text
REPRESENTATIVE_NAME_MATCH
= UNKNOWN
```

전체 심사 결과:

```text
REVIEW_REQUIRED
```

---

# Fixture 006 - 모호한 문서

업로드된 문서 중 하나를 신뢰할 수 있는 수준으로 분류할 수 없다.

해당 문서는 누락된 필수 문서일 가능성이 있다.

`classification_fallback.json`은 실제 LLM 호출이 아닌 결정론적 file-backed
fake adapter의 입력이다. CLI에서 `--classification-fallback`으로 명시적으로
지정하면 `file_ambiguous`의 1페이지 문서가 `CORPORATE_REGISTRY` 후보를 가진
`UNKNOWN` 분류로 처리된다.

예상 결과:

```text
관련 requirement
= UNKNOWN
```

전체 심사 결과:

```text
REVIEW_REQUIRED
```

파이프라인이 잘못하여 `ACTION_REQUIRED`를 반환해서는 안 된다.

---

# Fixture 007 - 하나의 PDF에 여러 문서 포함

하나의 OCR 파일에 여러 개의 문서 단위(document unit)가 포함되어 있다.

예상 분류:

```text
1~2페이지 -> BUSINESS_REGISTRATION_CERTIFICATE

3~5페이지 -> CORPORATE_REGISTRY

6페이지 -> SHAREHOLDER_REGISTER

7~8페이지 -> VAT_TAX_BASE_CERTIFICATE
```

예상 결과:

```text
READY
```

---

# Fixture 008 - 유효기간이 지난 문서

문서가 설정된 최신성 허용 기간(freshness window)을 초과한다.

예상 결과:

```text
관련 requirement
= UNSATISFIED
```

사유:

```text
DOCUMENT_EXPIRED
```

전체 심사 결과:

```text
ACTION_REQUIRED
```
