import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

async function render() {
  return readFile(new URL("../.next/server/app/index.html", import.meta.url), "utf8");
}

test("renders the FORM:E service flow without internal implementation copy", async () => {
  const html = await render();
  assert.match(html, /<title>FORM:E \| 금융업무 서류 사전점검<\/title>/);
  assert.match(html, /하려는 금융업무를/);
  assert.match(html, /필요한 서류를/);
  assert.match(html, /예시 결과 보기/);
  assert.match(html, /지원 범위/);
  assert.match(html, /카뱅 한도계좌/);
  assert.match(html, /신한 한도계좌 풀기/);
  assert.match(html, /국민은행 잔액증명서 발급/);
  assert.match(html, /은행과 업무를 함께 확인/);
  assert.match(html, /모호한 요청은 먼저 확인해요/);
  assert.match(html, /비회원 · 즉시 삭제/);
  assert.match(html, /property="og:image" content="[^"]+\/og\.png"/);
  assert.doesNotMatch(html, /준비 안내 ZIP 받기|카카오뱅크 공식 안내/);
  assert.doesNotMatch(html, /Starter Project|react-loading-skeleton|세계 최초|BANKING TASK COMPLETION LAYER|현재 MVP 지원 범위|별칭·벡터|RAG는|FastAPI/);
});
