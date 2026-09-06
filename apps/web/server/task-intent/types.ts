import type { ServiceId } from "./catalog.ts";

export interface InterpretedIntent {
  service_ids: ServiceId[];
  bank_mention: string | null;
  confidence: number;
  needs_clarification: boolean;
}

export interface TaskResolutionCandidate {
  task_id: string;
  label_ko: string;
  bank_code: string;
  bank_label: string;
  service_id: ServiceId;
  service_label: string;
  support_status: "SUPPORTED" | "GUIDE_ONLY";
  source_url: string;
  source_title: string;
  last_checked: string;
}

export interface TaskResolutionResponse {
  schema_version: "2.0";
  normalized_query: string;
  resolution: "RESOLVED" | "NEEDS_CONFIRMATION" | "UNSUPPORTED";
  intent: {
    services: { service_id: ServiceId; label_ko: string }[];
    bank_code: string | null;
    bank_label: string | null;
  };
  selected_task: TaskResolutionCandidate | null;
  candidates: TaskResolutionCandidate[];
  clarification_question: string | null;
  reason: string;
  interpretation_method: "llm";
}

export class TaskIntentError extends Error {
  code: string;
  status: number;

  constructor(code: string, message: string, status = 502) {
    super(message);
    this.name = "TaskIntentError";
    this.code = code;
    this.status = status;
  }
}
