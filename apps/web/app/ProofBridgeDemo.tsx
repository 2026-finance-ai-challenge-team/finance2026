"use client";

import { useMemo, useRef, useState, type DragEvent, type FormEvent, type ReactNode } from "react";
import {
  AnalysisApiError,
  analyzeDocuments,
  confirmDocumentClassification,
  deleteAnalysisSession,
  downloadPreparationKit,
  loadDemoAnalysis,
  resolveTask,
  type AnalysisResponse,
  type ApiDocumentStatus,
  type TaskResolutionCandidate,
  type TaskResolutionResponse,
} from "./analysisApi";
import {
  DOC_LABELS,
  DOCUMENT_TYPE_OPTIONS,
  analysisHeadline,
  completionOf,
  loadResult,
  toRequirementRows,
  toRows,
  toUploadedDocumentRows,
  type DisplayRow,
  type Tone,
} from "./classifyResult";

type View = "task" | "prepare" | "analyzing" | "result";
type IconName =
  | "alert"
  | "arrow"
  | "check"
  | "chevron"
  | "close"
  | "document"
  | "download"
  | "external"
  | "info"
  | "lock"
  | "refresh"
  | "search"
  | "spark"
  | "trash"
  | "upload";

const MAX_FILES = 10;
const MAX_FILE_SIZE = 10 * 1024 * 1024;
const ACCEPTED_EXTENSIONS = [".pdf", ".jpg", ".jpeg", ".png"];
const STATIC_SAMPLE_ROWS = toRows(loadResult());

const evidenceBundles = [
  "공과금 고지서",
  "관리비 고지서 + 등본",
  "세금 고지서",
  "건강보험 자격득실 확인서",
  "근로계약서 + 사업자등록증",
  "휴대폰 요금 납부확인서",
];

const bundleDescriptions: Record<string, string> = {
  utility_bill: "본인 명의 전기·가스·수도 고지서나 납부확인서가 있을 때",
  management_fee_and_resident_copy: "현재 거주지 관리비 고지서와 같은 주소의 주민등록표 등본이 있을 때",
  tax_bill: "본인에게 발급된 국세·지방세 고지서가 있을 때",
  health_insurance_qualification: "건강보험 가입·자격 내역으로 거래 목적을 증빙할 때",
  employment_contract_and_employer_registration: "재직 중인 회사의 근로계약서와 고용주 사업자등록증을 함께 준비할 수 있을 때",
  mobile_phone_payment: "휴대폰 요금의 납부계좌 등록 정보와 실제 납부내역을 확인할 수 있을 때",
};

const statusLabels: Record<ApiDocumentStatus, string> = {
  READY: "준비 완료",
  MISSING: "추가 필요",
  EXPIRED: "기한 만료",
  MISMATCH: "정보 불일치",
  UNNECESSARY: "이번 업무에는 불필요",
  REVIEW_REQUIRED: "확인 필요",
};

function Icon({ name }: { name: IconName }) {
  const paths: Record<IconName, ReactNode> = {
    alert: <><path d="M12 3 2.8 20h18.4z"/><path d="M12 9v4M12 17h.01"/></>,
    arrow: <><path d="M5 12h14"/><path d="m14 7 5 5-5 5"/></>,
    check: <path d="m5 12 4 4L19 6"/>,
    chevron: <path d="m9 7 5 5-5 5"/>,
    close: <><path d="m6 6 12 12M18 6 6 18"/></>,
    document: <><path d="M7 3h7l4 4v14H7z"/><path d="M14 3v5h5"/><path d="M10 13h5M10 17h5"/></>,
    download: <><path d="M12 4v11"/><path d="m7 10 5 5 5-5"/><path d="M5 20h14"/></>,
    external: <><path d="M14 5h5v5M19 5l-8 8"/><path d="M18 13v6H5V6h6"/></>,
    info: <><circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7h.01"/></>,
    lock: <><rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/></>,
    refresh: <><path d="M20 7v5h-5"/><path d="M4 17v-5h5"/><path d="M18 11a7 7 0 0 0-12-4l-2 2M6 13a7 7 0 0 0 12 4l2-2"/></>,
    search: <><circle cx="11" cy="11" r="7"/><path d="m16 16 4 4"/></>,
    spark: <><path d="m12 3 1.3 4.2L17 9l-3.7 1.8L12 15l-1.3-4.2L7 9l3.7-1.8z"/><path d="m18.5 15 .7 2.1 1.8.9-1.8.9-.7 2.1-.7-2.1L16 18l1.8-.9z"/></>,
    trash: <><path d="M4 7h16M9 7V4h6v3M7 7l1 14h8l1-14M10 11v6M14 11v6"/></>,
    upload: <><path d="M12 16V4"/><path d="m7 9 5-5 5 5"/><path d="M5 15v5h14v-5"/></>,
  };
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      {paths[name]}
    </svg>
  );
}

function formatBytes(bytes: number) {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))}KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)}MB`;
}

function toneForStatus(status: ApiDocumentStatus): Tone {
  if (status === "READY") return "ready";
  if (status === "EXPIRED") return "expired";
  if (status === "MISMATCH") return "mismatch";
  if (status === "UNNECESSARY") return "unused";
  return "needed";
}

function acquisitionChannelLabel(channel: string) {
  const labels: Record<string, string> = {
    government_online_or_offline: "온라인·주민센터·무인발급기",
    insurer_online_or_offline: "공단 홈페이지·앱·무인발급기",
    issuer_direct: "발급기관에 직접 요청",
    employer_direct: "고용주에게 요청",
    telecom_online_or_customer_center: "통신사 앱·웹·고객센터",
    tax_online_or_offline: "홈택스·위택스·관할기관",
    utility_provider_online_or_customer_center: "공급기관 앱·웹·고객센터",
  };
  return labels[channel] ?? "발급기관 확인";
}

function uploadedRelevanceLabel(document: AnalysisResponse["documents"][number]) {
  if (document.status === "UNNECESSARY") {
    return document.reason_code === "CLEARLY_UNRELATED_DOCUMENT"
      ? "업무와 관련 없는 문서"
      : "이번 업무에는 불필요";
  }
  if (document.doc_type === null) return "필요 여부 확인 중";
  return "이번 업무에 필요한 서류";
}

function FlowNav({ view }: { view: View }) {
  const current = view === "task" ? 1 : view === "prepare" ? 2 : view === "analyzing" ? 3 : 4;
  const steps = ["업무 확인", "서류 모으기", "AI 분석", "준비 키트"];
  return (
    <nav className="flow-nav" aria-label="업무 준비 단계">
      {steps.map((step, index) => {
        const number = index + 1;
        return (
          <div className="flow-fragment" key={step}>
            {index > 0 && (
              <div className={`flow-line ${number <= current ? "complete" : ""}`}/>
            )}
            <div className={`flow-step ${number <= current ? "active" : ""} ${number === current ? "current" : ""}`} aria-current={number === current ? "step" : undefined}>
              <span>{number < current ? <Icon name="check"/> : number}</span><b>{step}</b>
            </div>
          </div>
        );
      })}
    </nav>
  );
}

function TaskDiscoveryAside() {
  return (
    <aside className="task-discovery-aside">
      <div className="aside-head"><span>AI 업무 찾기</span><b>근거 있는 연결</b></div>
      <ol className="discovery-steps">
        <li><span>01</span><div><b>편한 표현 그대로 입력</b><p>은행명이나 정확한 업무명을 몰라도 괜찮아요.</p></div></li>
        <li><span>02</span><div><b>상황에 맞는 은행 업무</b><p>한도계좌 해제 · 상속인 금융거래 조회 · 상속예금 지급</p></div></li>
        <li><span>03</span><div><b>한 번 확인하고 시작</b><p>짧거나 모호한 표현은 자동 확정하지 않고 질문합니다.</p></div></li>
      </ol>
      <div className="official-note"><Icon name="check"/><div><b>현재 자동 점검 가능</b><p>카카오뱅크 한도계좌 해제 · 공식 출처 확인</p></div></div>
      <div className="ai-boundary-card"><Icon name="info"/><div><b>상속 업무는 공식 안내 제공</b><p>상속 서류의 자동 점검과 준비 키트는 아직 제공하지 않습니다.</p></div></div>
    </aside>
  );
}

function TaskMatchCard({
  resolution,
  onConfirm,
  onReset,
}: {
  resolution: TaskResolutionResponse;
  onConfirm: (task: TaskResolutionCandidate) => void;
  onReset: () => void;
}) {
  const [chosenTaskId, setChosenTaskId] = useState(resolution.selected_task?.task_id ?? "");
  const task = resolution.candidates.find((candidate) => candidate.task_id === chosenTaskId);
  if (resolution.resolution === "UNSUPPORTED") {
    return (
      <div className="task-match-card unsupported" role="status">
        <span className="match-icon"><Icon name="info"/></span>
        <div><span>아직 연결할 수 없는 업무예요</span><h2>{resolution.normalized_query || "하려는 일을 조금 더 알려주세요"}</h2><p>{resolution.reason}</p></div>
        <button className="secondary-action" type="button" onClick={onReset}>다시 입력</button>
      </div>
    );
  }
  return (
    <div className="task-match-card" role="status">
      <div className="match-heading">
        <span className="match-icon" aria-hidden="true"><Icon name="search"/></span>
        <div>
          <span>{resolution.resolution === "RESOLVED" ? "이 업무로 이해했어요" : "한 번만 확인해주세요"}</span>
          <h2>{task?.label_ko ?? resolution.intent.services.map((service) => service.label_ko).join(" · ")}</h2>
          <p>{resolution.clarification_question ?? resolution.reason}</p>
        </div>
      </div>
      <div className="task-candidate-picker">
        <label htmlFor="task-candidate">은행 · 서비스</label>
        <select id="task-candidate" value={chosenTaskId} onChange={(event) => setChosenTaskId(event.target.value)}>
          <option value="">처리할 은행과 업무를 선택해주세요</option>
          {resolution.candidates.map((candidate) => <option key={candidate.task_id} value={candidate.task_id}>{candidate.label_ko}</option>)}
        </select>
        {!resolution.intent.bank_code && <p>은행을 아직 확인하지 않았어요. 선택 목록에는 공식 안내가 등록된 은행만 있어요.</p>}
      </div>
      {task && <>
        <p className="task-support-note">{task.support_status === "GUIDE_ONLY" ? "공식 안내 제공 · 서류 자동 점검은 아직 지원하지 않아요." : "서류 점검 단계로 연결할 수 있어요."}</p>
        <a className="match-source" href={task.source_url} target="_blank" rel="noreferrer">{task.source_title} · {task.last_checked} 확인 <Icon name="external"/></a>
      </>}
      <div className="match-actions">
        <button className="secondary-action" type="button" onClick={onReset}>다른 업무 입력</button>
        {task?.support_status === "GUIDE_ONLY" ? (
          <a className="primary-action" href={task.source_url} target="_blank" rel="noreferrer">공식 업무 안내 보기 <Icon name="external"/></a>
        ) : (
          <button className="primary-action" type="button" disabled={!task} onClick={() => { if (task) onConfirm(task); }}>맞아요, 서류 준비하기 <Icon name="arrow"/></button>
        )}
      </div>
    </div>
  );
}

function EvidenceAside() {
  return (
    <aside className="workspace-aside">
      <div className="aside-head"><span>이번 업무의 인정 증빙</span><b>6가지 방법 중 하나</b></div>
      <ol className="bundle-list">
        {evidenceBundles.map((bundle, index) => <li key={bundle}><span>{String(index + 1).padStart(2, "0")}</span><p>{bundle}</p></li>)}
      </ol>
      <div className="official-note"><Icon name="check"/><div><b>공식 출처 확인</b><p>카카오뱅크 공개 안내 · 2026.08.28 최종 확인</p></div></div>
      <div className="ai-boundary-card"><Icon name="spark"/><div><b>AI는 문서를 읽고 분류를 돕습니다</b><p>최종 상태는 AI의 자유 추론이 아니라 공식 출처를 옮긴 규칙으로 계산합니다.</p></div></div>
      <div className="privacy-card"><Icon name="lock"/><div><b>원본은 분석 응답 전에 삭제합니다</b><p>원본과 OCR 캐시는 응답 전에 지우고 결과에는 원문을 저장하지 않습니다.</p></div></div>
    </aside>
  );
}

function ErrorBanner({ message, recovery }: { message: string; recovery?: string | null }) {
  return <div className="feedback-banner error" role="alert"><Icon name="alert"/><div><b>{message}</b>{recovery && <p>{recovery}</p>}</div></div>;
}

function NoticeBanner({ message }: { message: string }) {
  return <div className="feedback-banner notice" role="status"><Icon name="check"/><div><b>{message}</b></div></div>;
}

function ServiceIntro({ onDemo }: { onDemo: () => void }) {
  return (
    <section className="service-intro" aria-labelledby="service-title">
      <div className="service-hero">
        <div className="service-hero-copy">
          <div className="service-status"><span/> 금융업무 준비 사전점검 · 합성 샘플 제공</div>
          <p className="service-kicker">BANKING TASK COMPLETION LAYER</p>
          <h1 id="service-title">모르면 그냥 다 넣으세요.<br/><em>필요한 것만 챙겨드릴게요.</em></h1>
          <p className="service-lead">공공 경로로 처리할 증빙은 공식 제출 방법으로 연결하고, 가지고 있는 PDF와 사진은 은행의 공개 기준과 대조해 부족한 서류와 다음 행동을 정리합니다.</p>
          <div className="service-actions">
            <a className="primary-action" href="#task-finder">내 금융업무 준비하기 <Icon name="arrow"/></a>
            <button className="secondary-action" type="button" onClick={onDemo}><Icon name="spark"/> 합성 샘플로 바로 체험</button>
          </div>
          <ul className="service-trust" aria-label="서비스 원칙">
            <li><Icon name="check"/> 공식 출처 기반 규칙 판정</li>
            <li><Icon name="lock"/> 비회원·일회성 분석</li>
            <li><Icon name="trash"/> 원본 즉시 삭제</li>
          </ul>
        </div>
        <div className="service-preview" aria-label="ProofBridge 결과 예시">
          <div className="preview-top"><span>준비 상태 미리보기</span><b>공개 기준 사전 점검</b></div>
          <div className="preview-score"><div><span>준비 완성도</span><strong>67<small>%</small></strong></div><i><span/></i></div>
          <div className="preview-document ready"><span><Icon name="check"/></span><div><b>주민등록표 등본</b><small>이건 이미 있어요</small></div><em>준비 완료</em></div>
          <div className="preview-document needed"><span><Icon name="arrow"/></span><div><b>관리비 고지서</b><small>공식 발급 경로를 안내해드려요</small></div><em>추가 필요</em></div>
          <div className="preview-route"><Icon name="spark"/><div><span>다음 행동</span><b>발급 → 확인 → 앱 촬영 제출</b></div></div>
          <p><Icon name="info"/> 은행의 승인 결과가 아닌 공개 기준 사전 점검 예시입니다.</p>
        </div>
      </div>
      <div className="service-capabilities">
        <article><span>01</span><div><b>업무부터 찾기</b><p>정확한 메뉴명을 몰라도 편한 말로 준비할 업무를 연결합니다.</p></div></article>
        <article><span>02</span><div><b>문서는 한꺼번에</b><p>PDF와 사진을 분류하고 필요한 핵심 항목만 확인합니다.</p></div></article>
        <article><span>03</span><div><b>부족한 것까지 해결</b><p>빠진 서류의 공식 발급 경로와 실제 제출 순서를 안내합니다.</p></div></article>
      </div>
      <div className="support-scope"><span>현재 MVP 지원 범위</span><b>카카오뱅크 한도계좌 해제 준비</b><p>지원하지 않는 업무를 가능한 것처럼 안내하지 않습니다.</p></div>
    </section>
  );
}

export function ProofBridgeDemo() {
  const [view, setView] = useState<View>("task");
  const [taskQuery, setTaskQuery] = useState("");
  const [taskResolution, setTaskResolution] = useState<TaskResolutionResponse | null>(null);
  const [selectedTask, setSelectedTask] = useState<TaskResolutionCandidate | null>(null);
  const [resolvingTask, setResolvingTask] = useState(false);
  const [files, setFiles] = useState<File[]>([]);
  const [analysis, setAnalysis] = useState<AnalysisResponse | null>(null);
  const [staticDemo, setStaticDemo] = useState(false);
  const [error, setError] = useState<{ message: string; recovery?: string | null } | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const [largeText, setLargeText] = useState(false);
  const [confirmingId, setConfirmingId] = useState<string | null>(null);
  const [downloadingKit, setDownloadingKit] = useState(false);
  const [documentTypes, setDocumentTypes] = useState<Record<string, string>>({});
  const fileInputRef = useRef<HTMLInputElement>(null);
  const taskSearchId = useRef(0);

  const uploadedRows = useMemo<DisplayRow[]>(() => {
    if (analysis) return toUploadedDocumentRows(analysis);
    if (staticDemo) return STATIC_SAMPLE_ROWS.filter((row) => !row.key.startsWith("missing-"));
    return [];
  }, [analysis, staticDemo]);
  const requirementRows = useMemo<DisplayRow[]>(() => {
    if (analysis) return toRequirementRows(analysis);
    if (staticDemo) return STATIC_SAMPLE_ROWS.filter((row) => row.key.startsWith("missing-"));
    return [];
  }, [analysis, staticDemo]);
  const rows = useMemo<DisplayRow[]>(() => [...uploadedRows, ...requirementRows], [uploadedRows, requirementRows]);
  const completion = useMemo(() => completionOf(rows), [rows]);
  const officialBundles = useMemo(
    () => analysis?.requirements.flatMap((requirement) => requirement.bundles) ?? [],
    [analysis],
  );

  const findTask = async (event?: FormEvent, suggestedQuery?: string) => {
    event?.preventDefault();
    const searchId = ++taskSearchId.current;
    const query = (suggestedQuery ?? taskQuery).trim();
    if (query.length < 2) {
      setError({ message: "하려는 업무를 두 글자 이상 적어주세요.", recovery: "예: 카뱅 한도계좌" });
      return;
    }
    setTaskQuery(query);
    setResolvingTask(true);
    setTaskResolution(null);
    setError(null);
    setNotice(null);
    try {
      const result = await resolveTask(query);
      if (searchId === taskSearchId.current) setTaskResolution(result);
    } catch (caught) {
      const apiError = caught instanceof AnalysisApiError ? caught : new AnalysisApiError("입력한 업무를 찾지 못했어요.");
      if (searchId === taskSearchId.current) setError({ message: apiError.message, recovery: apiError.recovery });
    } finally {
      if (searchId === taskSearchId.current) setResolvingTask(false);
    }
  };

  const confirmTask = (task: TaskResolutionCandidate) => {
    if (task.support_status !== "SUPPORTED") return;
    setSelectedTask(task);
    setView("prepare");
    setError(null);
    setNotice(`${task.label_ko} 업무로 연결했어요.`);
  };

  const changeTask = () => {
    setView("task");
    setTaskResolution(null);
    setSelectedTask(null);
    setFiles([]);
    setError(null);
    setNotice(null);
  };

  const chooseFiles = (incoming: File[]) => {
    setError(null);
    setNotice(null);
    const merged = [...files, ...incoming].filter((file, index, all) =>
      all.findIndex((candidate) => candidate.name === file.name && candidate.size === file.size && candidate.lastModified === file.lastModified) === index,
    );
    const unsupported = merged.find((file) => !ACCEPTED_EXTENSIONS.some((extension) => file.name.toLowerCase().endsWith(extension)));
    if (unsupported) {
      setError({ message: `${unsupported.name}은 지원하지 않는 형식이에요.`, recovery: "PDF, JPG, PNG 파일만 선택해주세요." });
      return;
    }
    const oversized = merged.find((file) => file.size > MAX_FILE_SIZE);
    if (oversized) {
      setError({ message: `${oversized.name}이 10MB를 넘어요.`, recovery: "파일을 10MB 이하로 줄인 뒤 다시 선택해주세요." });
      return;
    }
    if (merged.length > MAX_FILES) {
      setError({ message: `파일은 한 번에 ${MAX_FILES}개까지 확인할 수 있어요.`, recovery: "중요한 증빙부터 나누어 올려주세요." });
      return;
    }
    setFiles(merged);
  };

  const handleDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setDragging(false);
    chooseFiles(Array.from(event.dataTransfer.files));
  };

  const runAnalysis = async () => {
    if (!files.length) return;
    setView("analyzing");
    setError(null);
    setNotice(null);
    setStaticDemo(false);
    try {
      setAnalysis(await analyzeDocuments(files, selectedTask?.task_id));
      setView("result");
    } catch (caught) {
      const apiError = caught instanceof AnalysisApiError ? caught : new AnalysisApiError("문서를 분석하지 못했어요.");
      setError({ message: apiError.message, recovery: apiError.recovery });
      setView("prepare");
    }
  };

  const runDemo = async () => {
    taskSearchId.current += 1;
    setResolvingTask(false);
    setView("analyzing");
    setError(null);
    setNotice(null);
    setFiles([]);
    try {
      setAnalysis(await loadDemoAnalysis());
      setStaticDemo(false);
    } catch {
      setAnalysis(null);
      setStaticDemo(true);
      setNotice("분석 서버가 없어 내장된 합성 결과로 안전하게 체험 중이에요.");
    } finally {
      setView("result");
    }
  };

  const resetSession = async () => {
    const sessionId = analysis?.session_id;
    setView("prepare");
    setFiles([]);
    setAnalysis(null);
    setStaticDemo(false);
    setError(null);
    setDocumentTypes({});
    if (!sessionId) {
      setNotice("화면의 합성 분석 결과를 지웠어요.");
      return;
    }
    const deleted = await deleteAnalysisSession(sessionId);
    setNotice(deleted ? "분석 세션과 결과를 삭제했어요." : "화면에서는 지웠지만 서버의 삭제 확인을 받지 못했어요.");
  };

  const confirmClassification = async (documentId: string, fallbackType: string | null) => {
    if (!analysis) return;
    const docType = documentTypes[documentId] ?? fallbackType;
    if (!docType) return;
    setConfirmingId(documentId);
    setError(null);
    try {
      setAnalysis(await confirmDocumentClassification(analysis.session_id, documentId, docType));
      setNotice("문서 종류 확인을 반영했어요. 내용과 발급일 검증은 계속 필요합니다.");
    } catch (caught) {
      const apiError = caught instanceof AnalysisApiError ? caught : new AnalysisApiError("문서 종류 확인을 저장하지 못했어요.");
      setError({ message: apiError.message, recovery: apiError.recovery });
    } finally {
      setConfirmingId(null);
    }
  };

  const downloadKit = async () => {
    if (!analysis) return;
    setDownloadingKit(true);
    setError(null);
    try {
      const { blob, filename } = await downloadPreparationKit(analysis.session_id);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = filename;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
      setNotice("공식 발급 경로와 제출 순서가 담긴 준비 안내 ZIP을 만들었어요.");
    } catch (caught) {
      const apiError = caught instanceof AnalysisApiError ? caught : new AnalysisApiError("준비 안내 키트를 내려받지 못했어요.");
      setError({ message: apiError.message, recovery: apiError.recovery });
    } finally {
      setDownloadingKit(false);
    }
  };

  const headline = analysis ? analysisHeadline(analysis, rows) : "합성 문서의 분류 결과를 확인해보세요.";
  const overall = analysis?.overall_status ?? "REVIEW_REQUIRED";
  const overallLabel = overall === "READY" ? "공개 기준 사전 점검 완료" : overall === "ACTION_REQUIRED" ? "보완할 서류가 있어요" : "확인이 필요한 항목이 있어요";
  const hasResidentCopy = analysis ? analysis.documents.some((document) => document.doc_type === "resident_registration_copy") : staticDemo;
  const needsManagementFee = rows.some((row) => row.name.includes("관리비") && row.status === "추가 필요");

  return (
    <div className={`product-shell ${largeText ? "large-text" : ""}`}>
      <a className="skip-link" href="#workspace">본문으로 바로가기</a>
      <header className="product-header">
        <a className="product-brand" href="#workspace" aria-label="ProofBridge 처음으로"><span className="brand-symbol" aria-hidden="true"><i/><i/></span><span>ProofBridge</span></a>
        <div className="header-context"><span className="context-dot"/>{selectedTask?.label_ko ?? "AI로 금융업무 찾기"}</div>
        <div className="header-actions"><a className="header-demo-link" href="#task-finder">서비스 체험</a><button className="text-size-button" type="button" aria-pressed={largeText} onClick={() => setLargeText((value) => !value)}>가<span aria-hidden="true">+</span> 글자 크게</button><div className="privacy-pill"><Icon name="lock"/> 비회원 · 즉시 삭제</div></div>
      </header>

      <main id="workspace" className="product-main">
        {view === "task" && <ServiceIntro onDemo={runDemo}/>}
        <FlowNav view={view}/>
        {error && (
          <ErrorBanner message={error.message} recovery={error.recovery}/>
        )}
        {notice && (
          <NoticeBanner message={notice}/>
        )}

        {view === "task" && (
          <section id="task-finder" className="task-discovery-grid">
            <div className="task-query-card">
              <div className="section-kicker"><Icon name="spark"/> AI 업무 찾기</div>
              <h1>하려는 금융업무를<br/><em>편하게 말해주세요.</em></h1>
              <p className="workspace-lead">정확한 메뉴명이나 서류 이름을 몰라도 괜찮아요. 공식 출처가 연결된 업무 카탈로그에서 가장 가까운 준비 절차를 찾습니다.</p>
              <form className="task-search-form" onSubmit={(event) => findTask(event)}>
                <label htmlFor="task-query">어떤 업무를 준비하고 있나요?</label>
                <div>
                  <Icon name="search"/>
                  <input id="task-query" value={taskQuery} maxLength={300} onChange={(event) => { taskSearchId.current += 1; setResolvingTask(false); setTaskQuery(event.target.value); setTaskResolution(null); }} placeholder="지금 상황을 적어주세요" autoComplete="off"/>
                  <button className="primary-action" type="submit" disabled={resolvingTask}>{resolvingTask ? "찾는 중…" : "업무 찾기"} <Icon name="arrow"/></button>
                </div>
              </form>
              <div className="query-examples" aria-label="입력 예시">
                <span>이렇게 적어보세요</span>
                {["카뱅 한도계좌", "부모님이 돌아가셔서 재산을 정리하고 싶어요", "국민은행에 있는 아버지 예금을 상속받고 싶어요"].map((query) => <button type="button" key={query} onClick={() => findTask(undefined, query)}>{query}</button>)}
              </div>
              {resolvingTask && <div className="task-searching" role="status"><span className="pulse-dot"/><div><b>상황에 맞는 은행 업무를 찾고 있어요</b></div></div>}
              {taskResolution && (
                <TaskMatchCard
                  resolution={taskResolution}
                  onConfirm={confirmTask}
                  onReset={() => { setTaskResolution(null); setTaskQuery(""); }}
                />
              )}
            </div>
            <TaskDiscoveryAside/>
          </section>
        )}

        {view === "prepare" && (
          <section className="workspace-grid">
            <div className="workspace-primary">
              <div className="section-kicker"><Icon name="spark"/> 지금 준비할 업무</div>
              <h1>서류 이름은 몰라도 괜찮아요.<br/><em>가지고 있는 것부터</em> 확인할게요.</h1>
              <p className="workspace-lead">카카오뱅크 한도계좌 해제에 인정되는 증빙 묶음과 업로드한 문서를 대조해, 빠진 서류와 다음 행동을 정리합니다.</p>

              <article className="selected-task-card">
                <div className="bank-badge" aria-hidden="true">K</div>
                <div><span>AI가 연결한 지원 업무</span><h2>{selectedTask?.label_ko ?? "카카오뱅크 한도계좌 해제"}</h2><p>본인 · 비대면 · 공개 기준 사전 점검</p></div>
                <button type="button" onClick={changeTask}>업무 변경 <Icon name="chevron"/></button>
              </article>

              <div className={`upload-zone ${dragging ? "dragging" : ""}`} onDragEnter={(event) => { event.preventDefault(); setDragging(true); }} onDragOver={(event) => event.preventDefault()} onDragLeave={(event) => { if (event.currentTarget === event.target) setDragging(false); }} onDrop={handleDrop}>
                <div className="upload-icon"><Icon name="upload"/></div>
                <div className="upload-copy"><h2>PDF·사진을 한꺼번에 올려주세요</h2><p>파일명을 바꾸지 않아도 됩니다. PDF, JPG, PNG · 최대 10개 · 파일당 10MB</p></div>
                <button className="upload-button" type="button" onClick={() => fileInputRef.current?.click()}>파일 선택</button>
                <input ref={fileInputRef} className="visually-hidden" type="file" accept=".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png" multiple onChange={(event) => { chooseFiles(Array.from(event.target.files ?? [])); event.target.value = ""; }}/>
              </div>

              {files.length > 0 && (
                <div className="selected-files" aria-live="polite">
                  <div className="selected-files-head"><span><Icon name="check"/><b>{files.length}개 파일을 선택했어요</b></span><small>최대 {MAX_FILES}개</small></div>
                  <ul>{files.map((file, index) => <li key={`${file.name}-${file.size}-${file.lastModified}`}><span className="file-icon"><Icon name="document"/></span><span className="file-name">{file.name}</span><small>{formatBytes(file.size)}</small><button className="icon-button" type="button" aria-label={`${file.name} 빼기`} onClick={() => setFiles((current) => current.filter((_, fileIndex) => fileIndex !== index))}><Icon name="close"/></button></li>)}</ul>
                </div>
              )}

              <div className="prepare-actions"><button className="secondary-action" type="button" onClick={runDemo}><Icon name="spark"/> 합성 샘플로 체험하기</button><button className="primary-action" type="button" disabled={!files.length} onClick={runAnalysis}>문서 분석 시작 <Icon name="arrow"/></button></div>
              <p className="sample-caution"><Icon name="info"/> 공개 심사용 환경에서는 실제 개인정보가 아닌 합성 샘플만 사용해주세요.</p>
            </div>
            <EvidenceAside/>
          </section>
        )}

        {view === "analyzing" && (
          <section className="analysis-state" aria-live="polite" aria-busy="true">
            <div className="analysis-orbit"><span/><Icon name="document"/></div>
            <div className="section-kicker"><Icon name="spark"/> 안전한 문서 분석</div>
            <h1>서류를 읽고 공식 요건과 대조하고 있어요</h1>
            <p>문서 수와 페이지에 따라 잠시 걸릴 수 있습니다. 실제 진행률을 확인할 수 없어 임의의 백분율은 표시하지 않습니다.</p>
            <ol className="analysis-steps">
              <li className="done"><Icon name="check"/><span><b>파일 안전 확인</b><small>형식과 크기를 검사합니다</small></span></li>
              <li className="current"><span className="pulse-dot"/><span><b>텍스트·문서 종류 인식</b><small>PDF 텍스트를 먼저 읽고 필요한 페이지만 OCR합니다</small></span></li>
              <li><span className="step-dot"/><span><b>공식 규칙 대조</b><small>AI가 아닌 버전형 규칙이 최종 상태를 계산합니다</small></span></li>
            </ol>
          </section>
        )}

        {view === "result" && (
          <section className="result-workspace">
            <div className={`result-summary ${overall.toLowerCase()}`}>
              <div className="summary-copy"><span className="result-eyebrow"><Icon name={overall === "READY" ? "check" : "alert"}/>{overallLabel}</span><h1>{headline}</h1><p>결과는 은행 승인을 보장하지 않는 공개 기준 사전 점검입니다. 최종 제출 전 원문과 공식 안내를 확인해주세요.</p></div>
              <div className="readiness-card" aria-label={`서류 준비 완성도 ${completion.percent}%`}><div><span>서류 준비 완성도</span><strong>{completion.percent}<small>%</small></strong></div><div className="progress-track"><span style={{ width: `${completion.percent}%` }}/></div><p>{completion.have}개 확보 · {Math.max(0, completion.total - completion.have)}개 보완·확인</p></div>
            </div>

            <div className="result-grid">
              <div className="result-primary">
                <div className="panel-heading"><div><span>내가 올린 파일</span><h2>이 업무에 필요한 파일인지 확인했어요</h2></div><b>{uploadedRows.length}개 파일</b></div>
                <div className="document-results">
                  {uploadedRows.map((row) => {
                    const apiDocument = analysis?.documents.find((document) => document.document_id === row.key);
                    return (
                      <article className={`document-result-card ${row.tone}`} key={row.key}>
                        <span className="document-result-icon"><Icon name="document"/></span>
                        <div className="document-result-copy">
                          <div><h3>{row.name}</h3><span className={`status-badge ${row.tone}`}>{row.status}</span></div>
                          {apiDocument && <p className={`document-relevance ${apiDocument.status === "UNNECESSARY" ? "unused" : apiDocument.doc_type === null ? "unknown" : "required"}`}>{uploadedRelevanceLabel(apiDocument)}</p>}
                          <p className="document-meta">{row.meta}</p><p>{row.note}</p>
                          {apiDocument?.needs_user_confirm && (
                            <div className="classification-confirm">
                              <label htmlFor={`doc-type-${apiDocument.document_id}`}>이 문서가 무엇인지 확인해주세요</label>
                              <div><select id={`doc-type-${apiDocument.document_id}`} value={documentTypes[apiDocument.document_id] ?? apiDocument.doc_type ?? ""} onChange={(event) => setDocumentTypes((current) => ({ ...current, [apiDocument.document_id]: event.target.value }))}><option value="">문서 종류 선택</option>{DOCUMENT_TYPE_OPTIONS.map((option) => <option value={option.docType} key={option.docType}>{option.label}</option>)}</select><button type="button" disabled={confirmingId === apiDocument.document_id || !(documentTypes[apiDocument.document_id] ?? apiDocument.doc_type)} onClick={() => confirmClassification(apiDocument.document_id, apiDocument.doc_type)}>{confirmingId === apiDocument.document_id ? "반영 중…" : "이 종류가 맞아요"}</button></div>
                              <small>확인은 문서 종류에만 반영되며 진위·내용·발급일을 승인하지 않습니다.</small>
                            </div>
                          )}
                        </div>
                      </article>
                    );
                  })}
                </div>
              </div>

              <aside className="completion-panel">
                <div className="panel-heading compact"><div><span>부족한 서류 해결</span><h2>추가 서류와 발급 방법</h2></div><Icon name="spark"/></div>
                {analysis?.completion_plan ? (
                  <>
                    <div className="selected-bundle"><span>가장 가까운 증빙 조합</span><b>{analysis.completion_plan.bundle_label}</b><small>{statusLabels[analysis.completion_plan.status]}</small></div>
                    <div className="guide-list">
                      {analysis.completion_plan.documents.filter((guide) => guide.status !== "READY").map((guide) => (
                          <details className="guide-card" key={guide.doc_type} open>
                            <summary><span className={`guide-check ${toneForStatus(guide.status)}`}><Icon name="chevron"/></span><span><b>{guide.label_ko}</b><small>{guide.acquisition.title}</small></span><span className={`status-badge ${toneForStatus(guide.status)}`}>{statusLabels[guide.status]}</span></summary>
                            <div className="guide-body">
                              <p className="guide-reason">{guide.reason}</p>
                              <div className="guide-channel"><span>어디서</span><b>{acquisitionChannelLabel(guide.acquisition.channel)}</b></div>
                              <p className="guide-description">{guide.acquisition.description}</p>
                              {guide.acquisition.steps.length > 0 && <><h4>이렇게 준비하세요</h4><ol>{guide.acquisition.steps.map((step) => <li key={step}>{step}</li>)}</ol></>}
                              <div className="guide-format"><span>준비 형태</span><b>{guide.submission_label}</b></div>
                              {guide.checklist.length > 0 && <><h4>확인할 내용</h4><ul>{guide.checklist.map((item) => <li key={item}><Icon name="check"/>{item}</li>)}</ul></>}
                              {guide.acquisition.url && <a href={guide.acquisition.url} target="_blank" rel="noreferrer">{guide.acquisition.action_label ?? "공식 발급 경로 열기"} <Icon name="external"/></a>}
                              <p className="guide-source">근거: {guide.acquisition.source.title ?? "공식 안내"}{guide.acquisition.source.last_checked ? ` · ${guide.acquisition.source.last_checked} 확인` : ""}</p>
                            </div>
                          </details>
                        ))}
                      {analysis.completion_plan.documents.every((guide) => guide.status === "READY") && <div className="all-documents-ready"><Icon name="check"/><div><b>추가로 발급할 서류가 없어요</b><p>선택된 증빙 조합에 필요한 문서를 모두 찾았습니다.</p></div></div>}
                    </div>
                    {officialBundles.length > 1 && (
                      <section className="alternative-bundles" aria-labelledby="alternative-bundles-title">
                        <div className="alternative-bundles-head">
                          <span>다른 인정 방법</span>
                          <h3 id="alternative-bundles-title">아래 조합을 전부 준비할 필요는 없어요</h3>
                          <p>카카오뱅크가 안내한 증빙 중 본인에게 가능한 <b>한 가지 조합</b>만 선택하면 됩니다. 현재 업로드한 파일과 가장 가까운 조합을 먼저 추천했어요.</p>
                        </div>
                        <div className="bundle-option-list">
                          {officialBundles.map((bundle) => {
                            const selected = bundle.bundle_code === analysis.completion_plan?.bundle_code;
                            const missing = bundle.missing_document_types;
                            const readyCount = bundle.document_types.length - missing.length;
                            return (
                              <article className={`bundle-option ${selected ? "selected" : ""}`} key={bundle.bundle_code}>
                                <div className="bundle-option-title">
                                  <span className="bundle-option-icon">{selected ? <Icon name="spark"/> : <Icon name="document"/>}</span>
                                  <div><b>{bundle.label_ko}</b><small>{bundleDescriptions[bundle.bundle_code] ?? (bundle.document_types.length === 1 ? "이 서류 하나로 신청하는 선택지" : `${bundle.document_types.length}개 서류를 함께 내는 선택지`)}</small></div>
                                  {selected && <em>현재 추천</em>}
                                </div>
                                <ul>
                                  {bundle.document_types.map((docType) => {
                                    const isMissing = missing.includes(docType);
                                    return <li className={isMissing ? "missing" : "ready"} key={docType}><Icon name={isMissing ? "arrow" : "check"}/><span>{DOC_LABELS[docType] ?? docType}</span><small>{isMissing ? "준비 필요" : "업로드됨"}</small></li>;
                                  })}
                                </ul>
                                <p>{missing.length === 0 ? "이 조합의 서류를 모두 찾았어요." : readyCount > 0 ? `${missing.length}개만 더 준비하면 이 조합을 사용할 수 있어요.` : "현재 가진 파일과 겹치지 않는 다른 선택지예요."}</p>
                              </article>
                            );
                          })}
                        </div>
                        <a className="bundle-source-link" href={analysis.completion_plan.submission.url ?? "https://blog.kakaobank.com/posts/service-limit-account"} target="_blank" rel="noreferrer">카카오뱅크 공식 인정 서류 전체 보기 <Icon name="external"/></a>
                      </section>
                    )}
                    {analysis.completion_plan.preparations.length > 0 && <div className="preparation-list"><h3>함께 챙길 것</h3><ul>{analysis.completion_plan.preparations.map((item) => <li key={item.code}><Icon name="check"/><span><b>{item.label_ko}</b>{item.notes && <small>{item.notes}</small>}</span></li>)}</ul></div>}
                    <div className="submission-guide"><span>제출 순서</span><h3>{analysis.completion_plan.submission.title}</h3><p>{analysis.completion_plan.submission.description}</p><ol>{analysis.completion_plan.submission.steps.map((step) => <li key={step}>{step}</li>)}</ol>{analysis.completion_plan.submission.expected_review && <p className="review-time"><Icon name="info"/>{analysis.completion_plan.submission.expected_review}</p>}{analysis.completion_plan.submission.url && <a href={analysis.completion_plan.submission.url} target="_blank" rel="noreferrer">{analysis.completion_plan.submission.action_label ?? "공식 제출 안내 열기"} <Icon name="external"/></a>}</div>
                  </>
                ) : hasResidentCopy && needsManagementFee ? (
                  <div className="fallback-kit">
                    <div className="selected-bundle"><span>현재 가장 가까운 증빙 조합</span><b>관리비 고지서 + 주민등록표 등본</b><small>관리비 고지서 보완 필요</small></div>
                    <div className="fallback-guide">
                      <span className="guide-check needed"><Icon name="chevron"/></span>
                      <div><b>관리비 고지서를 확보하세요</b><p>관리사무소 또는 이용 중인 관리비 앱·웹에서 현재 청구분을 요청하고, 입주자명·주소·동호수·청구금액을 확인하세요.</p></div>
                    </div>
                    <div className="fallback-guide">
                      <span className="guide-check needed"><Icon name="check"/></span>
                      <div><b>등본의 현재 주소를 확인하세요</b><p>관리비 고지서의 주소와 같은지 확인하고 원본을 출력해 촬영할 준비를 합니다.</p><a href="https://www.gov.kr/mw/AA020InfoCappView.do?CappBizCD=13100000015&tp_seq=04" target="_blank" rel="noreferrer">정부24 발급 페이지 <Icon name="external"/></a></div>
                    </div>
                    <div className="submission-guide"><span>제출 순서</span><h3>카카오뱅크 앱에서 촬영 제출</h3><ol><li>계좌 관리에서 한도 해제 메뉴를 엽니다.</li><li>해제 신청하기를 선택합니다.</li><li>준비한 원본 서류를 안내에 따라 촬영해 제출합니다.</li></ol><p className="review-time"><Icon name="info"/>서류 제출 후 심사·통보까지 2~3영업일이 걸릴 수 있어요.</p><a href="https://blog.kakaobank.com/posts/service-limit-account" target="_blank" rel="noreferrer">카카오뱅크 공식 안내 <Icon name="external"/></a></div>
                  </div>
                ) : (
                  <div className="empty-kit"><Icon name="info"/><h3>제출 조합을 한 번 더 골라야 해요</h3><p>확인이 필요한 문서 종류를 먼저 선택하면 6가지 인정 증빙 중 가장 가까운 조합과 발급 순서를 정리합니다.</p><a href="https://blog.kakaobank.com/posts/service-limit-account" target="_blank" rel="noreferrer">카카오뱅크 공식 안내 <Icon name="external"/></a></div>
                )}
              </aside>
            </div>

            {analysis?.warnings.length ? <details className="warnings-panel"><summary><Icon name="alert"/> 확인해야 할 제한사항 {analysis.warnings.length}개</summary><ul>{analysis.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul></details> : null}
            <div className="result-actions">
              <button className="secondary-action" type="button" onClick={resetSession}><Icon name="trash"/> 결과와 세션 삭제</button>
              {analysis && <div className="kit-download-action"><button className="secondary-action" type="button" disabled={downloadingKit} onClick={downloadKit}><Icon name="download"/> {downloadingKit ? "키트 생성 중…" : "준비 안내 ZIP 받기"}</button><small>공식 경로·체크리스트만 포함 · 업로드 원본 미포함</small></div>}
              <button className="primary-action" type="button" onClick={resetSession}>다른 서류 다시 확인 <Icon name="refresh"/></button>
            </div>
          </section>
        )}
      </main>
      <footer className="product-footer"><span>ProofBridge</span><p>은행의 최종 심사·승인을 대신하지 않습니다. 공식 출처 기반의 서류 준비 사전 점검 서비스입니다.</p></footer>
    </div>
  );
}
