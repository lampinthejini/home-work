/* eslint-disable @next/next/no-img-element -- 브랜드 이미지는 public/brand 의 고정 크기 webp 라 next/image 최적화가 필요 없다 */
import Link from "next/link";

/** Huge 로고 (프로그램 이름, 2026-10-30 사용자 확정) */
export function HugeLogo({ href = "/jobs", white = false, height = 32 }: { href?: string | null; white?: boolean; height?: number }) {
    const base = white ? "/brand/huge-wordmark-white" : "/brand/huge-wordmark";
    // 응시 화면은 링크를 두지 않는다 (§4.1 ExamLayout)
    if (href === null) {
        return <span className="brand"><img src={`${base}.webp`} srcSet={`${base}.webp 1x, ${base}@2x.webp 2x`} alt="Huge" height={height} width={height * 3} /></span>;
    }
    return (
        <Link href={href} className="brand" aria-label="Huge 홈">
            <img src={`${base}.webp`} srcSet={`${base}.webp 1x, ${base}@2x.webp 2x`} alt="" height={height} width={height * 3} />
        </Link>
    );
}

/** 'Team AIIT' 표시 (개발 팀 크레딧) */
export function TeamCredit({ dark = false }: { dark?: boolean }) {
    return (
        <span className="team-credit" style={dark ? { color: "#94A3B8" } : undefined}>
            <img src="/brand/aiit-wordmark.webp" srcSet="/brand/aiit-wordmark.webp 1x, /brand/aiit-wordmark@2x.webp 2x" alt="" width={44} height={24}
                style={dark ? { filter: "invert(1) brightness(1.6)" } : undefined} />
            <span>Made by <strong>Team AIIT</strong> · AI Interview Training</span>
        </span>
    );
}

export function Mascot({ name, size = 160, alt = "" }: { name: "01-guide" | "02-analysis" | "03-evaluation" | "04-discovery" | "05-report" | "06-better-hiring"; size?: number; alt?: string }) {
    return <img src={`/brand/${name}.webp`} alt={alt} width={size} height={Math.round(size * 0.92)} style={{ objectFit: "contain" }} />;
}
