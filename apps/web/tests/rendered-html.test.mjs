import assert from "node:assert/strict";
import test from "node:test";

async function render() {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);

  return worker.fetch(
    new Request("https://proofbridge.example/", {
      headers: { accept: "text/html", "x-forwarded-host": "proofbridge.example", "x-forwarded-proto": "https" },
    }),
    { ASSETS: { fetch: async () => new Response("Not found", { status: 404 }) } },
    { waitUntil() {}, passThroughOnException() {} },
  );
}

test("renders the ProofBridge demo and its safety boundary", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);

  const html = await response.text();
  assert.match(html, /<title>ProofBridge \| 금융업무 준비 데모<\/title>/);
  assert.match(html, /공공 마이데이터 위의 금융업무 완성 계층/);
  assert.match(html, /합성 샘플/);
  assert.match(html, /AI 분석과 실제 전송은 연결하지 않았습니다/);
  assert.match(html, /property="og:image" content="https:\/\/proofbridge\.example\/og\.png"/);
  assert.doesNotMatch(html, /Starter Project|react-loading-skeleton|세계 최초/);
});
