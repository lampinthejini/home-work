"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { HugeLogo } from "@/components/Brand";
import { PasswordChecklist, passwordRules } from "@/components/PasswordChecklist";
import { useApp } from "@/components/Providers";
import { Field } from "@/components/Ui";
import { api, ApiError } from "@/lib/api";

/** S-C03 ② 새 비밀번호 정하기. 링크는 30분, 한 번만 쓸 수 있다 */
function ResetForm() {
    const router = useRouter();
    const params = useSearchParams();
    const { toast } = useApp();
    const token = params.get("token") ?? "";
    const [next, setNext] = useState("");
    const [confirm, setConfirm] = useState("");
    const [error, setError] = useState<string | null>(null);
    const [expired, setExpired] = useState(!token);
    const [busy, setBusy] = useState(false);
    // 이메일은 링크에 없어서 '이메일 아이디 포함 금지'는 서버가 확인한다
    const valid = passwordRules(next, "").every((r) => r.ok) && next === confirm;

    async function submit(event: React.FormEvent) {
        event.preventDefault();
        setBusy(true);
        setError(null);
        try {
            await api("/auth/password-reset/confirm", { body: { token, new_password: next } });
            toast("ok", "비밀번호를 변경했습니다");
            router.replace("/login?reset=1");
        } catch (err) {
            if ((err as ApiError).code === "TOKEN_EXPIRED") setExpired(true);
            else setError((err as ApiError).message);
        } finally {
            setBusy(false);
        }
    }

    if (expired) {
        return (
            <div className="card stack" style={{ padding: 32 }}>
                <HugeLogo height={32} />
                <h1 style={{ fontSize: 22 }}>링크가 만료되었습니다(30분)</h1>
                <p className="small muted" style={{ margin: 0 }}>재설정 링크는 30분 동안 한 번만 쓸 수 있습니다. 새 링크를 받아 주세요.</p>
                <Link href="/password/forgot" className="btn btn-primary btn-lg">다시 요청하기</Link>
            </div>
        );
    }
    return (
        <form className="card stack" style={{ padding: 32 }} onSubmit={submit} noValidate>
            <HugeLogo height={32} />
            <h1 style={{ fontSize: 22 }}>새 비밀번호 정하기</h1>
            <Field label="새 비밀번호" required>
                <input className="input" type="password" value={next} onChange={(e) => setNext(e.target.value)} autoComplete="new-password" />
            </Field>
            <PasswordChecklist password={next} email="" />
            <Field label="새 비밀번호 확인" required error={confirm && confirm !== next ? "비밀번호가 일치하지 않습니다" : null}>
                <input className="input" type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} autoComplete="new-password" />
            </Field>
            {error && <div className="notice notice-error" role="alert">⚠ {error}</div>}
            <button type="submit" className="btn btn-primary btn-lg" disabled={!valid || busy}>{busy && <span className="spinner" />}변경하기</button>
            <p className="tiny muted" style={{ margin: 0 }}>바꾸면 다른 기기의 로그인도 모두 끊깁니다.</p>
        </form>
    );
}

export default function PasswordResetPage() {
    return <main className="narrow"><Suspense><ResetForm /></Suspense></main>;
}
