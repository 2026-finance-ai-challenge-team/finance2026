import assert from "node:assert/strict";

const base = process.env.PROOFBRIDGE_TEST_BASE_URL ?? "http://127.0.0.1:3000";

// [질의, 기대 resolution, 기대 bank_code, 기대 operation_id, 버튼 축]
const cases = [
  ["우리은행에서 아이 인터넷뱅킹 만들어주려고요", "RESOLVED", "WOORI", "woori.minor_internet_banking_registration", null],
  ["국민은행 한도계좌 좀 풀고 싶어요", "NEEDS_CONFIRMATION", "KB_KOOKMIN", "kb.limited_account_release", "purpose_code"],
  ["하나은행에서 법인 통장 만들려고요", "NEEDS_CONFIRMATION", "KEB_HANA", "hana.corporate_account_opening", "channel"],
  ["카카오뱅크 한도계좌 해제하고 싶어요", "RESOLVED", "KAKAO_BANK", "kakaobank.limit_account_release", null],
  ["신한은행 예금잔액증명서 떼려고요", "RESOLVED", "SHINHAN", "shinhan.balance_certificate_issuance", null],
  ["부모님이 돌아가셔서 재산을 정리하고 싶어요", "NEEDS_CONFIRMATION", null, null, null],
  ["우리 아버지가 돌아가셔서 재산 정리하려고요", "NEEDS_CONFIRMATION", null, null, null],
  ["부모님께 재산을 미리 증여받고 싶어요", "UNSUPPORTED", null, null, null],
];

const post = (body) => fetch(new URL("/api/v1/tasks/resolve", base), {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
  signal: AbortSignal.timeout(20000),
});

let passed = 0;
for (const [query, resolution, bank, operationId, axis] of cases) {
  try {
    const response = await post({ query });
    assert.equal(response.status, 200);
    const result = await response.json();
    assert.equal(result.resolution, resolution);
    if (bank !== null) assert.equal(result.intent.bank_code, bank);
    if (operationId !== null) assert.equal(result.intent.operation_id, operationId);
    assert.equal(result.pending_choice?.axis ?? null, axis);
    // A confirmed bank plus no pending question must produce documents; nothing else may.
    if (result.resolution === "RESOLVED") assert.ok(result.requirements.length > 0);
    else assert.deepEqual(result.requirements, []);
    passed++;
    console.log(`PASS ${query}`);
  } catch (error) {
    console.error(`FAIL ${query}: ${error.message}`);
  }
}

// 버튼을 눌렀을 때 서류가 나오는지 (모델 호출 없음)
try {
  const response = await post({
    operation_id: "kb.limited_account_release",
    selections: { purpose_code: "salary" },
  });
  const result = await response.json();
  assert.equal(result.resolution, "RESOLVED");
  assert.equal(result.interpretation_method, "selection");
  assert.ok(result.requirements.some((set) => set.document_groups.length > 0));
  passed++;
  console.log("PASS 버튼 선택 후 서류 목록");
} catch (error) {
  console.error(`FAIL 버튼 선택 후 서류 목록: ${error.message}`);
}

const total = cases.length + 1;
console.log(`Live intent checks: ${passed}/${total}`);
process.exitCode = passed === total ? 0 : 1;
