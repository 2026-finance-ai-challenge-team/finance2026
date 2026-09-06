import assert from "node:assert/strict";

const base = process.env.PROOFBRIDGE_TEST_BASE_URL ?? "http://127.0.0.1:3000";
const cases = [
  ["부모님이 돌아가셔서 재산을 정리하고 싶음", "NEEDS_CONFIRMATION", null, ["inheritance_inquiry", "inheritance_deposit_payment"]],
  ["돌아가신 아버지가 어느 은행에 돈을 두셨는지 모르겠어요", "NEEDS_CONFIRMATION", null, ["inheritance_inquiry"]],
  ["국민은행에 있는 돌아가신 아버지 예금을 받고 싶어요", "RESOLVED", "kb", ["inheritance_deposit_payment"]],
  ["우리은행의 돌아가신 부모님 예금을 상속받고 싶어요", "UNSUPPORTED", "woori", ["inheritance_deposit_payment"]],
  ["우리 아버지가 돌아가셔서 재산을 정리하려고요", "NEEDS_CONFIRMATION", null, ["inheritance_inquiry", "inheritance_deposit_payment"]],
  ["카뱅 한도계좌를 해제하고 싶어요", "RESOLVED", "kakaobank", ["limit_account_release"]],
  ["카뱅 송금 한도가 너무 적어요", "NEEDS_CONFIRMATION", "kakaobank", ["limit_account_release"]],
  ["부모님께 미리 재산을 증여받고 싶어요", "UNSUPPORTED", null, []],
];

let passed = 0;
for (const [query, resolution, bank, services] of cases) {
  try {
    const response = await fetch(new URL("/api/v1/tasks/resolve", base), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query }),
      signal: AbortSignal.timeout(20000),
    });
    assert.equal(response.status, 200);
    const result = await response.json();
    assert.equal(result.resolution, resolution);
    assert.equal(result.intent.bank_code, bank);
    assert.deepEqual(result.intent.services.map((service) => service.service_id), services);
    if (bank === null) assert.equal(result.selected_task, null);
    passed++;
    console.log(`PASS ${query}`);
  } catch (error) {
    console.error(`FAIL ${query}: ${error.message}`);
  }
}
console.log(`Live intent checks: ${passed}/${cases.length}`);
process.exitCode = passed === cases.length ? 0 : 1;
