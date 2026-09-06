import {
  BANK_ALIASES, BANKS, OPERATIONS, findOperation, operationLabel, requirementSetsOf,
  type Operation, type RequirementSet,
} from "./catalog.ts";
import { interpretQuery, redactQuery, validateIntent } from "./interpret.ts";
import {
  TaskIntentError,
  type ChoiceAxis, type ChoiceOption, type InterpretedIntent, type OperationCandidate,
  type PendingChoice, type RequirementView, type TaskResolutionResponse,
} from "./types.ts";

const normalize = (value: string) => value.normalize("NFKC").toLocaleLowerCase("en-US").replace(/\s/g, "");

const CHANNEL_LABELS: Record<string, string> = {
  branch: "영업점 방문",
  non_face_to_face: "비대면(앱·인터넷)",
};

// representative means the corporate officer for a company and the legal
// guardian for an individual, so the label depends on the customer type.
function visitorLabel(visitorType: string, customerType: string): string {
  const corporate = customerType === "corporation";
  switch (visitorType) {
    case "account_holder": return "본인이 직접";
    case "representative": return corporate ? "법인 대표자" : "법정대리인(부모 등)";
    case "agent": return "대리인이 대신";
    case "representative_or_agent": return corporate ? "대표자 또는 대리인" : "본인 또는 대리인";
    default: return visitorType;
  }
}

const LEVEL_LABELS: Record<string, string> = {
  official_minimum: "공식 최소 서류",
  official_required: "공식 필수 서류",
  recommended_additional: "추가로 요청될 수 있는 서류",
};

const SUBMISSION_LABELS: Record<string, string> = {
  original: "원본 제출",
  original_or_copy: "원본 또는 사본",
  photo_or_pdf: "사진 또는 PDF",
  printed_original_photo: "원본을 출력해 촬영",
  auto_submit: "은행이 자동 제출",
};

function candidateOf(operation: Operation): OperationCandidate {
  return {
    operation_id: operation.operation_id,
    label_ko: operationLabel(operation),
    operation_label_ko: operation.label_ko,
    bank_code: operation.bank_code,
    bank_slug: operation.bank_slug,
    bank_label_ko: operation.bank_label_ko,
    customer_type: operation.customer_type,
    confirmation_status: operation.status === "published" ? "CONFIRMED" : "IN_REVIEW",
    verified_at: operation.verified_at,
  };
}

function documentView(document: RequirementSet["documents"][number]) {
  const validity = document.issued_within_days ?? document.validity_days;
  return {
    doc_type: document.doc_type,
    label_ko: document.label_ko,
    issuer: document.issuer,
    submission_method: document.submission_method,
    submission_label_ko: SUBMISSION_LABELS[document.submission_method] ?? document.submission_method,
    issued_within_days: document.issued_within_days,
    validity_note: validity === null || validity === undefined ? null : `발급일로부터 ${validity}일 이내`,
    choice_group: document.choice_group,
    notes: document.notes,
  };
}

function requirementView(set: RequirementSet, operation: Operation): RequirementView {
  const groups: { choice_group: string | null; documents: ReturnType<typeof documentView>[] }[] = [];
  for (const document of set.documents) {
    const key = document.choice_group;
    const existing = key === null ? null : groups.find((group) => group.choice_group === key);
    if (existing) existing.documents.push(documentView(document));
    else groups.push({ choice_group: key, documents: [documentView(document)] });
  }
  return {
    requirement_code: set.requirement_code,
    requirement_level: set.requirement_level,
    level_label_ko: LEVEL_LABELS[set.requirement_level] ?? set.requirement_level,
    channel: set.channel,
    channel_label_ko: CHANNEL_LABELS[set.channel] ?? set.channel,
    visitor_type: set.visitor_type,
    visitor_label_ko: visitorLabel(set.visitor_type, operation.customer_type),
    purpose_code: set.purpose_code,
    purpose_label_ko: set.eligibility_notes,
    eligibility_notes: set.eligibility_notes,
    notes: set.notes,
    document_groups: groups,
    preparations: set.preparations,
    source: {
      publisher: set.source.publisher,
      title: set.source.title,
      url: set.source.url,
      checked_at: set.source.checked_at,
    },
  };
}

const AXIS_QUESTIONS: Record<ChoiceAxis, string> = {
  channel: "어떻게 처리하실 계획인가요?",
  visitor_type: "누가 처리하시나요?",
  purpose_code: "계좌를 어떤 목적으로 사용하시나요?",
};

function optionsFor(axis: ChoiceAxis, sets: readonly RequirementSet[], operation: Operation): ChoiceOption[] {
  const options: ChoiceOption[] = [];
  for (const set of sets) {
    const value = set[axis];
    if (value === null || options.some((option) => option.value === value)) continue;
    options.push({
      value,
      label_ko: axis === "channel" ? CHANNEL_LABELS[value] ?? value
        : axis === "visitor_type" ? visitorLabel(value, operation.customer_type)
        : set.eligibility_notes ?? value,
      description: axis === "purpose_code" ? null : set.eligibility_notes,
    });
  }
  return options;
}

/** Narrow the requirement sets by the choices made so far, one axis at a time. */
function narrow(
  operation: Operation,
  selections: { channel: string | null; visitor_type: string | null; purpose_code: string | null },
): { sets: RequirementSet[]; pending: PendingChoice | null } {
  let sets = [...requirementSetsOf(operation)];
  for (const axis of ["channel", "visitor_type", "purpose_code"] as const) {
    const chosen = selections[axis];
    if (chosen !== null) {
      const matched = sets.filter((set) => set[axis] === chosen
        || (axis === "visitor_type" && set.visitor_type === "representative_or_agent"));
      if (matched.length) sets = matched;
      continue;
    }
    const values = new Set(sets.map((set) => set[axis]).filter((value) => value !== null));
    if (values.size > 1) {
      return { sets, pending: { axis, question: AXIS_QUESTIONS[axis], options: optionsFor(axis, sets, operation) } };
    }
  }
  return { sets, pending: null };
}

function bankFromMention(query: string, mention: string | null) {
  if (!mention) return null;
  if (!normalize(query).includes(normalize(mention))) {
    throw new TaskIntentError("UNGROUNDED_BANK", "입력하신 은행을 확인하지 못했어요. 은행명을 다시 적어주세요.");
  }
  const slug = BANK_ALIASES.find((bank) => bank.aliases.some((alias) => normalize(alias) === normalize(mention)))?.bank_slug;
  return BANKS.find((bank) => bank.bank_slug === slug) ?? null;
}

export interface ResolveInput {
  query?: unknown;
  operation_id?: unknown;
  selections?: unknown;
}

function readSelections(value: unknown) {
  const raw = (typeof value === "object" && value !== null ? value : {}) as Record<string, unknown>;
  const read = (key: string) => (typeof raw[key] === "string" && raw[key].length <= 40 ? (raw[key] as string) : null);
  return { channel: read("channel"), visitor_type: read("visitor_type"), purpose_code: read("purpose_code") };
}

/** Keep only hints that exist in this operation's own requirement sets. */
function groundSelections(
  operation: Operation,
  selections: { channel: string | null; visitor_type: string | null; purpose_code: string | null },
) {
  const sets = requirementSetsOf(operation);
  const keep = (axis: ChoiceAxis) => {
    const value = selections[axis];
    return value !== null && sets.some((set) => set[axis] === value) ? value : null;
  };
  return { channel: keep("channel"), visitor_type: keep("visitor_type"), purpose_code: keep("purpose_code") };
}

function build(
  operation: Operation | null,
  bankLabel: string | null,
  bankCode: string | null,
  candidates: OperationCandidate[],
  selections: { channel: string | null; visitor_type: string | null; purpose_code: string | null },
  method: "llm" | "selection",
  needsBank: boolean,
): TaskResolutionResponse {
  if (!operation) {
    return {
      schema_version: "3.0",
      normalized_query: bankLabel ?? "",
      resolution: "UNSUPPORTED",
      intent: { bank_code: bankCode, bank_label: bankLabel, operation_id: null },
      selected_operation: null,
      candidates,
      pending_choice: null,
      selections,
      requirements: [],
      clarification_question: "은행에서 어떤 일을 처리하려는지 조금 더 알려주시겠어요?",
      reason: "현재 등록된 업무 중에서 맞는 항목을 찾지 못했어요.",
      interpretation_method: method,
    };
  }

  const grounded = groundSelections(operation, selections);
  const { sets, pending } = narrow(operation, grounded);
  const candidate = candidateOf(operation);
  const resolved = !needsBank && pending === null;

  return {
    schema_version: "3.0",
    normalized_query: operationLabel(operation),
    resolution: resolved ? "RESOLVED" : "NEEDS_CONFIRMATION",
    intent: {
      bank_code: operation.bank_code,
      bank_label: operation.bank_label_ko,
      operation_id: operation.operation_id,
    },
    selected_operation: candidate,
    candidates: candidates.length ? candidates : [candidate],
    pending_choice: pending,
    selections: grounded,
    // Never show documents before the bank is confirmed; a wrong bank means a wrong list.
    requirements: pending || needsBank ? [] : sets.map((set) => requirementView(set, operation)),
    clarification_question: needsBank
      ? "어느 은행에서 처리하실 업무인가요?"
      : pending?.question ?? null,
    reason: needsBank
      ? "하려는 업무는 찾았어요. 은행에 따라 필요한 서류가 달라서 은행을 먼저 확인할게요."
      : pending
        ? "업무를 찾았어요. 상황에 따라 필요한 서류가 달라져서 한 가지만 더 확인할게요."
        : "입력하신 상황에 맞는 업무와 필요 서류를 찾았어요.",
    interpretation_method: method,
  };
}

export async function resolveQuery(
  input: ResolveInput,
  interpret: (query: string) => Promise<InterpretedIntent> = interpretQuery,
): Promise<TaskResolutionResponse> {
  const selections = readSelections(input.selections);

  // Button presses come back with the operation already chosen; no model call.
  if (typeof input.operation_id === "string") {
    const operation = findOperation(input.operation_id);
    if (!operation) throw new TaskIntentError("UNKNOWN_OPERATION", "선택한 업무를 찾지 못했어요.", 400);
    return build(operation, operation.bank_label_ko, operation.bank_code, [candidateOf(operation)], selections, "selection", false);
  }

  const rawQuery = input.query;
  if (typeof rawQuery !== "string" || rawQuery.trim().length < 2 || rawQuery.trim().length > 300) {
    throw new TaskIntentError("INVALID_QUERY", "하려는 업무를 2자 이상, 300자 이하로 적어주세요.", 400);
  }
  const query = redactQuery(rawQuery.trim());
  const intent = validateIntent(await interpret(query));
  const bank = bankFromMention(query, intent.bank_mention);
  const operation = intent.operation_id ? findOperation(intent.operation_id) : null;

  if (!operation) {
    return build(null, bank?.label_ko ?? intent.bank_mention, bank?.bank_code ?? null, [], selections, "llm", false);
  }

  // A named bank outranks the model's pick: keep the intent, switch the bank.
  const sameWork = OPERATIONS.filter((item) => item.operation_code === operation.operation_code);
  const forBank = bank ? sameWork.find((item) => item.bank_slug === bank.bank_slug) ?? null : null;
  if (bank && !forBank) {
    return {
      ...build(null, bank.label_ko, bank.bank_code, sameWork.map(candidateOf), selections, "llm", false),
      reason: "하려는 업무는 찾았지만, 말씀하신 은행의 해당 업무는 아직 등록되어 있지 않아요.",
      clarification_question: "아래 은행 중에서 고르시거나 다른 업무를 입력해주세요.",
    };
  }

  const chosen = forBank ?? operation;
  const hinted = {
    channel: selections.channel ?? intent.channel_hint,
    visitor_type: selections.visitor_type ?? intent.visitor_hint,
    purpose_code: selections.purpose_code ?? intent.purpose_hint,
  };
  const needsBank = !bank || intent.needs_clarification || intent.confidence < 0.8;
  return build(chosen, chosen.bank_label_ko, chosen.bank_code, sameWork.map(candidateOf), hinted, "llm", needsBank);
}
