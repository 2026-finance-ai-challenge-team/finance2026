import { BANKS, SERVICES, TASK_CATALOG, type CatalogTask } from "./catalog.ts";
import { interpretQuery, redactQuery, validateIntent } from "./interpret.ts";
import { TaskIntentError, type InterpretedIntent, type TaskResolutionCandidate, type TaskResolutionResponse } from "./types.ts";

const normalize = (value: string) => value.normalize("NFKC").toLocaleLowerCase("en-US").replace(/\s/g, "");

function candidate(task: CatalogTask): TaskResolutionCandidate {
  const bank = BANKS.find((bank) => bank.bank_code === task.bank_code)!;
  const service = SERVICES.find((service) => service.service_id === task.service_id)!;
  return {
    ...task,
    label_ko: `${bank.label_ko} · ${service.label_ko}`,
    bank_label: bank.label_ko,
    service_label: service.label_ko,
  };
}

export async function resolveQuery(
  rawQuery: unknown,
  interpret: (query: string) => Promise<InterpretedIntent> = interpretQuery,
): Promise<TaskResolutionResponse> {
  if (typeof rawQuery !== "string" || rawQuery.trim().length < 2 || rawQuery.trim().length > 300) {
    throw new TaskIntentError("INVALID_QUERY", "하려는 업무를 2자 이상, 300자 이하로 적어주세요.", 400);
  }
  const query = redactQuery(rawQuery.trim());
  const intent = validateIntent(await interpret(query));
  const mention = intent.bank_mention;
  if (mention && !normalize(query).includes(normalize(mention))) {
    throw new TaskIntentError("UNGROUNDED_BANK", "입력하신 은행을 확인하지 못했어요. 은행명을 다시 적어주세요.");
  }
  const bank = mention ? BANKS.find((bank) => bank.aliases.some((alias) => normalize(alias) === normalize(mention))) : null;
  const services = intent.service_ids.map((id) => SERVICES.find((service) => service.service_id === id)!)
    .map(({ service_id, label_ko }) => ({ service_id, label_ko }));
  // Preserve an explicit bank. A missing catalog pair is not permission to substitute another bank.
  const candidates = intent.service_ids.flatMap((id) => TASK_CATALOG
    .filter((task) => task.service_id === id && (!mention || task.bank_code === bank?.bank_code))
    .map(candidate));
  const resolved = candidates.length === 1 && Boolean(bank) && services.length === 1
    && !intent.needs_clarification && intent.confidence >= 0.8;
  const resolution = !candidates.length ? "UNSUPPORTED" : resolved ? "RESOLVED" : "NEEDS_CONFIRMATION";
  const reason = services.length === 0
    ? "현재 등록된 업무 중에서 맞는 항목을 찾지 못했어요."
    : !candidates.length
      ? "하려는 업무는 찾았지만, 말씀하신 은행의 해당 업무는 아직 안내 목록에 없어요."
      : "입력하신 상황에서 관련 있는 은행 업무를 찾았어요.";
  const question = resolution === "RESOLVED" ? null
    : !services.length ? "은행에서 어떤 일을 처리하려는지 조금 더 알려주시겠어요?"
    : !candidates.length ? "은행명을 다시 확인하거나 다른 업무를 입력해주세요."
    : !mention && services.length > 1 ? "먼저 하려는 업무와 이용할 은행을 선택해주세요."
    : !mention ? "어느 은행에서 처리하려는 업무인가요?"
    : "찾은 업무가 하려는 일과 맞는지 확인해주세요.";
  return {
    schema_version: "2.0",
    normalized_query: [bank?.label_ko ?? mention, ...services.map((service) => service.label_ko)].filter(Boolean).join(" · "),
    resolution,
    intent: { services, bank_code: bank?.bank_code ?? null, bank_label: bank?.label_ko ?? mention },
    selected_task: resolved ? candidates[0] : null,
    candidates,
    clarification_question: question,
    reason,
    interpretation_method: "llm",
  };
}
