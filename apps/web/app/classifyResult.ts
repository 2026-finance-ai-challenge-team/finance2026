/**
 * 문서 분류 모듈(`modules/doc_classify`)의 출력 계약 — TypeScript 쪽 정의.
 *
 * 정본은 `modules/doc_classify/schema.py` (v1.0)다. 이 파일은 그 모양을 화면이
 * 읽을 수 있게 옮긴 것이며, 필드를 임의로 더하거나 이름을 바꾸지 않는다.
 *
 * 지금은 합성 샘플 JSON을 정적으로 읽는다. 백엔드가 생기면 `loadResult()`만
 * fetch로 바꾸면 되고 화면 코드는 건드리지 않는다.
 */

import sample from "./sample-result.json";

export const SCHEMA_VERSION = "1.0";

export type RelevanceStatus = "관련" | "이번 업무에는 불필요" | "판단 불가";

export interface Evidence {
  kind: string;
  pattern?: string;
  value?: string;
  matched?: number;
  total?: number;
}

export interface ClassifiedDocument {
  file_id: string;
  source_name: string;
  media: { kind: string; pages: number; detected_by?: string };
  text_source: { page: number; method: string; chars: number }[];
  visual_title?: string;
  classification: {
    doc_type: string | null;
    label_ko: string | null;
    confidence: number;
    decided_by: string | null;
    evidence: Evidence[];
    alternatives: { doc_type: string; confidence: number }[];
    unverified_signature?: boolean;
  };
  fields: {
    issuer?: string;
    issued_at?: string;
    issued_at_confident?: boolean;
    doc_number_present?: boolean;
  };
  validity: {
    expires_at: string | null;
    days_left: number | null;
    estimated?: boolean;
    note: string;
  };
  relevance: { status: RelevanceStatus; matched_rule: string | null };
  needs_user_confirm: boolean;
  confirm_reason: string | null;
  ocr_calls: number;
  notes: string[];
}

export interface ClassifyResult {
  schema_version: string;
  task_id: string;
  task_label: string;
  task_verified: boolean;
  checked_at: string;
  ocr_calls_total: number;
  missing: { required: string[]; conditional: string[]; alternatives: string[] };
  documents: ClassifiedDocument[];
}

/**
 * 결과를 가져온다. 백엔드가 생기면 여기만 fetch로 바꾼다.
 *
 *   const res = await fetch("/api/classify", { method: "POST", body: form });
 *   return (await res.json()) as ClassifyResult;
 */
export function loadResult(): ClassifyResult {
  return sample as unknown as ClassifyResult;
}

/** 아직 규칙 엔진이 없어 화면이 만들어낼 수 없는 상태. */
export const NOT_YET_DERIVABLE = ["준비 완료", "정보 불일치"] as const;

export type Tone = "ready" | "expired" | "needed" | "unused";

export interface DisplayRow {
  key: string;
  name: string;
  meta: string;
  status: string;
  tone: Tone;
  note: string;
}

const DOC_LABELS: Record<string, string> = {
  utility_bill: "공공요금 고지서·납부확인서",
  resident_registration_copy: "주민등록표 등본",
  resident_registration_abstract: "주민등록표 초본",
  family_relation_certificate: "가족관계증명서",
  health_insurance_certificate: "건강보험 자격득실 확인서",
  income_certificate: "소득금액증명",
};

function metaOf(doc: ClassifiedDocument): string {
  const parts: string[] = [];
  if (doc.fields.issuer) parts.push(doc.fields.issuer);
  if (doc.fields.issued_at) {
    parts.push(doc.fields.issued_at + (doc.fields.issued_at_confident ? "" : " (추정)"));
  }
  const method = doc.text_source.some((p) => p.method === "ocr") ? "OCR" : "PDF 텍스트";
  parts.push(method);
  return parts.join(" · ");
}

/**
 * 분류 결과 한 건을 화면 표시로 바꾼다.
 *
 * **`준비 완료`는 만들지 않는다.** 그 판정은 규칙 엔진의 몫이고 아직 없다.
 * 여기서 낼 수 있는 건 분류·유효기간·업무 관련성에서 직접 유도되는 것뿐이다.
 */
export function toDisplayRow(doc: ClassifiedDocument): DisplayRow {
  const base = {
    key: doc.file_id,
    name: doc.classification.label_ko ?? doc.source_name,
    meta: metaOf(doc),
  };

  if (doc.relevance.status === "판단 불가") {
    return {
      ...base,
      name: doc.source_name,
      status: "확인 필요",
      tone: "needed",
      note: doc.confirm_reason ?? "무슨 문서인지 확인이 필요해요.",
    };
  }

  if (doc.relevance.status === "이번 업무에는 불필요") {
    return {
      ...base,
      status: "이번 업무에는 불필요",
      tone: "unused",
      note: "이번 묶음에서는 빼둘게요. 다른 업무에서 쓸 수 있어요.",
    };
  }

  const daysLeft = doc.validity.days_left;
  if (daysLeft !== null && daysLeft < 0) {
    return {
      ...base,
      status: "기한 만료",
      tone: "expired",
      note: `${doc.validity.expires_at}에 기한이 지났어요. 다시 발급받아야 해요.`,
    };
  }

  return {
    ...base,
    status: "제출 대상",
    tone: "ready",
    note: doc.validity.expires_at
      ? `${doc.validity.expires_at}까지 쓸 수 있어요. ${doc.validity.note}`
      : "이번 업무에 제출할 문서예요.",
  };
}

/** 아직 없는 서류를 `추가 필요` 행으로 만든다. */
export function missingRows(result: ClassifyResult): DisplayRow[] {
  const buckets: [keyof ClassifyResult["missing"], string][] = [
    ["required", "필수"],
    ["conditional", "조건부"],
    ["alternatives", "대체 가능"],
  ];
  return buckets.flatMap(([bucket, label]) =>
    result.missing[bucket].map((docType) => ({
      key: `missing-${docType}`,
      name: DOC_LABELS[docType] ?? docType,
      meta: `${label} · 아직 없음`,
      status: "추가 필요",
      tone: "needed" as Tone,
      note: "이 문서를 발급받으면 묶음을 이어서 만들 수 있어요.",
    })),
  );
}

export function toRows(result: ClassifyResult): DisplayRow[] {
  return [...result.documents.map(toDisplayRow), ...missingRows(result)];
}

/**
 * 이번 업무에 필요한 항목 중 확보된 비율.
 *
 * 분모는 **이번 업무에 필요한 것**만 센다. `이번 업무에는 불필요`한 문서를 많이
 * 올렸다고 완성도가 떨어지면 안 되고, 반대로 그걸로 완성도가 올라가도 안 된다.
 * `판단 불가`는 필요한지조차 모르는 상태라 분모에 넣되 확보로는 치지 않는다.
 */
export function completionOf(rows: DisplayRow[]): { percent: number; have: number; total: number } {
  const counted = rows.filter((row) => row.tone !== "unused");
  const have = counted.filter((row) => row.tone === "ready").length;
  const total = counted.length;
  return { percent: total ? Math.round((have / total) * 100) : 0, have, total };
}
