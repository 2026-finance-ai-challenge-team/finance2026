# 자연어 은행 업무 찾기

사용자가 금융 용어를 몰라도 생활 상황을 입력하면 LLM이 업무 의도를 해석하고,
공식 출처가 있는 은행·서비스 카탈로그에 연결한다. `feat/task-intent`에서 추가한
기능이며 문서 판정 파이프라인과 독립적으로 실행한다.

```text
자연어 query
  → 식별번호 형태의 숫자·이메일 마스킹
  → LLM: 카탈로그의 업무 하나 선택 + 사용자가 언급한 은행·채널·방문자·목적 추출
  → 서버: 응답 검증 + 은행 그라운딩 + 업무 카탈로그 대조
  → 서류가 갈리는 축이 남아 있으면 버튼으로 되묻기
  → 확정되면 데이터베이스의 필요 서류 목록과 공식 출처 반환
```

LLM은 업무를 **고르기만** 한다. 필요 서류는 모델을 거치지 않고 데이터베이스 값을
그대로 내보낸다. 모델이 서류 이름이나 인정기간을 바꿔 쓰는 경로를 만들지 않는다.

## 구현 경계

- 업무·서류 데이터: 정책 데이터베이스의 `pg_dump` 결과를 `scripts/extract_policy_catalog.py`로
  `apps/web/server/task-intent/catalog.generated.json`에 평탄화한다. 서버는 실행 중에
  데이터베이스에 접속하지 않는다. 덤프가 갱신되면 스크립트를 다시 실행한다.
- 서버 모듈: `apps/web/server/task-intent/`. 화면이나 Next.js에 의존하지 않는 함수로 분리.
- HTTP: Next.js의 `POST /api/v1/tasks/resolve`. 기존 웹 앱의 서버에서 실행.
- 화면: 자연어 입력과 후보 선택. 업무 찾기 요청만 같은 출처의 API를 사용.
- 분석·삭제·ZIP 요청은 기존 `NEXT_PUBLIC_PROOFBRIDGE_API_BASE_URL` 서버를 사용.
- 문서 규칙, 준비 완료 판정, 상속 서류 심사와 상속 키트는 추가하지 않았다.

현재 카탈로그는 6개 은행(하나·KB국민·우리·신한·IBK기업·카카오뱅크)의 업무 56건이며
53건의 정책 버전에 66개의 요건 조합이 붙어 있다. 정책 상태가 `draft`인 항목은
응답에서 `confirmation_status: "IN_REVIEW"`로 표시하고 화면에도 확인 중임을 밝힌다.
공식 확인이 끝난 항목만 `CONFIRMED`다.

은행 이름을 아는 것과 해당 은행의 업무를 지원하는 것은 다르다. 사용자가 말한 은행에
그 업무가 없으면 같은 업무를 가진 다른 은행을 후보로 제시하고, 임의로 대체하지 않는다.

## 실행

카탈로그를 먼저 생성한다.

```bash
npm --prefix apps/web run catalog -- <덤프>.sql \
  --out apps/web/server/task-intent/catalog.generated.json
```

`apps/web/.env.local`에 서버 전용 `OPENAI_API_KEY`를 설정한다.
모델은 `PROOFBRIDGE_TASK_INTENT_MODEL`로 변경할 수 있으며 기본값은
`gpt-5.4-mini`다. Responses API의 strict JSON Schema 출력을 사용한다.
키를 `NEXT_PUBLIC_` 변수에 넣지 않는다.

```bash
cd apps/web
npm ci
npm run dev -- --port 3000
```

```bash
curl http://localhost:3000/api/v1/tasks/resolve \
  -H 'Content-Type: application/json' \
  -d '{"query":"부모님이 돌아가셔서 재산을 정리하고 싶음"}'
```

설정이 없거나 모델 호출에 실패하면 오류를 반환한다. 업무 찾기에는 가짜 LLM
결과나 키워드 성공 폴백을 사용하지 않는다. 기존 합성 문서 데모는 별도 경로다.

## API 계약 v3

요청은 두 가지 형태다. 본문은 4,096바이트 이하다.

```json
{ "query": "부모님이 돌아가셔서 재산 정리하려고요" }
{ "operation_id": "kb.limited_account_release", "selections": { "purpose_code": "salary" } }
```

첫 번째는 2~300자의 자연어이며 모델을 호출한다. 두 번째는 사용자가 버튼을 누른
뒤의 재요청이며 모델을 호출하지 않는다(`interpretation_method: "selection"`).
출력은 `apps/web/server/task-intent/types.ts`를 정본으로 사용한다.

- `resolution`
  - `RESOLVED`: 은행과 업무가 확정되고 남은 선택지가 없음. `requirements`가 채워진다.
  - `NEEDS_CONFIRMATION`: 은행 미확인이거나 선택이 더 필요함. `requirements`는 항상 빈 배열이다.
  - `UNSUPPORTED`: 카탈로그에 해당 업무가 없음.
- `pending_choice`: 다음에 물어볼 축 하나(`channel` · `visitor_type` · `purpose_code`)와
  그 업무에 실제로 존재하는 선택지만 담는다. 카탈로그에 없는 조합은 버튼에 나오지 않는다.
- `selections`: 모델이 추출했거나 사용자가 고른 값 중 **그 업무의 요건 조합에 실제로
  존재하는 값만** 남는다. 모델이 없는 값을 냈으면 버린다.
- `requirements`: 요건 조합별 서류 묶음. `choice_group`이 같은 서류는 택1이다.
  각 묶음에 공식 출처의 발행처·제목·URL·확인일이 붙는다.
- `confirmation_status`: 정책이 `published`면 `CONFIRMED`, `draft`면 `IN_REVIEW`.

은행을 확인하기 전에는 서류를 내보내지 않는다. 은행이 다르면 서류가 달라지므로,
잘못된 은행의 목록을 먼저 보여주는 것이 가장 위험한 실패다.
LLM의 자기평가 confidence를 사용자에게 정확도나 유사도 백분율로 표시하지 않는다.
v1의 `lexical_score`, `vector_score`, `embedding_model`은 제거했고 벡터 검색은 실행하지 않는다.

## 데이터와 실패 처리

LLM에는 마스킹한 업무 질의와 서비스 정의만 보낸다. 파일, OCR 원문, 문서 필드,
세션 결과는 전달하지 않는다. 숫자·이메일 마스킹은 이름·주소 등 모든 개인정보를
익명화하는 기능이 아니므로 업무 질의에도 불필요한 개인정보를 입력하지 않아야 한다.
서버는 질의와 응답을 저장하거나 로그로 출력하지 않고 `store: false`로 호출한다.
API의 보존·이용 조건은 공급자의 [데이터 정책](https://developers.openai.com/api/docs/guides/your-data)을 따른다.
브라우저에는 사용자가 입력한 문장이 화면 상태로 남으며, 새로 입력하거나 페이지를
종료하면 해당 상태가 교체·해제된다.

모델의 임의 서비스 식별자·추가 필드·잘못된 값과 원문에 없는 은행 언급은 거부한다.
공식 URL과 지원 상태는 모델이 아니라 카탈로그가 제공한다. 요청 제한은 서버
프로세스당 동시 4건·분당 30건이며, 다중 인스턴스 배포의 전체 한도는 별도
게이트웨이에서 설정해야 한다. 모델 요청 제한시간은 15초다.

## 검증

```bash
cd apps/web
npm run test:intent
npm test
```

자동 테스트는 합성 모델 응답을 주입해 카탈로그 매핑, 은행 추정 금지,
미지원 업무, 입력 검증, 숫자·이메일 마스킹, API 오류 처리를 검증한다.
이 테스트 통과를 실제 LLM의 의미 해석 정확도로 해석하지 않는다.
API 키가 있는 환경에서 다음 질의를 실제 모델로 추가 검증한다.

키를 설정한 개발 서버가 실행 중이면 `npm run test:intent:live`로 아래 합성 질의
8건을 실제 모델에 요청하여 확인한다. 기본 대상은 `http://127.0.0.1:3000`이며
`PROOFBRIDGE_TEST_BASE_URL`로 변경할 수 있다. 이 검증은 API 호출 비용이 발생하며
기본 `npm test`에는 포함하지 않는다.

| 입력 | 기대 결과 |
| --- | --- |
| 우리은행에서 아이 인터넷뱅킹 만들어주려고요 | 우리은행 · 미성년자 인터넷뱅킹, 서류 확정 |
| 국민은행 한도계좌 좀 풀고 싶어요 | KB국민은행 · 한도해제, 거래 목적 버튼 |
| 하나은행에서 법인 통장 만들려고요 | 하나은행 · 법인계좌 개설, 채널 버튼 |
| 카카오뱅크 한도계좌 해제하고 싶어요 | 카카오뱅크 · 한도계좌 해제, 서류 확정 |
| 신한은행 예금잔액증명서 떼려고요 | 신한은행 · 잔액증명서 발급 |
| 부모님이 돌아가셔서 재산을 정리하고 싶어요 | 상속 업무 인식, 은행 먼저 확인 |
| 우리 아버지가 돌아가셔서 재산 정리하려고요 | 우리은행으로 오인하지 않음 |
| 부모님께 재산을 미리 증여받고 싶어요 | 현재 카탈로그 밖 업무 |

새 업무는 정책 데이터베이스에 추가한 뒤 덤프를 다시 받아 `npm run catalog`를 실행한다.
코드에 업무를 손으로 적지 않는다. 카탈로그가 바뀌면 위 정답표도 함께 갱신한다.

## 출처

업무·서류 데이터의 공식 출처는 데이터베이스의 `sources` 테이블이 정본이며,
응답의 각 요건 묶음에 발행처·제목·URL·확인일이 함께 실린다. 이 문서에 복제하지 않는다.
카탈로그 생성일과 원본 덤프 파일명은 `catalog.generated.json`에 기록된다.

- [OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs)
- [OpenAI GPT-5.4 mini](https://developers.openai.com/api/docs/models/gpt-5.4-mini)
