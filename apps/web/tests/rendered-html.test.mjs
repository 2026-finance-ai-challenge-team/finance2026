import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

async function render() {
  return readFile(new URL("../.next/server/app/index.html", import.meta.url), "utf8");
}

test("renders the ProofBridge service flow without internal implementation copy", async () => {
  const html = await render();
  assert.match(html, /<title>ProofBridge \| 금융업무 증빙 사전점검<\/title>/);
  assert.match(html, /하려는 금융업무를/);
  assert.match(html, /모르면 그냥 다 넣으세요/);
  assert.match(html, /예시로 먼저 체험하기/);
  assert.match(html, /현재 지원 업무/);
  assert.match(html, /카카오뱅크 한도계좌 해제/);
  assert.match(html, /카뱅 한도계좌/);
  assert.match(html, /신한 한도계좌 풀기/);
  assert.match(html, /국민은행 잔액증명서 발급/);
  assert.match(html, /은행과 업무를 함께 확인/);
  assert.match(html, /AI는 등록된 업무 안에서만 찾아요/);
  assert.match(html, /AI는 등록된 업무 안에서만 찾아요/);
  assert.match(html, /비회원 · 즉시 삭제/);
  assert.match(html, /property="og:image" content="[^"]+\/og\.png"/);
  assert.doesNotMatch(html, /Starter Project|react-loading-skeleton|세계 최초|BANKING TASK COMPLETION LAYER|현재 MVP 지원 범위|별칭·벡터|RAG는|FastAPI/);
});
