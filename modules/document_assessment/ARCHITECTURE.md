# 아키텍처

## 시스템 목표

정규화된 OCR 출력을 설명 가능하고 결정론적인 문서 심사 결과로 변환한다.

---

## 상위 수준 파이프라인

```text
NAVER CLOVA General OCR V2 (선택 입력)
        |
        v
CLOVA OCR Adapter
        |
        v
Canonical 정규화 OCR 출력
        |
        v
문서 단위 분류
        |
        v
필드 추출
        |
        v
구조화된 문서
        |
        v
문서 간 일관성 검증
        |
        v
근거(Evidence)
        |
        v
규칙 엔진
        |
        v
요구사항 결과
        |
        v
심사
        |
        v
설명 프롬프트 빌더
```

---

## 핵심 원칙

모든 파이프라인 단계는 타입이 명시된 입력(typed input)을 받고 타입이 명시된 출력(typed output)을 반환한다.

어떠한 단계도 이전 단계의 구현 세부사항에 의존해서는 안 된다.

예:

분류기(Classifier)의 구현 세부사항은 추출기(Extractor)와 무관해야 한다.

추출기는 오직 `ClassifiedDocument` 계약에만 의존한다.

---

# 모듈 경계

## ocr_adapters

책임:

- 외부 OCR provider 응답을 검증한다.
- provider page와 field를 canonical `OcrFile`, `OcrPage`, `OcrBlock`으로 변환한다.
- 원문 텍스트, 신뢰도, 좌표와 결정론적 evidence ID를 보존한다.
- upstream OCR 실패를 adapter conversion error로 표현한다.

생성 결과:

`OcrFile`

다음을 수행해서는 안 된다:

- 실제 OCR API 호출 또는 credential 처리
- 문서 분류
- 비즈니스 필드 추출 또는 정규화
- 일관성·규칙·심사 상태 판정
- LLM 호출

`source_file_id`는 물리 업로드 파일을 식별하는 caller-owned 값이다. CLOVA의
`image.name`으로 임의 생성하지 않는다. `application_context` 역시 OCR 결과가
아니므로 adapter 외부에서 `PocInput`에 결합한다.

## classification

책임:

- OCR 페이지를 문서 단위로 그룹화한다.
- 각 문서 단위를 분류한다.
- 결정론적 규칙을 우선적으로 사용한다.
- 모호한 분류 결과를 명시적으로 표현한다.

생성 결과:

`ClassifiedDocument`

다음을 수행해서는 안 된다:

- 비즈니스 필드 추출
- 적격 여부 판정

---

## extraction

책임:

- 각 문서 유형에 필요한 필드를 추출한다.
- 추출된 값을 정규화한다.
- 근거 블록 참조(evidence block reference)를 보존한다.
- 누락되거나 불확실한 필드를 명시적으로 표현한다.

생성 결과:

`StructuredDocument`

다음을 수행해서는 안 된다:

- 서로 다른 문서를 비교
- 은행 업무 규칙의 결과를 판정

---

## validation

책임:

- 문서 간 필드를 비교한다.
- 문서의 필드를 신청 컨텍스트(application context)와 비교한다.
- 명시적인 일관성 검사 결과를 생성한다.

생성 결과:

`ConsistencyResult`

다음을 수행해서는 안 된다:

- 전체 신청 상태를 판정

---

## rule_engine

책임:

- 선언적 규칙(declarative rules)을 로드한다.
- 요구사항을 평가한다.
- `SATISFIED` / `UNSATISFIED` / `UNKNOWN` 결과를 생성한다.
- 결정론적인 reason code를 생성한다.
- 근거(evidence)를 보존한다.

생성 결과:

`RequirementResult[]`

다음을 수행해서는 안 된다:

- LLM 호출
- 사용자 대상 자연어 설명 생성

---

## assessment

책임:

요구사항 평가 결과를 하나의 전체 파이프라인 결과로 변환한다.

규칙:

```text
blocking UNSATISFIED가 존재
→ ACTION_REQUIRED

blocking UNSATISFIED가 없고
blocking UNKNOWN이 존재
→ REVIEW_REQUIRED

모든 blocking 요구사항이 SATISFIED
→ READY
```

---

## explanation

책임:

- 심사 결과 구조를 LLM에 안전하게 전달할 수 있는 프롬프트로 변환한다.
- 불필요한 민감정보를 제거하거나 마스킹한다.
- LLM이 규칙 평가 결과를 변경하지 않도록 명시적으로 지시한다.

다음을 수행해서는 안 된다:

- 심사 결과 변경
- 추가적인 은행 업무 요구사항 생성

---

# AI 경계

```text
                    LLM 사용 허용
                         |
          +--------------+--------------+
          |                             |
      모호한 분류                  모호한 추출
          |
          v

---------------- 결정론적 경계 ----------------

구조화된 문서
        |
        v
검증
        |
        v
규칙 엔진
        |
        v
심사

------------------------------------------------

        |
        v

LLM 설명 생성
```

결정론적 영역은 LLM 없이도 동일한 결과를 재현할 수 있어야 한다.

---

# 의존성 규칙

허용:

```text
ocr_adapters -> schemas
classification -> schemas
extraction -> schemas
validation -> schemas
rule_engine -> schemas
assessment -> schemas
explanation -> schemas
```

파이프라인 오케스트레이션(pipeline orchestration)은 모든 파이프라인 모듈에 의존할 수 있다.

금지되는 예:

```text
ocr_adapters -> classification
ocr_adapters -> extraction
ocr_adapters -> rule_engine
rule_engine -> explanation
rule_engine -> OpenAI client
validation -> assessment
schemas -> pipeline modules
```

---

# CLI

초기 PoC는 하나의 진입점(entry point)을 제공한다.

예:

```bash
python -m hana_poc.cli fixtures/001_ready/input.json
```

예상 실행 단계:

```text
[1] INPUT
[2] CLASSIFICATION
[3] EXTRACTION
[4] CONSISTENCY
[5] RULE RESULTS
[6] ASSESSMENT
[7] LLM PROMPT
```

웹 UI는 필요하지 않다.
