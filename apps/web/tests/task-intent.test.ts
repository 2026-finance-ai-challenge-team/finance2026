import assert from "node:assert/strict";
import { test } from "node:test";

import { OPERATIONS, findOperation, requirementSetsOf } from "../server/task-intent/catalog.ts";
import { redactQuery, validateIntent } from "../server/task-intent/interpret.ts";
import { resolveQuery } from "../server/task-intent/resolve.ts";
import { TaskIntentError, type InterpretedIntent } from "../server/task-intent/types.ts";

const intent = (values: Partial<InterpretedIntent> = {}): InterpretedIntent => ({
  operation_id: null,
  bank_mention: null,
  channel_hint: null,
  visitor_hint: null,
  purpose_hint: null,
  confidence: 0.95,
  needs_clarification: false,
  ...values,
});

const model = (values: Partial<InterpretedIntent> = {}) => async () => intent(values);

test("카탈로그는 데이터베이스 덤프에서 생성된다", () => {
  assert.ok(OPERATIONS.length > 40);
  assert.ok(OPERATIONS.every((operation) => operation.operation_id.includes(".")));
  assert.equal(new Set(OPERATIONS.map((item) => item.operation_id)).size, OPERATIONS.length);
  // Every operation must reach at least one requirement set, or the flow dead-ends.
  for (const operation of OPERATIONS) {
    assert.ok(requirementSetsOf(operation).length > 0, operation.operation_id);
  }
});

test("은행과 업무가 확정되면 서류 목록을 낸다", async () => {
  const result = await resolveQuery(
    { query: "우리은행에서 아이 인터넷뱅킹 만들어주려고요" },
    model({ operation_id: "woori.minor_internet_banking_registration", bank_mention: "우리은행" }),
  );
  assert.equal(result.resolution, "RESOLVED");
  assert.equal(result.intent.bank_code, "WOORI");
  assert.equal(result.pending_choice, null);
  const documents = result.requirements.flatMap((set) => set.document_groups.flatMap((group) => group.documents));
  assert.ok(documents.some((document) => document.doc_type === "family_relation_certificate"));
  assert.ok(result.requirements.every((set) => set.source.url.startsWith("https://")));
});

test("서류가 갈리는 업무는 버튼으로 먼저 묻는다", async () => {
  const asked = await resolveQuery(
    { query: "국민은행 한도계좌 풀고 싶어요" },
    model({ operation_id: "kb.limited_account_release", bank_mention: "국민은행" }),
  );
  assert.equal(asked.resolution, "NEEDS_CONFIRMATION");
  assert.equal(asked.pending_choice?.axis, "purpose_code");
  assert.ok((asked.pending_choice?.options.length ?? 0) > 1);
  assert.deepEqual(asked.requirements, []);

  const answered = await resolveQuery({
    operation_id: "kb.limited_account_release",
    selections: { purpose_code: asked.pending_choice!.options[0].value },
  });
  assert.equal(answered.resolution, "RESOLVED");
  assert.equal(answered.interpretation_method, "selection");
  assert.ok(answered.requirements.length > 0);
});

test("채널과 방문자를 모두 물어야 하는 업무", async () => {
  const first = await resolveQuery(
    { query: "하나은행에서 법인 통장 만들려고요" },
    model({ operation_id: "hana.corporate_account_opening", bank_mention: "하나은행" }),
  );
  assert.equal(first.pending_choice?.axis, "channel");

  const second = await resolveQuery({
    operation_id: "hana.corporate_account_opening",
    selections: { channel: "branch" },
  });
  assert.equal(second.pending_choice?.axis, "visitor_type");

  const third = await resolveQuery({
    operation_id: "hana.corporate_account_opening",
    selections: { channel: "branch", visitor_type: "agent" },
  });
  assert.equal(third.resolution, "RESOLVED");
  assert.ok(third.requirements.some((set) => set.visitor_type === "agent"));
});

test("은행을 말하지 않으면 서류를 내지 않고 은행부터 확인한다", async () => {
  const result = await resolveQuery(
    { query: "부모님이 돌아가셔서 재산 정리하려고요" },
    model({ operation_id: "shinhan.inheritance_deposit_claim", needs_clarification: true, confidence: 0.6 }),
  );
  assert.equal(result.resolution, "NEEDS_CONFIRMATION");
  assert.deepEqual(result.requirements, []);
  // The same work at other banks must be offered instead of guessing one.
  assert.ok(result.candidates.length > 1);
  assert.ok(result.candidates.every((candidate) => candidate.operation_id.endsWith("inheritance_deposit_claim")));
});

test("등록되지 않은 은행·업무 조합은 은행을 바꿔치기하지 않는다", async () => {
  const result = await resolveQuery(
    { query: "카카오뱅크에서 법인 통장 만들려고요" },
    model({ operation_id: "hana.corporate_account_opening", bank_mention: "카카오뱅크" }),
  );
  assert.equal(result.resolution, "UNSUPPORTED");
  assert.equal(result.intent.bank_code, "KAKAO_BANK");
  assert.equal(result.selected_operation, null);
  assert.deepEqual(result.requirements, []);
});

test("같은 업무는 사용자가 말한 은행으로 옮긴다", async () => {
  const result = await resolveQuery(
    { query: "신한은행 한도계좌 일반계좌로 바꾸고 싶어요" },
    model({ operation_id: "ibk.limit_account_release", bank_mention: "신한은행" }),
  );
  assert.equal(result.intent.bank_code, "SHINHAN");
  assert.equal(result.selected_operation?.bank_slug, "shinhan");
});

test("업무를 찾지 못하면 지어내지 않는다", async () => {
  const result = await resolveQuery({ query: "부모님께 재산을 미리 증여받고 싶어요" }, model());
  assert.equal(result.resolution, "UNSUPPORTED");
  assert.equal(result.selected_operation, null);
  assert.deepEqual(result.requirements, []);
});

test("원문에 없는 은행 언급은 거부한다", async () => {
  await assert.rejects(
    () => resolveQuery(
      { query: "돌아가신 아버지 예금을 찾고 싶어요" },
      model({ operation_id: "shinhan.inheritance_deposit_claim", bank_mention: "신한은행" }),
    ),
    (error: TaskIntentError) => error.code === "UNGROUNDED_BANK",
  );
});

test("'우리 아버지'를 우리은행으로 읽지 않는다", async () => {
  const result = await resolveQuery(
    { query: "우리 아버지가 돌아가셔서 재산 정리하려고요" },
    model({ operation_id: "shinhan.inheritance_deposit_claim", needs_clarification: true, confidence: 0.6 }),
  );
  assert.notEqual(result.intent.bank_code, "WOORI");
  assert.deepEqual(result.requirements, []);
});

test("모델이 낸 선택값도 카탈로그에 있어야 반영한다", async () => {
  const result = await resolveQuery(
    { query: "하나은행 영업점 가서 법인 통장 만들 거예요" },
    model({
      operation_id: "hana.corporate_account_opening",
      bank_mention: "하나은행",
      channel_hint: "branch",
      visitor_hint: "account_holder", // 이 업무에는 없는 값이라 무시되어야 한다
    }),
  );
  assert.equal(result.selections.channel, "branch");
  assert.equal(result.selections.visitor_type, null);
  assert.equal(result.pending_choice?.axis, "visitor_type");
});

test("선택한 업무가 카탈로그에 없으면 400", async () => {
  await assert.rejects(
    () => resolveQuery({ operation_id: "nowhere.nothing" }),
    (error: TaskIntentError) => error.code === "UNKNOWN_OPERATION" && error.status === 400,
  );
});

test("입력 길이를 검증한다", async () => {
  for (const query of ["", "가", "가".repeat(301), 42, null]) {
    await assert.rejects(
      () => resolveQuery({ query }, model()),
      (error: TaskIntentError) => error.code === "INVALID_QUERY" && error.status === 400,
    );
  }
});

test("숫자와 이메일을 가린다", () => {
  assert.equal(redactQuery("주민번호 900101-1234567 입니다"), "주민번호 [식별번호] 입니다");
  assert.equal(redactQuery("a@b.com 으로 보내주세요"), "[이메일] 으로 보내주세요");
});

test("모델 응답 검증은 목록 밖 값을 막는다", () => {
  assert.throws(() => validateIntent({ ...intent(), operation_id: "made.up" }));
  assert.throws(() => validateIntent({ ...intent(), channel_hint: "carrier_pigeon" }));
  assert.throws(() => validateIntent({ ...intent(), confidence: 2 }));
  assert.throws(() => validateIntent({ ...intent(), extra: true }));
  const valid = validateIntent(intent({ operation_id: findOperation(OPERATIONS[0].operation_id)!.operation_id }));
  assert.equal(valid.operation_id, OPERATIONS[0].operation_id);
});
