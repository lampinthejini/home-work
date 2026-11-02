"use client";

import Link from "next/link";
import { useState } from "react";

import { HugeLogo } from "@/components/Brand";
import { Field } from "@/components/Ui";
import { api, ApiError } from "@/lib/api";

/** S-C03 ① 재설정 링크 요청. 가입 여부와 상관없이 같은 안내를 보여 준다 */
export default function PasswordForgotPage() {
    const [email, setEmail] = useState("");
    const [sent, setSent] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [busy, setBusy] = useState(false);
    const valid = /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email.trim());

    async function submit(event: React.FormEvent) {
        event.preventDefault();
        setBusy(true);
        setError(null);
        try {
            await api("/auth/password-reset", { body: { email: email.trim() } });
            setSent(true);
        } catch (err) {
            setError((err as ApiError).message);
        } finally {
            setBusy(false);
        }
    }

    return (
        <main className="narrow">
            <form className="card stack" style={{ padding: 32 }} onSubmit={submit} noValidate>
                <HugeLogo height={32} />
                <h1 style={{ fontSize: 22 }}>비밀번호 찾기</h1>
                {sent ? (
                    <div className="notice notice-ok" role="status">가입된 계정이면 재설정 링크를 보냈습니다. 30분 안에 열어 주세요.</div>
                ) : (
                    <p className="small muted" style={{ margin: 0 }}>가입한 이메일을 입력하면 비밀번호를 다시 정할 수 있는 링크를 보내 드립니다.</p>
                )}
                <Field label="이메일" required>
                    <input className="input" type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="name@example.com" />
                </Field>
                {error && <div className="notice notice-error" role="alert">⚠ {error}</div>}
                <button type="submit" className="btn btn-primary btn-lg" disabled={!valid || busy}>{busy && <span className="spinner" />}{sent ? "다시 보내기" : "재설정 링크 받기"}</button>
                <Link href="/login" className="small">← 로그인으로</Link>
            </form>
        </main>
    );
}
