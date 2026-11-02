import "pretendard/dist/web/variable/pretendardvariable-dynamic-subset.css";
import "./globals.css";

import type { Metadata } from "next";
import type { ReactNode } from "react";

import { Providers } from "@/components/Providers";

export const metadata: Metadata = {
    title: { default: "Huge — AI 채용면접", template: "%s · Huge" },
    description: "AI가 1차 면접을 진행하는 채용 플랫폼 Huge (Team AIIT)",
    openGraph: { title: "Huge — AI 채용면접", description: "AI 1차 면접 플랫폼 · Team AIIT", images: ["/brand/og-image.jpg"] },
    robots: { index: false, follow: false },
};

export default function RootLayout({ children }: { children: ReactNode }) {
    return (
        <html lang="ko">
            <body>
                <Providers>{children}</Providers>
            </body>
        </html>
    );
}
