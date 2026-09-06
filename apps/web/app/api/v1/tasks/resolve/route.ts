import { resolveQuery, type ResolveInput } from "../../../../../server/task-intent/resolve.ts";
import { TaskIntentError } from "../../../../../server/task-intent/types.ts";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const MAX_BODY_BYTES = 4096;
let activeRequests = 0;
let windowStarted = 0;
let windowRequests = 0;

async function readInput(request: Request): Promise<ResolveInput> {
  if (!request.headers.get("content-type")?.toLowerCase().startsWith("application/json")) {
    throw new TaskIntentError("INVALID_CONTENT_TYPE", "입력 형식을 확인해주세요.", 415);
  }
  const reader = request.body?.getReader();
  if (!reader) throw new TaskIntentError("INVALID_QUERY", "하려는 업무를 적어주세요.", 400);
  let bytes = 0;
  let body = "";
  const decoder = new TextDecoder();
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      bytes += value.byteLength;
      if (bytes > MAX_BODY_BYTES) {
        await reader.cancel();
        throw new TaskIntentError("REQUEST_TOO_LARGE", "입력 내용이 너무 길어요.", 413);
      }
      body += decoder.decode(value, { stream: true });
    }
    body += decoder.decode();
    const payload = JSON.parse(body);
    if (typeof payload !== "object" || payload === null) {
      throw new TaskIntentError("INVALID_JSON", "입력 형식을 확인해주세요.", 400);
    }
    return payload as ResolveInput;
  } catch (error) {
    if (error instanceof TaskIntentError) throw error;
    throw new TaskIntentError("INVALID_JSON", "입력 형식을 확인해주세요.", 400);
  } finally {
    reader.releaseLock();
  }
}

export async function POST(request: Request): Promise<Response> {
  let admitted = false;
  const headers = { "Cache-Control": "no-store" };
  try {
    const input = await readInput(request);
    if (Date.now() - windowStarted >= 60000) {
      windowStarted = Date.now();
      windowRequests = 0;
    }
    if (activeRequests >= 4 || windowRequests >= 30) {
      return Response.json({ error: { code: "RATE_LIMITED", message: "요청이 많아요. 잠시 후 다시 시도해주세요." } }, {
        status: 429, headers: { ...headers, "Retry-After": "60" },
      });
    }
    admitted = true;
    activeRequests += 1;
    windowRequests += 1;
    return Response.json(await resolveQuery(input), { headers });
  } catch (error) {
    const failure = error instanceof TaskIntentError ? error
      : new TaskIntentError("INTENT_UNAVAILABLE", "업무를 찾지 못했어요. 잠시 후 다시 시도해주세요.", 503);
    return Response.json({ error: { code: failure.code, message: failure.message } }, { status: failure.status, headers });
  } finally {
    if (admitted) activeRequests -= 1;
  }
}
