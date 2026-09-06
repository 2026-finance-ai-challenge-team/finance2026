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
import type {
  AnalysisResponse,
  ApiDocumentResult,
  ApiRequirementBundle,
} from "./analysisApi";

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
 * 정적 합성 샘플을 가져온다. API 업로드 UI를 연결할 때 fetch로 교체한다.
 *
 *   const res = await fetch("/api/classify", { method: "POST", body: form });
 *   return (await res.json()) as ClassifyResult;
 */
export function loadResult(): ClassifyResult {
  return sample as unknown as ClassifyResult;
}

/** 현재 정적 데모가 API 규칙 결과를 읽지 않아 표시하지 않는 상태. */
export const NOT_YET_DERIVABLE = ["준비 완료", "정보 불일치"] as const;

export type Tone = "ready" | "expired" | "needed" | "unused" | "mismatch";

export interface DisplayRow {
  key: string;
  name: string;
  meta: string;
  status: string;
  tone: Tone;
  note: string;
}

export const DOC_LABELS: Record<string, string> = {
  utility_bill: "공공요금 고지서·납부확인서",
  management_fee_notice: "관리비 고지서",
  resident_registration_copy: "주민등록표 등본",
  resident_registration_abstract: "주민등록표 초본",
  family_relation_certificate: "가족관계증명서",
  health_insurance_certificate: "건강보험 자격득실 확인서",
  income_certificate: "소득금액증명",
  tax_bill: "세금 고지서",
  employment_contract: "근로계약서",
  business_registration_certificate: "사업자등록증",
  mobile_phone_payment_certificate: "휴대폰 요금 납부확인서",
};

export const DOCUMENT_TYPE_OPTIONS = Object.entries(DOC_LABELS).map(
  ([docType, label]) => ({ docType, label }),
);

function apiDocumentRow(doc: ApiDocumentResult): DisplayRow {
  const base = {
    key: doc.document_id,
    name: doc.label_ko ?? doc.source_name,
    meta: `${doc.source_name} · 분류 신뢰도 ${Math.round(doc.confidence * 100)}%`,
  };
  switch (doc.status) {
    case "READY":
      return { ...base, status: "준비 완료", tone: "ready", note: "공개 기준에서 사용할 수 있는 문서로 확인했어요." };
    case "EXPIRED":
      return { ...base, status: "기한 만료", tone: "expired", note: "발급일 또는 인정기간을 다시 확인하고 새로 준비해주세요." };
    case "MISMATCH":
      return { ...base, status: "정보 불일치", tone: "mismatch", note: "다른 문서의 핵심 정보와 달라 확인이 필요해요." };
    case "UNNECESSARY":
      return {
        ...base,
        status: "이번 업무에는 불필요",
        tone: "unused",
        note: doc.reason_code === "CLEARLY_UNRELATED_DOCUMENT"
          ? "내용을 확인했지만 선택한 업무의 인정 서류가 아니어서 제출 묶음에서 제외해요."
          : "문서 종류는 확인했지만 이번 업무의 인정 서류가 아니어서 제출 묶음에서 제외해요.",
      };
    case "MISSING":
      return { ...base, status: "추가 필요", tone: "needed", note: "이번 업무에 필요한 문서를 찾지 못했어요." };
    case "REVIEW_REQUIRED":
    default:
      return {
        ...base,
        status: "확인 필요",
        tone: "needed",
        note: doc.reason_code === "UNVERIFIED_DOCUMENT_SIGNATURE"
          ? "문서 종류는 찾았지만 실제 양식 표본 검증 전이라 한 번 더 확인해야 해요."
          : doc.reason_code === "AI_CLASSIFICATION_NEEDS_CONFIRMATION"
            ? "AI가 문서 종류를 제안했습니다. 아래에서 맞는지 확인해주세요."
            : doc.reason_code === "USER_CONFIRMED_DOCUMENT_TYPE"
              ? "문서 종류를 확인했습니다. 진위·발급일·내용은 원문 확인이 필요해요."
              : "자동 판정을 확정하기 어려워 사용자의 확인이 필요해요.",
      };
  }
}

function closestBundle(bundles: ApiRequirementBundle[]): ApiRequirementBundle | undefined {
  return [...bundles].sort((a, b) => {
    const specialRank = (bundle: ApiRequirementBundle) =>
      bundle.status === "MISMATCH" ? -2 : bundle.status === "REVIEW_REQUIRED" ? -1 : 0;
    return (
      specialRank(a) - specialRank(b)
      || b.evidence_document_ids.length - a.evidence_document_ids.length
      || a.missing_document_types.length - b.missing_document_types.length
    );
  })[0];
}

export function toUploadedDocumentRows(result: AnalysisResponse): DisplayRow[] {
  return result.documents.map(apiDocumentRow);
}

export function toRequirementRows(result: AnalysisResponse): DisplayRow[] {
  const rows: DisplayRow[] = [];
  result.requirements.forEach((requirement) => {
    const bundle = requirement.matched_bundle_code
      ? requirement.bundles.find((item) => item.bundle_code === requirement.matched_bundle_code)
      : closestBundle(requirement.bundles);
    if (!bundle) {
      if (requirement.status === "MISSING") {
        const docType = requirement.requirement_id || requirement.label_ko;
        rows.push({
          key: `api-missing-${docType}`,
          name: DOC_LABELS[docType] ?? DOC_LABELS[requirement.label_ko] ?? requirement.label_ko,
          meta: "필수 조합 · 아직 없음",
          status: "추가 필요",
          tone: "needed",
          note: "이 문서를 보완하면 현재 가장 가까운 제출 조합을 이어서 확인할 수 있어요.",
        });
      }
      return;
    }

    bundle.missing_document_types.forEach((docType) => {
      rows.push({
        key: `api-missing-${requirement.requirement_id}-${docType}`,
        name: DOC_LABELS[docType] ?? docType,
        meta: `${bundle.label_ko} · 아직 없음`,
        status: "추가 필요",
        tone: "needed",
        note: "이 문서를 보완하면 선택한 제출 조합을 완성할 수 있어요.",
      });
    });
    if (requirement.status === "MISMATCH") {
      rows.push({
        key: `api-mismatch-${requirement.requirement_id}`,
        name: "문서 정보 교차 확인",
        meta: bundle.label_ko,
        status: "정보 불일치",
        tone: "mismatch",
        note: "명의·주소 또는 법인명이 서로 다릅니다. 원문을 확인해주세요.",
      });
    }
  });
  return rows;
}

export function toApiRows(result: AnalysisResponse): DisplayRow[] {
  return [
    ...toUploadedDocumentRows(result),
    ...toRequirementRows(result),
  ];
}

export function analysisHeadline(result: AnalysisResponse, rows: DisplayRow[]): string {
  if (result.overall_status === "READY") return "공개 기준 사전 점검이 끝났어요.";
  if (rows.some((row) => row.tone === "mismatch")) return "문서 정보가 서로 달라요.";
  const missing = rows.filter((row) => row.status === "추가 필요");
  if (missing.length) {
    const name = `${missing[0].name}${missing.length > 1 ? ` 외 ${missing.length - 1}건` : ""}`;
    const last = name.charCodeAt(name.length - 1);
    const hasFinalConsonant = last >= 0xac00 && last <= 0xd7a3 && (last - 0xac00) % 28 !== 0;
    return `${name}${hasFinalConsonant ? "이" : "가"} 더 필요해요.`;
  }
  return "문서는 찾았지만 확인이 필요해요.";
}

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
 * **`준비 완료`는 만들지 않는다.** 이 변환기는 문서 분류 결과만 취급하며,
 * 최종 판정은 FastAPI에 연결된 PostgreSQL 정책 규칙의 결과를 사용해야 한다.
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
