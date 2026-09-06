# 자연어 은행 업무 찾기

사용자가 금융 용어를 몰라도 생활 상황을 입력하면 LLM이 업무 의도를 해석하고,
공식 출처가 있는 은행·서비스 카탈로그에 연결한다. `feat/task-intent`에서 추가한
기능이며 문서 판정 파이프라인과 독립적으로 실행한다.

```text
자연어 query
  → 식별번호 형태의 숫자·이메일 마스킹
  → LLM: 서비스 후보 + 사용자가 언급한 은행 추출
  → 서버: 응답 검증 + 은행·서비스 카탈로그 대조
  → 은행 · 서비스 후보와 공식 링크 반환
  → 사용자 확인 또는 추가 선택
```

## 구현 경계

- 서버 모듈: `apps/web/server/task-intent/`. 화면이나 Next.js에 의존하지 않는 함수로 분리.
- HTTP: Next.js의 `POST /api/v1/tasks/resolve`. 기존 웹 앱의 서버에서 실행.
- 화면: 자연어 입력과 후보 선택. 업무 찾기 요청만 같은 출처의 API를 사용.
- 분석·삭제·ZIP 요청은 기존 `NEXT_PUBLIC_PROOFBRIDGE_API_BASE_URL` 서버를 사용.
- 문서 규칙, 준비 완료 판정, 상속 서류 심사와 상속 키트는 추가하지 않았다.

현재 카탈로그는 카카오뱅크·우리은행의 한도계좌 해제, KB국민은행의 상속인
금융거래 조회·상속예금 지급으로 구성한다. 카카오뱅크 항목만 기존 문서 분석
화면으로 연결한다. 나머지는 `GUIDE_ONLY`로 공식 안내만 제공한다.
`SUPPORTED`는 기존 분석 흐름으로 연결하는 식별자이며, 외부 분석 서버 배포나
가용성을 보장하는 상태가 아니다.

은행 이름을 아는 것과 해당 은행의 업무를 지원하는 것은 다르다. 예를 들어
우리은행 상속예금을 요청하면 상속 의도와 우리은행을 보존하면서 등록된 조합이
없음을 반환한다. KB국민은행으로 임의 대체하지 않는다.

## 실행

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

## API 계약 v2

입력은 `{ "query": "사용자 표현" }`이며 2~300자, 요청 본문은 4,096바이트 이하다.
출력은 `apps/web/server/task-intent/types.ts`를 정본으로 사용한다.

```json
{
  "schema_version": "2.0",
  "normalized_query": "상속인 금융거래 조회 · 상속예금 지급",
  "resolution": "NEEDS_CONFIRMATION",
  "intent": {
    "services": [
      {"service_id": "inheritance_inquiry", "label_ko": "상속인 금융거래 조회"},
      {"service_id": "inheritance_deposit_payment", "label_ko": "상속예금 지급"}
    ],
    "bank_code": null,
    "bank_label": null
  },
  "selected_task": null,
  "candidates": [],
  "clarification_question": "먼저 하려는 업무와 이용할 은행을 선택해주세요.",
  "reason": "입력하신 상황에서 관련 있는 은행 업무를 찾았어요.",
  "interpretation_method": "llm"
}
```

위 예시는 후보 배열만 생략했다. 실제 `candidates`에는 KB국민은행의 두 업무가
관련 서비스 순서대로 포함되며 각 후보에 `task_id`, `bank_code`, `bank_label`,
`service_id`, `service_label`, `label_ko`, `support_status`, `source_url`,
`source_title`, `last_checked`가 들어간다.

- `RESOLVED`: 은행이 명시되고 한 업무로 해석됨. 사용자 확인 뒤 이동한다.
- `NEEDS_CONFIRMATION`: 은행 미지정, 복수 업무, 모호한 입력 또는 낮은 신뢰도.
- `UNSUPPORTED`: 업무 또는 요청한 은행·업무 조합이 카탈로그에 없음.

은행을 말하지 않았다면 후보가 하나여도 `selected_task`는 `null`이다.
LLM의 자기평가 confidence를 사용자에게 정확도나 유사도 백분율로 표시하지 않는다.
기존 v1의 `lexical_score`, `vector_score`, `embedding_model`은 제거했다.
이 구현은 벡터 검색을 실행하지 않는다.

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
| 부모님이 돌아가셔서 재산을 정리하고 싶음 | 상속 조회·지급 후보, 은행 미정 |
| 아버지가 어느 은행에 돈을 두셨는지 모르겠어요 | 상속인 금융거래 조회, 은행 미정 |
| 국민은행에 있는 돌아가신 아버지 예금을 받고 싶어요 | KB국민은행 · 상속예금 지급, 안내만 |
| 우리은행의 상속예금을 찾고 싶어요 | 상속 의도 유지, 해당 조합 미등록 |
| 우리 아버지가 돌아가셔서 재산을 정리하려고요 | 우리은행으로 오인하지 않음 |
| 카뱅 한도계좌를 해제하고 싶어요 | 카카오뱅크 · 한도제한계좌 해제 |
| 카뱅 송금 한도가 너무 적어요 | 한도제한계좌 여부 추가 확인 |
| 부모님께 미리 재산을 증여받고 싶어요 | 현재 카탈로그 밖 업무 |

새 업무는 `catalog.ts`의 서비스 정의와 공식 출처가 있는 은행·업무 조합을
추가하고 대응 합성 테스트·실제 모델 질의 정답표를 함께 확장한다.

## 출처

업무 카탈로그 확인일: 2026-09-06. 문서 요건의 검증일이나 준비 완료 규칙이 아니다.

- [카카오뱅크 한도계좌 안내](https://blog.kakaobank.com/posts/service-limit-account)
- [우리은행 금융거래 목적 확인 안내](https://spot.wooribank.com/pot/Dream?ARTICLE_ID=46497&BOARD_ID=B00445&bbsMode=view&withyou=CQCNT0009)
- [KB국민은행 상속인 금융거래 조회](https://obank.kbstar.com/quics?page=C033712)
- [KB국민은행 상속예금 안내](https://obank1.kbstar.com/quics?page=C112064)
- [OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs)
- [OpenAI GPT-5.4 mini](https://developers.openai.com/api/docs/models/gpt-5.4-mini)
