export const SERVICES = [
  {
    service_id: "limit_account_release",
    label_ko: "한도제한계좌 해제",
    description: "금융거래 목적을 증빙하여 계좌에 걸린 거래 제한을 해제하는 업무. 일반 이체한도 설정 변경, 대출한도 증액, 카드한도 변경과 구분한다.",
  },
  {
    service_id: "inheritance_inquiry",
    label_ko: "상속인 금융거래 조회",
    description: "돌아가신 가족에게 어떤 금융재산이나 채무가 있는지, 어느 금융기관과 거래했는지 확인하는 업무. 예금 지급이나 해지 자체와 구분한다.",
  },
  {
    service_id: "inheritance_deposit_payment",
    label_ko: "상속예금 지급",
    description: "돌아가신 가족 명의의 예금을 상속인이 지급받거나 해지 또는 명의변경하는 업무. 생전 증여, 상속포기, 부동산 등기, 상속세 신고는 이 업무가 아니다.",
  },
] as const;

export type ServiceId = (typeof SERVICES)[number]["service_id"];

export const BANKS = [
  { bank_code: "kakaobank", label_ko: "카카오뱅크", aliases: ["카카오뱅크", "카뱅", "카카오은행", "kakaobank"] },
  { bank_code: "kb", label_ko: "KB국민은행", aliases: ["KB국민은행", "국민은행", "국민", "KB", "케이비"] },
  { bank_code: "woori", label_ko: "우리은행", aliases: ["우리은행", "우리뱅크", "woori"] },
  { bank_code: "hana", label_ko: "하나은행", aliases: ["하나은행", "하나뱅크", "hana"] },
  { bank_code: "shinhan", label_ko: "신한은행", aliases: ["신한은행", "신한", "shinhan"] },
  { bank_code: "nh", label_ko: "NH농협은행", aliases: ["NH농협은행", "농협은행", "농협", "NH"] },
  { bank_code: "ibk", label_ko: "IBK기업은행", aliases: ["IBK기업은행", "기업은행", "IBK"] },
  { bank_code: "toss", label_ko: "토스뱅크", aliases: ["토스뱅크", "토스", "toss"] },
  { bank_code: "kbank", label_ko: "케이뱅크", aliases: ["케이뱅크", "케뱅", "kbank"] },
] as const;

export interface CatalogTask {
  task_id: string;
  bank_code: string;
  service_id: ServiceId;
  support_status: "SUPPORTED" | "GUIDE_ONLY";
  source_url: string;
  source_title: string;
  last_checked: string;
}

// These entries identify official services, not document requirements or approval rules.
export const TASK_CATALOG: readonly CatalogTask[] = [
  {
    task_id: "kakaobank.limit_account_release",
    bank_code: "kakaobank",
    service_id: "limit_account_release",
    support_status: "SUPPORTED",
    source_url: "https://blog.kakaobank.com/posts/service-limit-account",
    source_title: "카카오뱅크 한도계좌 안내",
    last_checked: "2026-09-06",
  },
  {
    task_id: "woori.limit_account_release",
    bank_code: "woori",
    service_id: "limit_account_release",
    support_status: "GUIDE_ONLY",
    source_url: "https://spot.wooribank.com/pot/Dream?ARTICLE_ID=46497&BOARD_ID=B00445&bbsMode=view&withyou=CQCNT0009",
    source_title: "우리은행 금융거래 목적 확인 안내",
    last_checked: "2026-09-06",
  },
  {
    task_id: "kb.inheritance_inquiry",
    bank_code: "kb",
    service_id: "inheritance_inquiry",
    support_status: "GUIDE_ONLY",
    source_url: "https://obank.kbstar.com/quics?page=C033712",
    source_title: "KB국민은행 상속인 금융거래 조회 서비스",
    last_checked: "2026-09-06",
  },
  {
    task_id: "kb.inheritance_deposit_payment",
    bank_code: "kb",
    service_id: "inheritance_deposit_payment",
    support_status: "GUIDE_ONLY",
    source_url: "https://obank1.kbstar.com/quics?page=C112064",
    source_title: "KB국민은행 상속예금 관련 안내",
    last_checked: "2026-09-06",
  },
];
