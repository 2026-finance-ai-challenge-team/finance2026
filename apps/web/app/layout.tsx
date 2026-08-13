import type { Metadata } from "next";
import { headers } from "next/headers";
import "./globals.css";

const description =
  "공공 마이데이터로 보낼 자료와 직접 준비할 증빙을 나누고, 디지털·인쇄·방문 준비 키트로 완성하는 ProofBridge 기획 데모입니다.";

export async function generateMetadata(): Promise<Metadata> {
  const requestHeaders = await headers();
  const host = requestHeaders.get("x-forwarded-host") ?? requestHeaders.get("host") ?? "localhost:3000";
  const protocol = requestHeaders.get("x-forwarded-proto") ?? (host.startsWith("localhost") ? "http" : "https");
  const image = `${protocol}://${host}/og.png`;

  return {
    title: "ProofBridge | 금융업무 준비 데모",
    description,
    openGraph: {
      title: "ProofBridge",
      description,
      type: "website",
      images: [{ url: image, width: 1536, height: 910, alt: "흩어진 서류를 준비 완료 키트로 잇는 ProofBridge" }],
    },
    twitter: { card: "summary_large_image", title: "ProofBridge", description, images: [image] },
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
