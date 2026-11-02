"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { HugeLogo } from "@/components/Brand";
import { PasswordChecklist, passwordRules } from "@/components/PasswordChecklist";
import { useApp } from "@/components/Providers";
import { Field, Loading } from "@/components/Ui";
import { api, ApiError, loginPath } from "@/lib/api";

/** S-C04 관리자 초기 비밀번호 변경. 건너뛸 수 없다 */
export default function PasswordChangePage() {
    const router = useRouter();
    const { me, meLoaded, refreshMe, toast } = useApp();
    const [current, setCurrent] = useState("");
    const [next, setNext] = useState("");
    const [confirm, setConfirm] = useState("");
    const [error, setError] = useState<string | null>(null);
    const [busy, setBusy] = useState(false);

    useEffect(() => {
        if (meLoaded && !me) router.replace(loginPath());
    }, [me, meLoaded, router]);

    if (!me) return <Loading />;
    const valid = current && passwordRules(next, me.email).every((r) => r.ok) && next === confirm;

    async function submit(event: React.FormEvent) {
        event.preventDefault();
        setBusy(true);
        setError(null);
        try {
            await api("/auth/password-change", { body: { current_password: current, new_password: next } });
            const updated = await refreshMe();
            toast("ok", "비밀번호를 변경했습니다");
            router.replace(updated?.role === "admin" ? "/admin/postings" : "/jobs");
        } catch (err) {
            setError((err as ApiError).message);
        } finally {
            setBusy(false);
        }
    }

    return (
        <main className="narrow">
            <form className="card stack" style={{ padding: 32 }} onSubmit={submit} noValidate>
                <HugeLogo height={32} href="/password/change" />
                <h1 style={{ fontSize: 22 }}>{me.password_change_required ? "처음 로그인하셨습니다. 비밀번호를 변경해 주세요." : "비밀번호 변경"}</h1>
                <Field label={me.password_change_required ? "현재(초기) 비밀번호" : "현재 비밀번호"} required>
                    <input className="input" type="password" value={current} onChange={(e) => setCurrent(e.target.value)} autoComplete="current-password" />
                </Field>
                <Field label="새 비밀번호" required>
                    <input className="input" type="password" value={next} onChange={(e) => setNext(e.target.value)} autoComplete="new-password" />
                </Field>
                <PasswordChecklist password={next} email={me.email} />
                <Field label="새 비밀번호 확인" required error={confirm && confirm !== next ? "비밀번호가 일치하지 않습니다" : null}>
                    <input className="input" type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} autoComplete="new-password" />
                </Field>
                {error && <div className="notice notice-error" role="alert">{error}</div>}
                <button type="submit" className="btn btn-primary btn-lg" disabled={!valid || busy}>{busy && <span className="spinner" />}변경하고 시작하기</button>
            </form>
        </main>
    );
}
