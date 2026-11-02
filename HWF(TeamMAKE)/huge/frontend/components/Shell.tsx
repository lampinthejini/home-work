"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";

import { HugeLogo, TeamCredit } from "@/components/Brand";
import { NotificationBell } from "@/components/NotificationBell";
import { useApp, type Me } from "@/components/Providers";
import { Loading } from "@/components/Ui";
import { api, loginPath } from "@/lib/api";

export function Gnb() {
    const { me, refreshMe } = useApp();
    const pathname = usePathname();
    const router = useRouter();

    async function logout() {
        await api("/auth/logout", { method: "POST" }).catch(() => undefined);
        await refreshMe();
        router.push("/jobs");
    }

    return (
        <header className="gnb">
            <div className="container">
                <HugeLogo />
                <nav aria-label="주 메뉴">
                    <Link href="/jobs" aria-current={pathname.startsWith("/jobs") ? "page" : undefined}>채용 공고</Link>
                    {me?.role === "applicant" && <Link href="/mypage" aria-current={pathname.startsWith("/mypage") ? "page" : undefined}>마이페이지</Link>}
                    {me?.role === "admin" && <Link href="/admin/postings">관리자</Link>}
                </nav>
                <div className="spacer" />
                {me ? (
                    <div className="row">
                        {!me.password_change_required && <NotificationBell />}
                        <span className="small muted">{me.name}님</span>
                        <button type="button" className="btn btn-secondary btn-sm" onClick={logout}>로그아웃</button>
                    </div>
                ) : (
                    <div className="row">
                        <Link className="btn btn-text" href={`/login?next=${encodeURIComponent(pathname)}`}>로그인</Link>
                        <Link className="btn btn-primary btn-sm" href="/signup">회원가입</Link>
                    </div>
                )}
            </div>
        </header>
    );
}

export function Footer() {
    return (
        <footer className="footer">
            <div className="container">
                <span className="tiny muted">Huge — AI 1차 채용면접 플랫폼 · AI 평가는 참고용 1차 전형에만 쓰입니다</span>
                <TeamCredit />
            </div>
        </footer>
    );
}

export function SiteShell({ children }: { children: ReactNode }) {
    return (
        <>
            <Gnb />
            <MobileBanner />
            <main className="page">{children}</main>
            <Footer />
        </>
    );
}

/** 라우트 가드 (§2.3). 역할이 다르면 그 역할 홈으로, 로그인이 없으면 /login?next= */
export function useGuard(role: "applicant" | "admin"): Me | null {
    const { me, meLoaded, toast } = useApp();
    const router = useRouter();
    const ok = meLoaded && me !== null && me.role === role && !me.password_change_required;

    useEffect(() => {
        if (!meLoaded) return;
        if (me === null) {
            router.replace(loginPath());
        } else if (me.password_change_required) {
            router.replace("/password/change");
        } else if (me.role !== role) {
            if (me.role === "applicant") toast("warn", "접근 권한이 없습니다");
            router.replace(me.role === "admin" ? "/admin/postings" : "/jobs");
        }
    }, [me, meLoaded, role, router, toast]);

    return ok ? me : null;
}

export function Guarded({ role, children }: { role: "applicant" | "admin"; children: ReactNode }) {
    const me = useGuard(role);
    return me ? <>{children}</> : <Loading />;
}

/** 지원 절차·응시·관리자 화면은 PC 전용 (§4.8, G-12) */
export function DesktopOnly({ children }: { children: ReactNode }) {
    const [mobile, setMobile] = useState<boolean | null>(null);

    useEffect(() => {
        const ua = navigator.userAgent;
        const touchMac = /Macintosh/.test(ua) && navigator.maxTouchPoints > 1;
        // 마운트 뒤 한 번 기기 판별 (서버 렌더에는 navigator 가 없다)
        // eslint-disable-next-line react-hooks/set-state-in-effect
        setMobile(/Mobi|Android|iPhone|iPad|Tablet/i.test(ua) || touchMac);
    }, []);

    if (mobile === null) return null;
    if (!mobile) return <>{children}</>;
    return (
        <div className="narrow center stack">
            <h2>PC에서 이용해 주세요</h2>
            <p className="muted">지원 절차와 AI 면접은 카메라·마이크와 전체 화면이 필요해 PC의 Chrome 또는 Edge 최신 버전에서만 진행할 수 있습니다.</p>
            <Link className="btn btn-secondary" href="/jobs">공고 목록으로</Link>
        </div>
    );
}

/** 모바일에서만 보이는 닫을 수 없는 안내 (§4.8) */
export function MobileBanner() {
    return <div className="notice notice-warn mobile-only" role="note">모바일 기기에서는 지원·응시를 할 수 없습니다. PC의 Chrome 또는 Edge에서 이용해 주세요.</div>;
}
