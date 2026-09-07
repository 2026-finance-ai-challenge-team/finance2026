import type { Metadata } from "next";
import "./globals.css";

const description =
  "하려는 금융업무를 입력하면 필요한 증빙과 부족한 서류, 공식 발급 경로를 한 번에 정리하는 FORM:E입니다.";
const publicOrigin = process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000";

export function generateMetadata(): Metadata {
  return {
    metadataBase: new URL(publicOrigin),
    title: "FORM:E | 금융업무 서류 사전점검",
    description,
    openGraph: {
      title: "FORM:E",
      description,
      type: "website",
      images: [{ url: "/og.png", width: 1536, height: 910, alt: "금융업무 서류 준비를 돕는 FORM:E" }],
    },
    twitter: { card: "summary_large_image", title: "FORM:E", description, images: ["/og.png"] },
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
