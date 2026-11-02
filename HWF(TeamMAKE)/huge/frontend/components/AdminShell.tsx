"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import type { ReactNode } from "react";

import { HugeLogo, TeamCredit } from "@/components/Brand";
import { NotificationBell } from "@/components/NotificationBell";
import { useApp } from "@/components/Providers";
import { DesktopOnly, useGuard } from "@/components/Shell";
import { Loading } from "@/components/Ui";
import { api } from "@/lib/api";

const MENU = [
    { href: "/admin/postings", icon: "▤", label: "공고 관리" },
    { href: "/admin/applicants", icon: "▥", label: "지원자" },
    { href: "/admin/next-stage", icon: "▦", label: "다음 전형" },
    { href: "/admin/questions", icon: "▨", label: "질문 관리" },
    { href: "/admin/dashboard", icon: "▧", label: "대시보드" },
    { href: "/admin/settings", icon: "⚙", label: "운영 설정" },
];

export function AdminShell({ title, actions, children }: { title: string; actions?: ReactNode; children: ReactNode }) {
    const me = useGuard("admin");
    const pathname = usePathname();
    const router = useRouter();
    const { refreshMe } = useApp();

    async function logout() {
        await api("/auth/logout", { method: "POST" }).catch(() => undefined);
        await refreshMe();
        router.push("/login");
    }

    if (!me) return <Loading />;
    return (
        <DesktopOnly>
            <div className="admin">
                <aside className="sidebar" aria-label="관리자 메뉴">
                    <HugeLogo href="/admin/postings" white height={30} />
                    {MENU.map((m) => (
                        <Link key={m.href} href={m.href} aria-current={pathname.startsWith(m.href) ? "page" : undefined}><span aria-hidden>{m.icon}</span>{m.label}</Link>
                    ))}
                    <span className="grow" />
                    <div style={{ padding: "0 12px" }}><TeamCredit dark /></div>
                </aside>
                <div className="admin-main">
                    <div className="admin-top">
                        <h1 style={{ fontSize: 20, margin: 0 }}>{title}</h1>
                        <div className="row">
                            {actions}
                            <NotificationBell />
                            <span className="small muted">👤 {me.name}</span>
                            <Link className="btn btn-text btn-sm" href="/password/change">비밀번호 변경</Link>
                            <button type="button" className="btn btn-secondary btn-sm" onClick={logout}>로그아웃</button>
                        </div>
                    </div>
                    <div className="admin-body">{children}</div>
                </div>
            </div>
        </DesktopOnly>
    );
}
