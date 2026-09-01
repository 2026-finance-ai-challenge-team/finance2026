export type ApiDocumentStatus =
  | "READY"
  | "MISSING"
  | "EXPIRED"
  | "MISMATCH"
  | "UNNECESSARY"
  | "REVIEW_REQUIRED";

export interface ApiDocumentResult {
  document_id: string;
  source_name: string;
  doc_type: string | null;
  label_ko: string | null;
  confidence: number;
  status: ApiDocumentStatus;
  reason_code: string;
  needs_user_confirm: boolean;
  classification_method: string;
}

export interface ApiTaskSummary {
  task_id: string;
  label_ko: string;
  bank_code: string;
  policy_key: string;
  channel: string;
  visitor_type: string;
  verified: boolean;
  source_url: string | null;
  as_of: string | null;
  last_checked: string | null;
  demo_available: boolean;
}

export type TaskResolutionStatus = "RESOLVED" | "NEEDS_CONFIRMATION" | "UNSUPPORTED";

export interface TaskResolutionCandidate {
  task_id: string;
  label_ko: string;
  bank_code: string;
  support_status: "SUPPORTED" | "GUIDE_ONLY" | "PLANNED";
  confidence: number;
  lexical_score: number;
  vector_score: number;
  matched_aliases: string[];
}

export interface TaskKnowledgeEvidence {
  chunk_id: string;
  title: string;
  excerpt: string;
  source_url: string;
  verified: boolean;
  last_checked: string;
  score: number;
}

export interface TaskResolutionResponse {
  schema_version: "1.0";
  query: string;
  normalized_query: string;
  resolution: TaskResolutionStatus;
  selected_task: TaskResolutionCandidate | null;
  candidates: TaskResolutionCandidate[];
  clarification_question: string | null;
  reason: string;
  evidence: TaskKnowledgeEvidence[];
  retrieval_methods: ("alias" | "vector")[];
  embedding_model: string;
}

export interface ApiRequirementBundle {
  bundle_code: string;
  label_ko: string;
  status: ApiDocumentStatus;
  document_types: string[];
  missing_document_types: string[];
  evidence_document_ids: string[];
}

export interface ApiRequirementResult {
  requirement_id: string;
  label_ko: string;
  status: ApiDocumentStatus;
  blocking: boolean;
  reason_code: string;
  evidence_document_ids: string[];
  matched_bundle_code: string | null;
  bundles: ApiRequirementBundle[];
  source: {
    title: string | null;
    url: string | null;
    as_of: string | null;
    last_checked: string | null;
    verified: boolean;
  };
}

export interface ApiSourceReference {
  title: string | null;
  url: string | null;
  as_of: string | null;
  last_checked: string | null;
  verified: boolean;
}

export interface ApiAcquisitionGuide {
  title: string;
  channel: string;
  description: string;
  steps: string[];
  url: string | null;
  action_label: string | null;
  source: ApiSourceReference;
}

export interface ApiCompletionDocumentGuide {
  doc_type: string;
  label_ko: string;
  status: ApiDocumentStatus;
  reason: string;
  acquisition: ApiAcquisitionGuide;
  submission_method: string;
  submission_label: string;
  checklist: string[];
}

export interface ApiCompletionPlan {
  bundle_code: string;
  bundle_label: string;
  status: ApiDocumentStatus;
  documents: ApiCompletionDocumentGuide[];
  preparations: { code: string; label_ko: string; notes: string | null }[];
  submission: {
    title: string;
    description: string;
    steps: string[];
    url: string | null;
    action_label: string | null;
    expected_review: string | null;
    source: ApiSourceReference;
  };
}

export interface AnalysisResponse {
  schema_version: "1.0";
  session_id: string;
  task: {
    task_id: string;
    label_ko: string;
    bank_code: string;
    policy_key: string;
    channel: string;
    visitor_type: string;
    verified: boolean;
    source_url: string | null;
    as_of: string | null;
    last_checked: string | null;
    demo_available: boolean;
  };
  overall_status: "READY" | "ACTION_REQUIRED" | "REVIEW_REQUIRED";
  checked_at: string;
  documents: ApiDocumentResult[];
  requirements: ApiRequirementResult[];
  completion_plan: ApiCompletionPlan | null;
  warnings: string[];
}

interface ErrorPayload {
  error?: { code?: string; message?: string; recovery?: string | null };
}

const API_BASE = (
  process.env.NEXT_PUBLIC_PROOFBRIDGE_API_BASE_URL ?? "http://127.0.0.1:8000"
).replace(/\/$/, "");

export class AnalysisApiError extends Error {
  recovery: string | null;

  constructor(message: string, recovery: string | null = null) {
    super(message);
    this.name = "AnalysisApiError";
    this.recovery = recovery;
  }
}

async function apiError(response: Response, fallback: string): Promise<AnalysisApiError> {
  const payload = (await response.json().catch(() => ({}))) as ErrorPayload;
  return new AnalysisApiError(payload.error?.message ?? fallback, payload.error?.recovery ?? null);
}

export async function analyzeDocuments(
  files: File[],
  taskId = "kakaobank.limit_account_release",
): Promise<AnalysisResponse> {
  const form = new FormData();
  form.set("task_id", taskId);
  files.forEach((file) => form.append("files", file, file.name));

  let response: Response;
  try {
    response = await fetch(`${API_BASE}/api/v1/analyze`, {
      method: "POST",
      body: form,
    });
  } catch {
    throw new AnalysisApiError(
      "분석 서버에 연결하지 못했어요.",
      "FastAPI가 실행 중인지와 웹의 API 주소 설정을 확인해주세요.",
    );
  }

  if (!response.ok) {
    const payload = (await response.json().catch(() => ({}))) as ErrorPayload;
    throw new AnalysisApiError(
      payload.error?.message ?? "문서를 분석하지 못했어요.",
      payload.error?.recovery ?? "파일 형식과 크기를 확인한 뒤 다시 시도해주세요.",
    );
  }
  return (await response.json()) as AnalysisResponse;
}

export async function loadDemoAnalysis(): Promise<AnalysisResponse> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}/api/v1/demo`, { method: "POST" });
  } catch {
    throw new AnalysisApiError("합성 데모 서버에 연결하지 못했어요.");
  }
  if (!response.ok) throw await apiError(response, "합성 데모를 불러오지 못했어요.");
  return (await response.json()) as AnalysisResponse;
}

export async function listAnalysisTasks(): Promise<ApiTaskSummary[]> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}/api/v1/tasks`, { cache: "no-store" });
  } catch {
    throw new AnalysisApiError("지원 업무 목록을 불러오지 못했어요.");
  }
  if (!response.ok) throw await apiError(response, "지원 업무 목록을 불러오지 못했어요.");
  return (await response.json()) as ApiTaskSummary[];
}

export async function resolveTask(query: string): Promise<TaskResolutionResponse> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}/api/v1/tasks/resolve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query }),
    });
  } catch {
    throw new AnalysisApiError(
      "업무를 찾는 서버에 연결하지 못했어요.",
      "FastAPI가 실행 중인지 확인한 뒤 다시 시도해주세요.",
    );
  }
  if (!response.ok) throw await apiError(response, "입력한 업무를 해석하지 못했어요.");
  return (await response.json()) as TaskResolutionResponse;
}

export async function deleteAnalysisSession(sessionId: string): Promise<boolean> {
  try {
    const response = await fetch(`${API_BASE}/api/v1/sessions/${sessionId}`, {
      method: "DELETE",
    });
    if (!response.ok) return false;
    const payload = (await response.json()) as { deleted?: boolean };
    return payload.deleted === true;
  } catch {
    return false;
  }
}

export async function downloadPreparationKit(
  sessionId: string,
): Promise<{ blob: Blob; filename: string }> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}/api/v1/sessions/${sessionId}/preparation-kit`);
  } catch {
    throw new AnalysisApiError(
      "준비 안내 키트를 내려받지 못했어요.",
      "분석 서버 연결을 확인한 뒤 다시 시도해주세요.",
    );
  }
  if (!response.ok) throw await apiError(response, "준비 안내 키트를 만들지 못했어요.");
  const disposition = response.headers.get("content-disposition") ?? "";
  const filename = disposition.match(/filename="?([^";]+)"?/i)?.[1]
    ?? `proofbridge-preparation-kit-${sessionId}.zip`;
  return { blob: await response.blob(), filename };
}

export async function confirmDocumentClassification(
  sessionId: string,
  documentId: string,
  docType: string,
): Promise<AnalysisResponse> {
  let response: Response;
  try {
    response = await fetch(
      `${API_BASE}/api/v1/sessions/${sessionId}/documents/${documentId}/classification`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ doc_type: docType }),
      },
    );
  } catch {
    throw new AnalysisApiError(
      "문서 종류 확인을 저장하지 못했어요.",
      "분석 서버 연결을 확인한 뒤 다시 시도해주세요.",
    );
  }
  if (!response.ok) {
    const payload = (await response.json().catch(() => ({}))) as ErrorPayload;
    throw new AnalysisApiError(
      payload.error?.message ?? "문서 종류 확인을 저장하지 못했어요.",
      payload.error?.recovery ?? "문서 종류를 다시 선택해주세요.",
    );
  }
  return (await response.json()) as AnalysisResponse;
}
