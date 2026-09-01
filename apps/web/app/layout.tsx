import type { Metadata } from "next";
import "./globals.css";

const description =
  "하려는 금융업무를 편하게 입력하면 공식 출처 기반 RAG로 절차를 연결하고, 증빙의 누락·확인 항목과 발급 경로를 정리하는 ProofBridge입니다.";
const publicOrigin = process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000";

export function generateMetadata(): Metadata {
  return {
    metadataBase: new URL(publicOrigin),
    title: "ProofBridge | 금융업무 증빙 사전점검",
    description,
    openGraph: {
      title: "ProofBridge",
      description,
      type: "website",
      images: [{ url: "/og.png", width: 1536, height: 910, alt: "흩어진 서류를 준비 완료 키트로 잇는 ProofBridge" }],
    },
    twitter: { card: "summary_large_image", title: "ProofBridge", description, images: ["/og.png"] },
  };
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ko">
      <body>{children}</body>
    </html>
  );
}
