import assert from "node:assert/strict";
import test from "node:test";
import { POST } from "../app/api/v1/tasks/resolve/route.ts";
import { TASK_CATALOG } from "../server/task-intent/catalog.ts";
import { interpretQuery, redactQuery, validateIntent } from "../server/task-intent/interpret.ts";
import { resolveQuery } from "../server/task-intent/resolve.ts";
import { TaskIntentError, type InterpretedIntent } from "../server/task-intent/types.ts";

const inheritance: InterpretedIntent = {
  service_ids: ["inheritance_inquiry", "inheritance_deposit_payment"],
  bank_mention: null,
  confidence: 0.92,
  needs_clarification: true,
};
const payment: InterpretedIntent = {
  service_ids: ["inheritance_deposit_payment"],
  bank_mention: "국민은행",
  confidence: 0.95,
  needs_clarification: false,
};

function modelResponse(intent: unknown) {
  return Response.json({ status: "completed", output: [{ type: "message", content: [{ type: "output_text", text: JSON.stringify(intent) }] }] });
}

test("parent death and estate intent yields two services without inventing a bank", async () => {
  const result = await resolveQuery("부모님이 돌아가셔서 재산을 정리하고 싶음", async () => inheritance);
  assert.equal(result.resolution, "NEEDS_CONFIRMATION");
  assert.equal(result.intent.bank_code, null);
  assert.equal(result.selected_task, null);
  assert.deepEqual(result.candidates.map((task) => task.task_id), ["kb.inheritance_inquiry", "kb.inheritance_deposit_payment"]);
  assert.ok(result.candidates.every((task) => task.support_status === "GUIDE_ONLY"));
  assert.match(result.clarification_question!, /은행/);
});

test("explicit bank and service resolve to a catalog pair and official source", async () => {
  const result = await resolveQuery("국민은행의 돌아가신 아버지 예금을 받고 싶어요", async () => payment);
  assert.equal(result.resolution, "RESOLVED");
  assert.equal(result.selected_task?.task_id, "kb.inheritance_deposit_payment");
  assert.equal(result.selected_task?.support_status, "GUIDE_ONLY");
  assert.equal(result.selected_task?.source_url, TASK_CATALOG.find((task) => task.task_id === "kb.inheritance_deposit_payment")?.source_url);
});

test("the same service at an unlisted bank is not replaced with KB", async () => {
  const result = await resolveQuery("우리은행에 남은 부모님 예금을 상속받고 싶어요", async () => ({ ...payment, bank_mention: "우리은행" }));
  assert.equal(result.resolution, "UNSUPPORTED");
  assert.equal(result.intent.bank_code, "woori");
  assert.equal(result.intent.services[0].service_id, "inheritance_deposit_payment");
  assert.deepEqual(result.candidates, []);
});

test("an unknown bank mention is preserved rather than mapped to a known bank", async () => {
  const result = await resolveQuery("가상은행의 상속예금을 찾고 싶어요", async () => ({ ...payment, bank_mention: "가상은행" }));
  assert.equal(result.intent.bank_label, "가상은행");
  assert.equal(result.intent.bank_code, null);
  assert.deepEqual(result.candidates, []);
});

test("우리 아버지 is not treated as 우리은행", async () => {
  const result = await resolveQuery("우리 아버지가 돌아가셔서 재산을 정리하려고요", async () => inheritance);
  assert.equal(result.intent.bank_code, null);
  assert.equal(result.selected_task, null);
});

test("a bank invented by the model is rejected", async () => {
  await assert.rejects(resolveQuery("부모님 예금을 찾고 싶어요", async () => payment), { code: "UNGROUNDED_BANK" });
});

test("a precise KakaoBank request keeps the existing analysis task id", async () => {
  const result = await resolveQuery("카뱅 한도계좌 해제", async () => ({ ...payment, bank_mention: "카뱅", service_ids: ["limit_account_release"] }));
  assert.equal(result.selected_task?.task_id, "kakaobank.limit_account_release");
  assert.equal(result.selected_task?.support_status, "SUPPORTED");
});

test("missing bank never silently selects the only supported analysis task", async () => {
  const result = await resolveQuery("한도계좌 해제", async () => ({ ...payment, bank_mention: null, service_ids: ["limit_account_release"] }));
  assert.equal(result.selected_task, null);
  assert.equal(result.resolution, "NEEDS_CONFIRMATION");
  assert.ok(result.candidates.some((task) => task.bank_code === "woori"));
});

test("ambiguous transfer limits and low confidence require confirmation", async () => {
  for (const overrides of [{ needs_clarification: true }, { confidence: 0.4 }]) {
    const result = await resolveQuery("카뱅 송금 한도가 너무 적어요", async () => ({ ...payment, service_ids: ["limit_account_release"], bank_mention: "카뱅", ...overrides }));
    assert.equal(result.resolution, "NEEDS_CONFIRMATION");
    assert.equal(result.selected_task, null);
  }
});

test("unrelated requests and services outside the catalog are not forced to a match", async () => {
  const result = await resolveQuery("상속세 신고를 하고 싶어요", async () => ({ ...inheritance, service_ids: [] }));
  assert.equal(result.resolution, "UNSUPPORTED");
  assert.deepEqual(result.candidates, []);
});

test("invalid inputs are rejected before the model is called", async () => {
  let calls = 0;
  for (const value of [null, 123, {}, " ", "가", "가".repeat(301)]) {
    await assert.rejects(resolveQuery(value, async () => { calls++; return inheritance; }), { code: "INVALID_QUERY", status: 400 });
  }
  assert.equal(calls, 0);
});

test("model output cannot inject a service, source, status, or invalid confidence", () => {
  for (const value of [
    { ...payment, service_ids: ["approve_all"] },
    { ...payment, support_status: "SUPPORTED" },
    { ...payment, source_url: "https://example.com" },
    { ...payment, confidence: NaN },
    { ...payment, confidence: 1.1 },
    { ...payment, needs_clarification: "false" },
    { ...payment, bank_mention: "" },
  ]) assert.throws(() => validateIntent(value), TaskIntentError);
});

test("identifier-like numbers and emails are removed before external transmission", async () => {
  const input = "국민은행 상속예금, 주민번호 900101-1234567, 전화 010-1234-5678, 계좌 123456789012, 연락 test@example.com";
  let sent = "";
  await interpretQuery(input, {
    apiKey: "synthetic-test-key",
    fetcher: async (url, init) => {
      assert.equal(url, "https://api.openai.com/v1/responses");
      sent = String(init?.body);
      const body = JSON.parse(sent);
      assert.equal(body.store, false);
      assert.equal(body.text.format.strict, true);
      assert.equal(body.text.format.type, "json_schema");
      assert.equal(body.input[0].role, "user");
      return modelResponse(payment);
    },
  });
  assert.doesNotMatch(sent, /900101|1234567|010-1234|123456789012|test@example/);
  assert.match(sent, /국민은행 상속예금/);
  assert.match(redactQuery(input), /\[식별번호\]/);
});

test("no API key means an explicit unavailable error, not a fake interpretation", async () => {
  await assert.rejects(interpretQuery("상속예금", { apiKey: "" }), { code: "INTENT_NOT_CONFIGURED", status: 503 });
});

test("upstream refusal, incomplete output, malformed JSON, and outages fail closed", async () => {
  const fetchers: typeof fetch[] = [
    async () => Response.json({ status: "completed", output: [{ type: "message", content: [{ type: "refusal", refusal: "refused" }] }] }),
    async () => Response.json({ status: "incomplete", output: [] }),
    async () => new Response("not JSON"),
    async () => new Response("sensitive upstream error", { status: 429 }),
    async () => { throw new Error("synthetic network error"); },
  ];
  for (const fetcher of fetchers) {
    await assert.rejects(interpretQuery("상속예금", { apiKey: "synthetic-test-key", fetcher }), (error: unknown) => {
      assert.ok(error instanceof TaskIntentError);
      assert.doesNotMatch(error.message, /sensitive|synthetic|key/);
      return true;
    });
  }
});

test("HTTP endpoint validates content type, malformed JSON, and byte limits", async () => {
  for (const [body, contentType, status] of [
    [JSON.stringify({ query: "카뱅 한도계좌" }), "text/plain", 415],
    ["{", "application/json", 400],
    [JSON.stringify({ query: "가".repeat(2000) }), "application/json", 413],
    [JSON.stringify({ query: "" }), "application/json", 400],
  ] as const) {
    const response = await POST(new Request("http://localhost/api/v1/tasks/resolve", { method: "POST", headers: { "Content-Type": contentType }, body }));
    assert.equal(response.status, status);
    assert.equal(response.headers.get("cache-control"), "no-store");
  }
});

test("HTTP integration returns the interpreted bank and service, with no original input echo", async () => {
  const originalFetch = globalThis.fetch;
  const originalKey = process.env.OPENAI_API_KEY;
  try {
    process.env.OPENAI_API_KEY = "synthetic-test-key";
    globalThis.fetch = async () => modelResponse(payment);
    const response = await POST(new Request("http://localhost/api/v1/tasks/resolve", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ query: "국민은행의 돌아가신 아버지 예금을 받고 싶어요" }),
    }));
    assert.equal(response.status, 200);
    const result = await response.json();
    assert.equal(result.selected_task.bank_label, "KB국민은행");
    assert.equal(result.selected_task.service_label, "상속예금 지급");
    assert.equal(result.query, undefined);
  } finally {
    globalThis.fetch = originalFetch;
    if (originalKey === undefined) delete process.env.OPENAI_API_KEY;
    else process.env.OPENAI_API_KEY = originalKey;
  }
});
