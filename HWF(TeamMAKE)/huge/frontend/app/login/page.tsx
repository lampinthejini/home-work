"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { HugeLogo, Mascot, TeamCredit } from "@/components/Brand";
import { useApp } from "@/components/Providers";
import { Field } from "@/components/Ui";
import { api, ApiError } from "@/lib/api";

type LoginResponse = { role: "applicant" | "admin"; redirect: string };

function LoginForm() {
    const params = useSearchParams();
    const router = useRouter();
    const { me, meLoaded, refreshMe } = useApp();
    const next = params.get("next");
    const [email, setEmail] = useState(params.get("email") ?? "");
    const [password, setPassword] = useState("");
    const [show, setShow] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [busy, setBusy] = useState(false);

    useEffect(() => {
        if (meLoaded && me) router.replace(me.role === "admin" ? "/admin/postings" : "/jobs");
    }, [me, meLoaded, router]);

    async function submit(event: React.FormEvent) {
        event.preventDefault();
        if (!email.trim() || !password) {
            setError("이메일과 비밀번호를 입력해 주세요.");
            return;
        }
        setBusy(true);
        setError(null);
        try {
            const res = await api<LoginResponse>("/auth/login", { body: { email, password, next } });
            await refreshMe();
            router.replace(res.redirect);
        } catch (err) {
            setError((err as ApiError).message);
        } finally {
            setBusy(false);
        }
    }

    return (
        <main className="narrow">
            <div className="card stack" style={{ padding: 32 }}>
                <div className="center stack">
                    <div style={{ display: "flex", justifyContent: "center" }}><HugeLogo height={40} /></div>
                    <p className="muted">AI가 함께하는 더 나은 채용의 시작</p>
                </div>
                {params.get("joined") && <div className="notice notice-ok" role="status">가입이 완료되었습니다. 로그인해 주세요.</div>}
                {params.get("reset") && <div className="notice notice-ok" role="status">비밀번호를 변경했습니다. 새 비밀번호로 로그인해 주세요.</div>}
                <form className="stack" onSubmit={submit} noValidate>
                    <Field label="이메일">
                        <input className="input" type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="name@example.com" />
                    </Field>
                    <Field label="비밀번호">
                        <div style={{ position: "relative" }}>
                            <input className="input" type={show ? "text" : "password"} autoComplete="current-password" value={password}
                                onChange={(e) => setPassword(e.target.value)} style={{ paddingRight: 64 }} />
                            <button type="button" className="btn btn-text btn-sm" style={{ position: "absolute", right: 6, top: 10 }}
                                onClick={() => setShow((v) => !v)} aria-pressed={show}>{show ? "숨기기" : "보기"}</button>
                        </div>
                    </Field>
                    {error && <div className="notice notice-error" role="alert">⚠ {error}</div>}
                    <button type="submit" className="btn btn-primary btn-lg" disabled={busy} style={{ width: "100%" }}>
                        {busy && <span className="spinner" />}로그인
                    </button>
                </form>
                <div className="row between small">
                    <Link href="/password/forgot">비밀번호 찾기</Link>
                    <span>처음이신가요? <Link href={`/signup${next ? `?next=${encodeURIComponent(next)}` : ""}`}>회원가입</Link></span>
                </div>
                <hr style={{ border: 0, borderTop: "1px solid var(--color-line)", margin: "8px 0" }} />
                <p className="tiny muted center">관리자도 이 화면에서 로그인합니다.</p>
            </div>
            <div className="row" style={{ justifyContent: "center", marginTop: 24, gap: 16 }}>
                <Mascot name="01-guide" size={72} />
                <TeamCredit />
            </div>
        </main>
    );
}

export default function LoginPage() {
    return <Suspense><LoginForm /></Suspense>;
}
