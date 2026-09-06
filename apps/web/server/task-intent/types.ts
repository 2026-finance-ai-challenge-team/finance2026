import type { Operation, RequirementSet } from "./catalog.ts";

export type ChoiceAxis = "channel" | "visitor_type" | "purpose_code";

export interface InterpretedIntent {
  operation_id: string | null;
  bank_mention: string | null;
  channel_hint: string | null;
  visitor_hint: string | null;
  purpose_hint: string | null;
  confidence: number;
  needs_clarification: boolean;
}

export interface OperationCandidate {
  operation_id: string;
  label_ko: string;
  operation_label_ko: string;
  bank_code: string;
  bank_slug: string;
  bank_label_ko: string;
  customer_type: string;
  /** draft rows are still being confirmed against the official page. */
  confirmation_status: "CONFIRMED" | "IN_REVIEW";
  verified_at: string;
}

export interface ChoiceOption {
  value: string;
  label_ko: string;
  description: string | null;
}

export interface PendingChoice {
  axis: ChoiceAxis;
  question: string;
  options: ChoiceOption[];
}

export interface RequirementDocumentView {
  doc_type: string;
  label_ko: string;
  issuer: string | null;
  submission_method: string;
  submission_label_ko: string;
  issued_within_days: number | null;
  validity_note: string | null;
  choice_group: string | null;
  notes: string | null;
}

export interface RequirementView {
  requirement_code: string;
  requirement_level: string;
  level_label_ko: string;
  channel: string;
  channel_label_ko: string;
  visitor_type: string;
  visitor_label_ko: string;
  purpose_code: string | null;
  purpose_label_ko: string | null;
  eligibility_notes: string | null;
  notes: string | null;
  /** Documents the user may choose between, grouped by choice_group. */
  document_groups: { choice_group: string | null; documents: RequirementDocumentView[] }[];
  preparations: { code: string; label_ko: string; notes: string | null }[];
  source: { publisher: string; title: string; url: string; checked_at: string };
}

export interface TaskResolutionResponse {
  schema_version: "3.0";
  normalized_query: string;
  resolution: "RESOLVED" | "NEEDS_CONFIRMATION" | "UNSUPPORTED";
  intent: {
    bank_code: string | null;
    bank_label: string | null;
    operation_id: string | null;
  };
  selected_operation: OperationCandidate | null;
  candidates: OperationCandidate[];
  pending_choice: PendingChoice | null;
  selections: { channel: string | null; visitor_type: string | null; purpose_code: string | null };
  requirements: RequirementView[];
  clarification_question: string | null;
  reason: string;
  interpretation_method: "llm" | "selection";
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

export type { Operation, RequirementSet };
