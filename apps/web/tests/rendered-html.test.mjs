import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

async function render() {
  return readFile(new URL("../.next/server/app/index.html", import.meta.url), "utf8");
}

test("renders the ProofBridge intent finder and its support boundary", async () => {
  const html = await render();
  assert.match(html, /<title>ProofBridge \| 금융업무 증빙 사전점검<\/title>/);
  assert.match(html, /하려는 금융업무를/);
  assert.match(html, /모르면 그냥 다 넣으세요/);
  assert.match(html, /합성 샘플로 바로 체험/);
  assert.match(html, /현재 MVP 지원 범위/);
  assert.match(html, /지원하지 않는 업무를 가능한 것처럼 안내하지 않습니다/);
  assert.match(html, /카카오뱅크 한도계좌 해제/);
  assert.match(html, /카뱅 한도계좌/);
  assert.match(html, /부모님이 돌아가셔서 재산을 정리하고 싶어요/);
  assert.match(html, /상속인 금융거래 조회/);
  assert.match(html, /상속 서류의 자동 점검과 준비 키트는 아직 제공하지 않습니다/);
  assert.match(html, /property="og:image" content="[^"]+\/og\.png"/);
  assert.doesNotMatch(html, /Starter Project|react-loading-skeleton|세계 최초/);
});
