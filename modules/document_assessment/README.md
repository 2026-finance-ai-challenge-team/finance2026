# Hana Corporate Account Document Assessment PoC

## 프로젝트 개요

이 저장소는 가상의 하나은행 비대면 법인계좌 개설 업무를 예시로 삼아,
OCR 이후의 문서 심사 과정을 검증하는 PoC(개념 검증 프로젝트)다. 제출된
문서가 어떤 종류인지 분류하고, 법인명·사업자등록번호·대표자명 같은 값을
추출한 뒤, 문서 사이의 정보가 일치하는지와 업무상 필요한 문서가 갖춰졌는지를
판정한다.

이 프로젝트가 직접 PDF나 이미지를 읽어 OCR을 수행하지는 않는다. 외부 OCR
과정을 거쳐 공통 JSON 구조로 정리된 결과가 이 PoC의 시작점이다. 입력부터
최종 결과까지 같은 근거와 같은 규칙을 사용하면 항상 같은 결과를 내는
결정론적(deterministic) 처리를 검증하는 것이 핵심이다.

최종 상태는 다음 세 가지다.

- `READY`: 현재 PoC 규칙의 모든 필수 조건을 충족했다.
- `ACTION_REQUIRED`: 확인된 근거로 미충족 조건이 존재한다.
- `REVIEW_REQUIRED`: 근거가 부족해 사람이 추가로 확인해야 한다.

이 상태들은 실제 하나은행의 승인이나 계좌 개설 결과가 아니다. 공개적으로
확인 가능한 업무 흐름을 단순화하여 만든 PoC 판정일 뿐이다.

## 무엇을 입력하고 무엇을 출력하는가

### 입력 데이터: Synthetic Normalized OCR

실제 문서 처리 흐름을 개념적으로 나타내면 다음과 같다.

```text
PDF / Image
    |
    v
External OCR Service
    |
    v
CLOVA V2 Adapter (외부 형식 → 공통 OCR 구조)
    |
    v
Normalized OCR JSON
    |
    v
이 PoC의 input.json
```

여기서 synthetic은 실제 고객 문서가 아니라 테스트를 위해 만든 가상의 OCR
결과라는 뜻이다. normalized는 OCR 서비스마다 다른 원본 응답을 그대로 쓰지
않고, 이 프로젝트가 이해하는 공통 `file → page → block` 구조로 정리했다는
뜻이다.

예를 들어 `fixtures/001_ready/input.json`의 일부는 다음과 같은 형태다.

```json
{
  "application_context": {
    "corporation_name": "주식회사 하나테크",
    "business_registration_number": "1234567890",
    "representative_name": "김하나",
    "application_date": "2026-08-01"
  },
  "files": [
    {
      "file_id": "file_business_registration",
      "pages": [
        {
          "page": 1,
          "blocks": [
            {
              "block_id": "br_1",
              "text": "사업자등록증명",
              "bbox": [],
              "confidence": 0.99
            }
          ]
        }
      ]
    }
  ]
}
```

- `application_context`는 신청 과정에서 별도로 받은 법인명, 사업자등록번호,
  대표자명, 신청일 같은 기준 정보다.
- `file_id`는 업로드된 원본 파일을 구분하는 안정적인 식별자다.
- `pages`는 한 파일의 페이지 목록이며, 각 페이지 번호는 1부터 시작한다.
- `block_id`는 OCR이 찾아낸 텍스트 조각을 가리키는 식별자다. 이후 단계가
  어떤 문구를 근거로 사용했는지 추적할 때 쓰인다.
- `text`는 OCR이 인식한 원문이다.
- `bbox`는 원본 페이지에서 텍스트가 위치한 영역이다. 현재 synthetic
  fixture에서는 빈 배열일 수 있다.
- `confidence`는 OCR 인식 신뢰도를 0에서 1 사이의 값으로 표현한다.

실제 OCR 서비스의 응답 형식이 서로 다르다면, 운영 환경에서는 이를 공통
형식으로 바꾸는 연결 계층이 필요할 수 있다.

```text
OCR Provider A ---\
                   +--> normalization / adapter layer --> PoC OCR schema
OCR Provider B ---/
```

Adapter(연결 계층)는 서로 다른 외부 서비스나 대체 구현을 파이프라인이
기대하는 공통 인터페이스 또는 데이터 형식에 연결한다. 이 저장소의
`hana_poc.ocr_adapters.clova_v2`는 NAVER CLOVA General OCR V2 응답을
`OcrFile → OcrPage → OcrBlock` 공통 구조로 변환한다. 실제 CLOVA API를
호출하거나 인증 정보를 다루지는 않는다.

한 CLOVA 응답만으로는 업로드된 물리 파일의 안정적인 식별자를 알 수 없으므로
호출자가 `source_file_id`를 제공한다. 신청 법인명·대표자명·신청일 같은
`application_context`도 OCR 결과가 아니므로 별도로 결합한다.

```python
import json

from hana_poc.ocr_adapters import convert_clova_v2_response
from schemas import ApplicationContext, PocInput

response = json.loads(clova_response_json)
ocr_file = convert_clova_v2_response(
    response,
    source_file_id="file_business_registration",
)
poc_input = PocInput(
    application_context=ApplicationContext(
        corporation_name="주식회사 하나테크",
        application_date="2026-08-01",
    ),
    files=[ocr_file],
)
```

변환 규칙은 다음과 같다.

- `convertedImageInfo.pageIndex`는 0부터 시작하므로 내부 `page`에는 1을 더한다.
- CLOVA `field` 하나를 canonical `OcrBlock` 하나로 보존한다.
- `inferText`는 수정하지 않고 `text`로 옮긴다.
- `inferConfidence`는 clamp하지 않고 0~1 범위를 검증한다.
- 꼭짓점 4개는 provider 순서대로 `[x1, y1, ..., x4, y4]`에 보존한다.
- `block_id`는 `uid`, page index, field index로 결정론적으로 만든다.
- `inferResult != SUCCESS`는 업무 상태가 아니라 adapter conversion error다.

기존 CLI는 계속 normalized `PocInput` JSON만 받는다. CLOVA raw response에는
`application_context`가 없기 때문에 provider 전용 CLI 옵션이나 암묵적인
기본값은 추가하지 않았다.

### 출력 데이터

파이프라인은 각 단계의 결과를 `PipelineResult`에 함께 보존한다.
`PipelineResult`에는 검증된 입력, 분류된 문서, 추출된 문서, 일관성 검사,
요구사항 결과, 최종 Assessment, 설명용 prompt payload가 들어 있다.

CLI는 이 구조를 다음 일곱 section의 읽기 쉬운 JSON으로 출력한다.

```text
[1] INPUT
[2] CLASSIFICATION
[3] EXTRACTION
[4] CONSISTENCY
[5] RULE RESULTS
[6] ASSESSMENT
[7] LLM PROMPT
```

`LLM PROMPT`는 자연어 답변이 아니라, 결정된 결과를 나중에 안전하게 설명할
수 있도록 만든 구조화된 데이터다. 현재 PoC는 실제 LLM을 호출하지 않는다.

## Architecture: 입력이 최종 상태가 되기까지

### 실행 진입점과 orchestration

사용자가 CLI를 실행하면 `cli.py`와 `pipeline.py`가 다음 관계로 동작한다.

```text
사용자
  |
  v
src/hana_poc/cli.py
  |  input.json 읽기, argument 처리, rule/fallback 경로 선택
  v
src/hana_poc/pipeline.py
  |  각 단계를 순서대로 호출하고 PipelineResult 구성
  v
classification
  |
  v
extraction
  |
  v
validation
  |
  v
rule_engine
  |
  v
assessment
  |
  v
explanation
```

`src/hana_poc/cli.py`는 터미널에서 파이프라인을 실행하는 진입점이다.
`input.json`을 읽고 Pydantic schema로 검증하며, `--rules`와
`--classification-fallback` argument를 처리한다. 그런 다음 pipeline을
호출해 일곱 section을 출력한다. 파일이 없거나 JSON, input schema, rule 또는
fallback 설정이 잘못된 경우에는 오류를 stderr에 쓰고 non-zero exit code로
종료한다. 반면 `READY`, `ACTION_REQUIRED`, `REVIEW_REQUIRED`는 모두
정상적인 업무 결과이므로 exit code 0이다.

`src/hana_poc/pipeline.py`는 여러 단계를 올바른 순서로 연결하는 조정 계층
(orchestration layer)이다. 이 파일이 새로운 업무 판정을 내리지는 않는다.
각 단계의 기존 함수를 호출하고 결과를 `PipelineResult`로 묶는다. 분류 보조
구현처럼 교체 가능한 의존성은 외부에서 주입할 수 있어, 기본 CLI는 보조
분류기 없이 실행하고 테스트는 deterministic fake adapter를 연결할 수 있다.

### 단계별 데이터 흐름

```text
Synthetic Normalized OCR (PocInput)
        |
        v
Document Classification
        |
        v
ClassifiedDocument[]
        |
        v
Field Extraction
        |
        v
StructuredDocument[]
        |
        v
Cross-Document Validation
        |
        v
ConsistencyResult[]
        |
        v
Rule Engine
        |
        v
RequirementResult[]
        |
        v
Assessment
        |
        v
READY / ACTION_REQUIRED / REVIEW_REQUIRED
        |
        v
Explanation Prompt Builder
        |
        v
LLM-safe structured prompt
```

#### 1. 문서 단위 분할과 분류

Classification은 normalized OCR의 `OcrFile`, page, block을 입력받는다. 먼저
하나의 파일에 여러 논리적 문서가 들어 있는지 문서 제목과 명시적인 시작
신호로 판단하여 `DocumentUnit`으로 나눈다. 그다음 알려진 제목 규칙을
우선 적용해 각 문서 유형을 결정한다.

출력인 `ClassifiedDocument`에는 문서 유형뿐 아니라 원본 파일, 페이지 범위,
분류 상태, 분류 방식, 판단 근거가 된 `block_id`가 들어 있다. 예를 들어
OCR block `br_1`의 텍스트가 `사업자등록증명`이면 다음처럼 연결된다.

```text
block_id = br_1
text = "사업자등록증명"
        |
        v
document_type = BUSINESS_REGISTRATION_CERTIFICATE
classification_status = CONFIDENT
evidence_block_ids = ["br_1"]
```

제목 규칙으로 확정할 수 없는 문서는 임의의 유형으로 추측하지 않고
`document_type = UNKNOWN`으로 남긴다.

#### 2. 문서별 필드 추출

Extraction은 `ClassifiedDocument`를 입력받아 문서 유형에 맞는 필드를
결정론적 패턴으로 찾는다. 사업자등록번호의 하이픈 제거, 법인명의 명백한
공백 차이 제거처럼 안전하게 정의된 정규화도 이 단계에서 수행한다. 퍼지
유사도나 의미 추론으로 값을 만들어내지는 않는다.

출력인 `StructuredDocument`는 문서 유형과 함께 법인명, 사업자등록번호,
대표자명, 발급일자 등 추출된 필드와 그 근거를 담는 구조화된 문서 객체다.
각 필드는 `KNOWN` 또는 `UNKNOWN` 상태를 가진다.

```text
OCR block
block_id = br_4
text = "대표자: 김하나"
        |
        v
ExtractedField
name = representative_name
value = "김하나"
status = KNOWN
evidence_block_ids = ["br_4"]
```

값을 신뢰할 수 없으면 빈 문자열이나 추정값을 넣지 않는다. `value = null`,
`status = UNKNOWN`으로 표현한다.

#### 3. 문서 간 일관성 검증

Validation은 여러 `StructuredDocument`와 `application_context`를 입력받아
같은 의미의 필드가 서로 일치하는지 비교한다. 비교에는 앞 단계가 만든
정규화 값을 사용하며, LLM이나 의미적 유사도는 사용하지 않는다.

출력인 `ConsistencyResult`에는 검사 식별자 `check_id`, 상태, 판정 이유를
나타내는 `reason_code`, 비교에 참여한 값, 관련 문서 식별자가 들어 있다.
예를 들어 두 문서의 대표자명이 모두 알려져 있고 같으면 다음 결과가 된다.

```text
사업자등록증 representative_name = "김하나"  (br_4)
법인등기   representative_name = "김하나"  (reg_4)
                    |
                    v
REPRESENTATIVE_NAME_MATCH = SATISFIED
reason_code = VALUES_MATCH
```

한쪽 값이 `UNKNOWN`이면 충돌이라고 단정하지 않고 일관성 결과도
`UNKNOWN`으로 유지한다.

#### 4. 선언적 업무 규칙 평가

Rule engine은 `StructuredDocument[]`, `ConsistencyResult[]`,
`application_context`, YAML rule configuration을 입력받는다. YAML에 선언된
문서 존재 조건, 일관성 검사 조건, freshness 기간을 일반적인 evaluator로
평가한다.

출력인 `RequirementResult`에는 `requirement_id`, `SATISFIED /
UNSATISFIED / UNKNOWN` 상태, `blocking` 여부, `reason_code`, 관련 문서
근거가 들어 있다. `reason_code`는 단순 자유 문장 대신
`REQUIRED_DOCUMENT_MISSING`, `DOCUMENT_EXPIRED`처럼 결과가 나온 이유를
프로그램이 안정적으로 구분하는 코드다.

`fixtures/001_ready/input.json`에서는 필수 문서가 모두 있고 법인 정보도
일치하므로 현재 YAML에 선언된 여섯 개 blocking requirement가 모두
`SATISFIED`가 된다.

#### 5. 전체 Assessment

Assessment는 `RequirementResult[]`와 `ConsistencyResult[]`를 입력받는다.
여기서는 새로운 문서 규칙을 평가하지 않고, blocking requirement들의 상태를
정해진 우선순위로 집계한다.

출력인 `Assessment`는 전체 상태와 upstream requirement·consistency 결과를
그대로 보존한다. fixture 001에서는 모든 blocking requirement가
`SATISFIED`이므로 전체 상태가 `READY`가 된다.

#### 6. 설명용 prompt 구성

Explanation Prompt Builder는 `Assessment`를 입력받아 설명에 필요한 필드만
허용 목록 방식으로 선택한다. 상태, `requirement_id`, `reason_code`,
evidence와 함께 “UNKNOWN을 거절로 설명하지 않는다” 같은 제약을 구조화된
payload에 넣는다.

출력은 JSON으로 직렬화 가능한 LLM-safe prompt다. 이 단계는 상태를 다시
판단하거나 새로운 evidence를 만들지 않으며, 실제 LLM API를 호출하지도 않는다.

### 단계 사이의 Pydantic 데이터 계약

이 프로젝트는 단계 사이에 구조가 불명확한 Python `dict`를 계속 넘기지
않는다. 대신 `schemas/`에 Pydantic으로 입력과 출력의 필드 및 타입을 명시한
데이터 모델을 정의한다.

| 단계 | 대표 출력 모델 | 담는 내용 |
| --- | --- | --- |
| Classification | `ClassifiedDocument` | 문서 유형, 분류 상태, 페이지 범위, OCR 근거 |
| Extraction | `StructuredDocument` | 추출 필드, 정규화 값, 필드 상태와 근거 |
| Validation | `ConsistencyResult` | 비교 상태, 참여 값, 이유와 문서 근거 |
| Rule Engine | `RequirementResult` | 요구사항 상태, blocking 여부, reason code, 근거 |
| Assessment | `Assessment` | 전체 상태와 보존된 upstream 결과 |

이 계약은 잘못된 enum이나 값 구조를 단계 경계에서 조기에 발견하고,
`UNKNOWN` 필드가 값을 꾸며내거나 빈 문자열로 표현되지 않도록 검증한다.
또한 한 단계의 내부 구현 방식이 다음 단계로 새어나가지 않게 하여 각 모듈이
공개된 데이터 구조에만 의존하도록 한다.

## 왜 이런 구조를 선택했는가

### 같은 근거와 규칙에는 같은 결과를 낸다

결정론적 판정은 동일한 evidence와 동일한 rule configuration에 언제나 같은
결과를 돌려준다는 뜻이다. 문서 심사 결과를 재현하고, 왜 그 결과가 나왔는지
검토하려면 이 성질이 중요하다. 이 프로젝트는 validation, rule engine,
assessment에서 현재 시간, random, network, LLM 추론을 사용하지 않으며 문서
freshness도 input의 `application_date`를 기준으로 계산한다.

### 모르는 것과 충족되지 않은 것을 구분한다

`UNKNOWN`은 확인할 정보가 부족하다는 뜻이고, `UNSATISFIED`는 확인된 근거로
조건이 충족되지 않았다는 뜻이다. 둘을 합치면 아직 확인되지 않은 문서를
누락으로 단정하거나, 확인되지 않은 값을 충돌로 잘못 판단할 수 있다. 그래서
schema, validation, rule engine, assessment, prompt 전 구간에서 두 상태를
분리해 보존한다.

### 결과와 원본 근거를 함께 보존한다

근거(evidence)는 추출값이나 판정이 어디에서 나왔는지 가리키는 참조다.
추출된 `representative_name = 김하나`만 남기는 대신 원본 OCR의 `br_4`도
함께 기록한다. Classification은 block ID를, validation과 rule engine은 관련
document ID를 보존하므로 결과를 원본 입력까지 추적할 수 있다.

### 업무 정책과 평가 방법을 분리한다

선언적 규칙(declarative rule)은 “어떤 문서가 필요한가” 같은 정책을 코드의
`if requirement_id == ...` 분기 대신 YAML 데이터로 표현한다. Python
evaluator는 문서 존재, 후보 문서, 일관성 결과, freshness 같은 규칙 구조를
일반적으로 해석한다. 따라서 같은 구조의 다른 workflow나 version을 추가할 때
evaluator의 control flow를 바꾸지 않고 별도 rule set을 제공할 수 있다.

### 단계 사이의 계약을 코드로 검증한다

Pydantic 데이터 모델은 문서에만 적어 둔 약속이 아니라 실행 시 검증되는
계약이다. 허용되지 않은 `DocumentType`, `UNKNOWN` candidate, 값이 들어 있는
`UNKNOWN` field, 근거가 없는 `KNOWN` field 같은 잘못된 상태를 조기에
거부한다.

### AI를 보조 수단으로 제한한다

LLM은 비정형 입력을 해석하거나 사람이 읽을 설명을 만드는 데 도움을 줄 수
있지만, 은행 업무 상태를 결정하는 기준으로 사용하면 결과 재현이 어려워진다.
이 프로젝트는 AI가 보조할 수 있는 지점과 결정론적 core를 분리하고, 최종
상태는 항상 명시적인 데이터와 규칙으로 계산한다.

## Three-Valued Logic: 정보 부족과 충돌을 구분하기

이 프로젝트의 일관성 검사와 requirement 평가는 세 가지 상태를 사용한다.

| 상태 | 판단할 수 있는 내용 |
| --- | --- |
| `SATISFIED` | 필요한 근거가 있고 값이 일치하거나 조건이 충족됨 |
| `UNSATISFIED` | 확인된 근거로 값 충돌, 문서 누락, 만료 등을 판정할 수 있음 |
| `UNKNOWN` | 필요한 근거가 없거나 신뢰할 수 없어 어느 쪽인지 결정할 수 없음 |

대표자 정보가 다음과 같다고 가정한다.

```text
사업자등록증 대표자 = 김하나
법인등기 대표자     = UNKNOWN
```

법인등기의 대표자 정보가 확인되지 않았으므로 두 값이 같다고도, 다르다고도
결정할 수 없다.

```text
REPRESENTATIVE_NAME_MATCH = UNKNOWN
```

이는 `UNSATISFIED`가 아니다. “정보가 확인되지 않았다”와 “확인된 두 정보가
충돌한다”는 서로 다른 상황이기 때문이다.

반대로 다음처럼 알려진 값 두 개가 실제로 다르면 결과도 달라진다.

```text
사업자등록증 대표자 = 김하나
법인등기 대표자     = 박하나

REPRESENTATIVE_NAME_MATCH = UNSATISFIED
reason_code = KNOWN_VALUES_CONFLICT
```

`UNKNOWN`을 암묵적으로 `UNSATISFIED`로 바꾸지 않는 것이 이 파이프라인의
핵심 불변조건이다.

## Assessment: 요구사항을 전체 상태로 집계하기

`blocking`은 해당 requirement가 최종 Assessment 상태 결정에 영향을 주는
필수 조건이라는 뜻이다. Assessment는 다음 우선순위를 적용한다.

```text
blocking UNSATISFIED가 하나라도 존재
        |
        v
ACTION_REQUIRED

그렇지 않고 blocking UNKNOWN이 하나라도 존재
        |
        v
REVIEW_REQUIRED

그 외: 모든 blocking requirement가 SATISFIED
        |
        v
READY
```

- `READY`는 현재 제출된 synthetic 문서가 PoC rule set을 충족했다는 뜻이며,
  실제 은행 승인이나 계좌 개설 완료를 의미하지 않는다.
- `ACTION_REQUIRED`는 문서 누락, 확인된 값 충돌, 문서 만료처럼 결정론적으로
  확인된 미충족 조건이 있다는 뜻이다.
- `REVIEW_REQUIRED`는 거절이 아니라 evidence 부족으로 추가 확인이 필요하다는
  뜻이다.

따라서 blocking `UNKNOWN`은 직접 `ACTION_REQUIRED`가 되지 않는다.

## AI Boundary: LLM이 가능한 곳과 금지되는 곳

설계상 LLM 또는 LLM과 호환되는 보조 구현은 다음 경계에서만 사용할 수 있다.

- 규칙으로 확정하기 어려운 문서 분류
- 정형 패턴만으로 처리하기 어려운 필드 추출
- 이미 결정된 결과를 사용자가 이해하기 쉽게 설명

현재 구현에서 field extraction은 모두 결정론적 규칙을 사용한다. 문서 분류에는
교체 가능한 interface만 있으며 fixture 006에서 실제 LLM 대신 file-backed
fake adapter를 사용한다. Explanation도 prompt payload까지만 만들고 외부
모델을 호출하지 않는다.

다음 판정은 LLM이 수행해서는 안 된다.

- `SATISFIED`, `UNSATISFIED`, `UNKNOWN`
- `READY`, `ACTION_REQUIRED`, `REVIEW_REQUIRED`

특히 validation → rule engine → assessment로 이어지는 deterministic core는
LLM client나 explanation 구현에 의존하지 않는다. Architecture tests가 이
의존성 경계를 지속적으로 검사한다.

## YAML Rule Engine: 정책과 evaluator의 책임 분리

현재 workflow의 업무 정책 source of truth는 다음 파일이다.

```text
rules/HANA_BANK/CORPORATE_NON_FACE_TO_FACE_ACCOUNT_OPENING/poc-v1.yaml
```

YAML은 “무엇을 요구하는가?”를 정의한다. Python의 generic evaluator는 “그
선언을 어떤 3값 논리로 평가하는가?”를 담당한다. 현재 evaluator에는 특정
`requirement_id`를 위한 특별 분기가 없다.

예를 들어 다음 규칙은 주주정보 관련 필수 조건을 선언한다.

```yaml
- id: SHAREHOLDER_INFORMATION_REQUIRED
  blocking: true
  document_presence:
    any_of:
      - SHAREHOLDER_REGISTER
      - STOCK_CHANGE_STATEMENT
```

이를 한국어로 풀면 “최종 Assessment에 영향을 주는 주주정보 요구사항은
주주명부 또는 주식등변동상황명세서 중 하나가 확인되면 충족된다”는 뜻이다.
`any_of`의 문서 중 확정된 문서가 있으면 `SATISFIED`, 관련 후보 문서만
있으면 `UNKNOWN`, 둘 다 없으면 `UNSATISFIED`가 된다.

Freshness(문서 최신성)도 requirement마다 선언할 수 있다. 현재
`CORPORATE_REGISTRY_REQUIRED`는 `max_age_days: 90`을 사용하며,
`application_date - issue_date`로 기간을 계산한다. system current date에
따라 결과가 바뀌지 않는다.

## 지원 문서 유형

영문 `DocumentType`은 사용자에게 보여주기 위한 문구가 아니라 Python, YAML,
JSON, test 사이에서 동일하게 사용하는 안정적인 machine-readable identifier다.

| 시스템 식별자 | 문서 |
| --- | --- |
| `BUSINESS_REGISTRATION_CERTIFICATE` | 사업자등록증명 |
| `CORPORATE_REGISTRY` | 법인 등기사항전부증명서 |
| `SHAREHOLDER_REGISTER` | 주주명부 |
| `STOCK_CHANGE_STATEMENT` | 주식등변동상황명세서 |
| `VAT_TAX_BASE_CERTIFICATE` | 부가가치세 과세표준증명 |
| `STANDARD_FINANCIAL_STATEMENT_CERTIFICATE` | 표준재무제표증명 |
| `UNKNOWN` | 문서 유형을 확정할 수 없음 |

“시스템이 표현할 수 있는 문서 유형”과 “특정 workflow에서 반드시 필요한
문서”는 다른 개념이다. 어떤 문서가 필수이고 무엇으로 대체할 수 있는지는
YAML rule set이 결정한다.

## Fixture Scenarios

`fixtures/`의 fixture는 실제 고객 정보가 아닌 synthetic OCR 입력과 기대
결과를 한 디렉터리에 묶은 실행 가능한 명세(executable specification)다.
`expected.json`은 전체 `PipelineResult`를 복제한 snapshot이 아니라, 각
scenario가 중요하게 검증하는 필드만 선언하는 partial assertion이다.

| Fixture | 검증 상황 | 기대 상태 |
| --- | --- | --- |
| `001_ready` | 모든 필수 문서가 있고 법인 정보가 일치 | `READY` |
| `002_missing_registry` | 법인 등기사항증명서 누락 | `ACTION_REQUIRED` |
| `003_missing_sales_evidence` | 매출 증빙 문서 누락 | `ACTION_REQUIRED` |
| `004_company_name_mismatch` | 문서 사이의 법인명 충돌 | `ACTION_REQUIRED` |
| `005_unknown_representative` | 법인등기의 대표자 필드가 `UNKNOWN` | `REVIEW_REQUIRED` |
| `006_ambiguous_document` | 필수 문서 후보일 수 있는 미분류 문서 | `REVIEW_REQUIRED` |
| `007_multi_document_pdf` | 하나의 OCR file에 네 개의 논리 문서 포함 | `READY` |
| `008_expired_document` | 법인등기 문서가 freshness 기간을 초과 | `ACTION_REQUIRED` |

E2E runner는 `input.json`과 `expected.json`이 있는 fixture를 일반적으로
발견한다. 같은 디렉터리에 `classification_fallback.json`이 있으면 이를
deterministic fake classification adapter 설정으로 주입한다. 세부 fixture
계약은 [fixtures/README.md](fixtures/README.md)를 참고한다.

## Repository Structure

- `schemas/`: 단계 사이에서 사용하는 Pydantic 데이터 계약을 정의한다.
- `src/hana_poc/classification/`: OCR page를 논리적 document unit으로 나누고
  알려진 제목 규칙 또는 주입된 보조 분류 결과로 문서 유형을 결정한다.
- `src/hana_poc/extraction/`: 문서 유형별 업무 필드를 추출하고 안전하게
  정규화한다.
- `src/hana_poc/validation/`: 여러 문서와 `application_context` 사이의
  값을 비교하여 `ConsistencyResult`를 만든다.
- `src/hana_poc/rule_engine/`: YAML의 문서 존재·일관성·freshness 조건을
  평가하여 `RequirementResult`를 만든다.
- `src/hana_poc/assessment/`: blocking requirement 결과를 전체 상태로
  집계한다.
- `src/hana_poc/explanation/`: Assessment를 상태 변경 없이 LLM-safe
  structured prompt로 투영한다.
- `src/hana_poc/pipeline.py`: 위 단계를 순서대로 연결하고 구조화된
  `PipelineResult`를 반환하는 orchestration layer다.
- `src/hana_poc/cli.py`: input과 option을 받아 pipeline을 실행하고 결과를
  출력하는 터미널 entry point다.
- `rules/`: bank, workflow, version별 business policy를 YAML로 관리한다.
- `fixtures/`: synthetic input과 partial expected assertion을 관리한다.
- `tests/`: unit, integration, E2E, architecture test를 계층별로 관리한다.
- `docs/`: 정확한 데이터 계약, stage specification, scope, acceptance
  criteria를 제공한다.

프로젝트 전체 경계는 [ARCHITECTURE.md](ARCHITECTURE.md), 상세 범위는
[POC_SCOPE.md](docs/product/POC_SCOPE.md), 데이터 구조는
[PIPELINE_CONTRACTS.md](docs/contracts/PIPELINE_CONTRACTS.md), 승인 기준은
[ACCEPTANCE_CRITERIA.md](docs/ACCEPTANCE_CRITERIA.md)에서 확인할 수 있다.

## Installation

Python 3.9 이상과 [uv](https://docs.astral.sh/uv/)를 사용한다. `uv`가 프로젝트
루트의 `.venv`를 만들고 lockfile을 기준으로 의존성을 동기화하므로, 별도로
가상환경을 활성화하거나 `pip`를 직접 실행할 필요가 없다.

```bash
uv sync --extra test
```

Runtime dependency는 Pydantic과 PyYAML뿐이다. `pytest`는 production
dependency가 아니라 `test` optional dependency로 관리한다. `uv.lock`은
재현 가능한 개발·테스트 환경을 위해 함께 관리한다.

## Usage

기본 fixture를 실행한다.

```bash
uv run python -m hana_poc.cli fixtures/001_ready/input.json
```

기본 rule set은
`rules/HANA_BANK/CORPORATE_NON_FACE_TO_FACE_ACCOUNT_OPENING/poc-v1.yaml`이다.
다른 rule file을 검증하려면 `--rules PATH`로 명시적으로 override할 수 있다.

CLI 출력은 앞에서 설명한 일곱 section을 포함한다. 전체 JSON은 길기 때문에
터미널 출력에서 확인하며, fixture 001의 Assessment는 `READY`다.

## Ambiguous Classification: 확정할 수 없는 문서 처리

fixture 006은 제목이 `법인 관련 증명서`일 뿐이어서 규칙만으로는 이 문서가
법인 등기사항증명서인지 확정할 수 없는 상황을 나타낸다.

```text
rule-based classifier가 문서 유형을 확정하지 못함
        |
        v
보조 분류 결과가 있다면 가능한 문서 유형 후보를 제공
        |
        v
PoC에서는 실제 LLM 대신 deterministic file-backed fake adapter 사용
        |
        v
candidate_document_types = [CORPORATE_REGISTRY]
        |
        v
확정 문서가 아니므로 SATISFIED로 판단할 수 없음
        |
        v
문서가 없다고도 확정할 수 없으므로 UNSATISFIED도 아님
        |
        v
CORPORATE_REGISTRY_REQUIRED = UNKNOWN
        |
        v
REVIEW_REQUIRED
```

여기서 fallback(대체 판단 절차)은 제목 규칙만으로 결정하지 못했을 때 선택적으로
다음 보조 분류기로 넘기는 과정이다. Adapter는 그 보조 구현을 공통
classification interface에 연결한다. `candidate_document_types`는 확정된
문서 유형이 아니라 “가능성이 있어 후속 검토가 필요한 허용 후보 유형” 목록이다.

다음 명령은 fixture 006의 가짜 보조 분류 결과를 명시적으로 주입한다.

```bash
uv run python -m hana_poc.cli \
  fixtures/006_ambiguous_document/input.json \
  --classification-fallback \
  fixtures/006_ambiguous_document/classification_fallback.json
```

`classification_fallback.json`은 실제 LLM 응답이 아니다. source file과 page
범위에 대해 어떤 확정 유형 또는 후보 유형을 반환할지를 적은 테스트 가능한
JSON 설정이다. 위 명령은 exit code 0과 `REVIEW_REQUIRED`를 반환한다.

fallback option 없이 fixture 006을 실행하면 보조 후보 정보가 없다. 빈 후보를
모든 missing-document requirement의 `UNKNOWN`으로 확대하지 않는 generic
semantics에 따라 이 경우에는 `ACTION_REQUIRED`가 될 수 있다. E2E acceptance
scenario는 명시적인 fallback 설정을 사용한다.

## Testing

전체 test suite는 다음 명령으로 실행한다.

```bash
uv run pytest
```

- Unit tests는 schema와 각 stage의 작은 결정론적 동작을 검증한다.
- Integration tests는 stage 연결, orchestration, CLI 동작을 검증한다.
- E2E tests는 discovery된 8개 fixture의 모든 partial expected assertion을
  검증한다.
- Architecture tests는 금지된 downstream dependency, `rule_engine →
  explanation` 의존, deterministic core의 LLM provider 의존,
  `schemas → pipeline implementation` 의존이 없는지 AST로 검사한다.

테스트에는 실제 OCR API, 은행 API, 데이터베이스, LLM client 또는 credential이
필요하지 않다.

## Safety and Scope

- 실제 하나은행 내부 시스템이나 실제 계좌 개설 승인 시스템이 아니다.
- 실제 하나은행의 내부 정책 전체가 아니라 공개 정보를 바탕으로 단순화한
  PoC rule set을 사용한다.
- 실제 고객 PII를 사용하지 않으며 fixture는 synthetic data만 포함한다.
- 실제 OCR API나 은행 API를 호출하지 않고, 운영 데이터베이스를 사용하지 않는다.
- 실제 production LLM integration이나 credential을 요구하지 않는다.
- `READY`는 PoC 규칙 충족 상태일 뿐 실제 은행 승인이나 계좌 개설 완료가
  아니다.

## Limitations

- PDF/image OCR과 실제 CLOVA API 호출은 구현 범위 밖이다.
- CLOVA V2 adapter는 이미 받은 합성 응답 JSON의 형식 변환만 수행한다.
- 기본 CLI 입력은 계속 synthetic normalized OCR JSON으로 제한된다.
- 실제 LLM integration은 없으며 모호한 분류는 file-backed fake adapter로
  시뮬레이션한다.
- field extraction은 현재 지원 문서와 알려진 deterministic pattern으로
  제한된다.
- 지원 document type이 제한적이며 YAML rule set은 simplified PoC policy다.
- 설명 단계는 자연어 응답이 아니라 LLM-safe structured prompt까지만 생성한다.

README는 프로젝트를 처음 실행하고 핵심 설계를 이해하기 위한 문서다. 정확한
schema field와 stage별 계약은 `docs/`의 specification을 참고한다.
