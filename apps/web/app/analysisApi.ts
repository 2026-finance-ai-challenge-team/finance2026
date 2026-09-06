export type ApiDocumentStatus =
  | "READY"
  | "MISSING"
  | "EXPIRED"
  | "MISMATCH"
  | "UNNECESSARY"
  | "REVIEW_REQUIRED";

export type MetadataStatus = "CONFIRMED" | "INFERRED" | "AMBIGUOUS" | "NOT_FOUND";

export interface ApiMetadataValue<T> {
  value: T | null;
  status: MetadataStatus;
  confidence: number | null;
  source_label?: string | null;
  evidence_block_ids: string[];
}

export interface ApiDocumentMetadata {
  schema_version: "1.0";
  document_type: ApiMetadataValue<string> & {
    candidates: { value: string; name: string | null; confidence: number | null }[];
  };
  document_name: ApiMetadataValue<string>;
  owner_name: ApiMetadataValue<string> & {
    role: "PERSON" | "CORPORATION" | "REPRESENTATIVE" | null;
    candidates: { value: string; role: string; source_label: string | null }[];
  };
  owner_match: {
    status: "MATCH" | "MISMATCH" | "POSSIBLE_MATCH" | "UNKNOWN" | "NOT_CHECKED";
  };
  issued_at: ApiMetadataValue<string> & { candidates: string[] };
  expires_at: ApiMetadataValue<string> & { candidates: string[] };
  needs_review: boolean;
  warnings: string[];
}

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
  metadata: ApiDocumentMetadata | null;
}

export interface ApiTaskSummary {
  task_id: string;
  label_ko: string;
  bank_code: string;
  bank_name_ko: string | null;
  policy_key: string;
  operation_code?: string | null;
  channel: string;
  visitor_type: string;
  purpose_code?: string | null;
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
  bank_name_ko?: string;
  policy_key?: string;
  operation_code?: string | null;
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
  retrieval_methods: ("alias" | "vector" | "llm" | "deterministic")[];
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

export interface ApiTaskRequirementDocument {
  requirement_code: string;
  requirement_level: string;
  choice_group: string | null;
  bundle_code: string | null;
  doc_type: string;
  label_ko: string;
  original_required: boolean | null;
  issued_within_days: number | null;
  submission_method: string;
  submission_label: string;
  notes: string | null;
  acquisition: ApiAcquisitionGuide;
  source: ApiSourceReference;
}

export interface TaskRequirementsResponse {
  schema_version: "1.0";
  task: ApiTaskSummary;
  documents: ApiTaskRequirementDocument[];
  preparations: { code: string; label_ko: string; notes: string | null }[];
  warnings: string[];
}

export interface AnalysisResponse {
  schema_version: "1.0";
  session_id: string;
  task: {
    task_id: string;
    label_ko: string;
    bank_code: string;
    bank_name_ko: string | null;
    policy_key: string;
    operation_code: string | null;
    channel: string;
    visitor_type: string;
    purpose_code: string | null;
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
  options: { ownerName?: string; purposeCode?: string } = {},
): Promise<AnalysisResponse> {
  const form = new FormData();
  form.set("task_id", taskId);
  if (options.ownerName) form.set("owner_name", options.ownerName);
  if (options.purposeCode) form.set("purpose_code", options.purposeCode);
  files.forEach((file) => form.append("files", file, file.name));

  let response: Response;
  try {
    response = await fetch(`${API_BASE}/api/v1/analyze`, {
      method: "POST",
      body: form,
    });
  } catch {
    throw new AnalysisApiError(
      "문서 확인 서비스에 잠시 연결할 수 없어요.",
      "잠시 후 다시 시도해주세요. 계속 문제가 생기면 페이지를 새로고침해주세요.",
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

export async function loadTaskRequirements(
  taskId: string,
  purposeCode?: string,
): Promise<TaskRequirementsResponse> {
  const query = purposeCode ? `?purpose_code=${encodeURIComponent(purposeCode)}` : "";
  let response: Response;
  try {
    response = await fetch(`${API_BASE}/api/v1/tasks/${encodeURIComponent(taskId)}/requirements${query}`, {
      cache: "no-store",
    });
  } catch {
    throw new AnalysisApiError(
      "필요한 서류를 불러오지 못했어요.",
      "잠시 후 다시 시도해주세요.",
    );
  }
  if (!response.ok) throw await apiError(response, "필요한 서류를 불러오지 못했어요.");
  return (await response.json()) as TaskRequirementsResponse;
}

export async function loadDemoAnalysis(): Promise<AnalysisResponse> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}/api/v1/demo`, { method: "POST" });
  } catch {
    throw new AnalysisApiError("예시 결과를 잠시 불러올 수 없어요.", "잠시 후 다시 시도해주세요.");
  }
  if (!response.ok) throw await apiError(response, "예시 결과를 불러오지 못했어요.");
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
      "업무 찾기 서비스 연결이 잠시 지연되고 있어요.",
      "잠시 후 다시 시도해주세요. 계속 문제가 생기면 페이지를 새로고침해주세요.",
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
