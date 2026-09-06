# AGENTS.md

## 프로젝트 목적

이 저장소는 가상의 하나은행 비대면 법인계좌 개설 업무에서 사용되는 OCR 이후 문서 심사 파이프라인(Post-OCR Document Assessment Pipeline)의 PoC(Proof of Concept)를 구현한다.

이 PoC의 목표는 구조화된 OCR 출력이 결정론적(deterministic) 문서 심사 결과로 처리될 수 있는지를 검증하는 것이다.

UI는 구현하지 않는다.

최종 실행 인터페이스는 CLI이며, fixture 또는 JSON 입력을 받아 파이프라인의 중간 결과와 최종 결과를 출력한다.

---

## 범위

### 포함 범위

파이프라인은 정규화된 OCR 출력에서 시작한다.

시스템은 다음 기능을 구현한다.

1. 문서 단위 분할 및 분류
2. 필드 추출
3. 문서 간 일관성 검증
4. 결정론적 규칙 평가
5. `SATISFIED` / `UNSATISFIED` / `UNKNOWN` 요구사항 판정
6. `READY` / `ACTION_REQUIRED` / `REVIEW_REQUIRED` 심사 결과
7. 사용자 대상 설명 생성을 위한 LLM 프롬프트 생성

### 제외 범위

다음 항목은 구현하지 않는다.

- OCR
- 이미지 전처리
- 파일 업로드 UI
- 프론트엔드
- 본인 확인
- 인증
- 운영용 데이터베이스
- 실제 하나은행 API 연동
- 실제 은행 업무상의 승인
- 실제 고객 데이터
- 명시적으로 요청되지 않은 실제 운영 LLM 호출

OCR 입력에는 반드시 합성(synthetic) fixture를 사용해야 한다.

---

## 핵심 아키텍처 불변조건

다음 규칙은 어떠한 경우에도 위반해서는 안 된다.

### AI 경계

LLM은 다음 작업을 보조할 수 있다.

- 모호한 문서 분류
- 비정형 필드 추출
- 사용자 대상 설명 생성

LLM은 다음 상태를 판정해서는 안 된다.

- `SATISFIED`
- `UNSATISFIED`
- `UNKNOWN`
- `READY`
- `ACTION_REQUIRED`
- `REVIEW_REQUIRED`

이러한 판정은 반드시 결정론적으로 수행되어야 한다.

### 근거(Evidence)

추출된 모든 필드는 해당 값의 근거 참조(evidence reference)를 보존해야 한다.

모든 규칙 평가 결과는 어떤 문서 또는 필드가 해당 결과를 발생시켰는지 설명할 수 있어야 한다.

### UNKNOWN 의미론

`UNKNOWN`은 사용 가능한 근거가 결정론적인 판정을 내리기에 충분하지 않음을 의미한다.

`UNKNOWN`을 암묵적으로 `UNSATISFIED`로 변환해서는 안 된다.

### 비즈니스 규칙에서의 퍼지 매칭 금지

비즈니스 규칙은 LLM 추론 또는 의미적 유사도(semantic similarity)를 사용해서는 안 된다.

단, 결정론적인 정규화(normalization)는 사용할 수 있다.

### 민감정보

fixture에는 실제 고객의 개인정보(PII)를 포함해서는 안 된다.

LLM adapter로 전달되는 모든 텍스트는 반드시 마스킹 경계(masking boundary)를 통과해야 한다.

---

## 저장소 구성

작업과 관련된 문서만 읽는다.

시스템 아키텍처:

- `ARCHITECTURE.md`

PoC 범위 및 경계:

- `docs/product/POC_SCOPE.md`

데이터 계약:

- `docs/contracts/PIPELINE_CONTRACTS.md`

파이프라인 명세:

- `docs/pipeline/`

비즈니스 규칙:

- `rules/HANA_BANK/CORPORATE_NON_FACE_TO_FACE_ACCOUNT_OPENING/poc-v1.yaml`

기대 동작 및 승인 기준:

- `docs/ACCEPTANCE_CRITERIA.md`

합성 입력 예제:

- `fixtures/`

---

## 의존성 방향

허용되는 의존성 방향은 다음과 같다.

```text
OCR schema
→ classification
→ extraction
→ validation
→ rule_engine
→ assessment
→ explanation
```

역방향 의존성은 금지한다.

`rule_engine`은 `explanation` 또는 LLM 구현에 절대 의존해서는 안 된다.

---

## 구현 원칙

다음을 우선한다.

- 작고 순수한 함수
- 명시적인 타입
- Pydantic 모델 또는 dataclass
- 결정론적 동작
- 의존성 주입
- 구조화된 결과
- 자유 형식의 내부 오류 메시지 대신 reason code 사용

다음을 피한다.

- 숨겨진 전역 상태
- 거대한 단일 파이프라인 함수
- 여러 Python 파일에 분산되어 하드코딩된 비즈니스 규칙
- 암묵적인 dictionary 구조
- 모든 예외를 포괄적으로 처리하는 catch-all 예외 처리
- 비즈니스 규칙 평가 내부에서의 LLM 호출

---

## 필수 개발 워크플로

모든 작업에서 다음 절차를 따른다.

1. 작업과 관련된 명세를 읽는다.
2. 기존 schema와 test를 확인한다.
3. 요구사항을 충족하는 최소한의 변경만 구현한다.
4. 필요한 test를 추가하거나 수정한다.
5. unit test를 실행한다.
6. integration test를 실행한다.
7. end-to-end fixture test를 실행한다.
8. 아키텍처 제약조건이 유지되는지 검증한다.
9. test가 실패하는 상태에서는 작업이 완료되었다고 선언하지 않는다.

---

## 완료 조건(Definition of Done)

다음 조건을 모두 만족해야 작업이 완료된 것으로 간주한다.

- 관련 test가 통과한다.
- 기존 test가 계속 통과한다.
- schema validation이 성공한다.
- 아키텍처 불변조건을 위반하지 않는다.
- fixture 출력이 기대 출력과 일치한다.
- 요청되지 않은 운영용 dependency가 추가되지 않았다.
