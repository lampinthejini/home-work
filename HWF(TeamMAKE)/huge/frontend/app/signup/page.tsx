"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { HugeLogo } from "@/components/Brand";
import { PasswordChecklist, passwordRules } from "@/components/PasswordChecklist";
import { Field } from "@/components/Ui";
import { api, ApiError } from "@/lib/api";

const TERMS = "Huge 서비스 이용약관: 채용 지원과 AI 1차 면접 응시를 위한 서비스이며, 응시는 공고당 1회입니다. 부정 응시(화면 이탈 2회 등)는 응시 취소 사유가 됩니다.";
const PRIVACY = "수집 항목: 이름·이메일·비밀번호(해시 저장)·휴대전화. 목적: 회원 식별, 장애 처리·다음 전형 연락. 보관: 회원 탈퇴 시까지. 생년월일·성별·주소·사진은 받지 않습니다.";

function formatPhone(value: string): string {
    const digits = value.replace(/\D/g, "").slice(0, 11);
    if (digits.length < 4) return digits;
    if (digits.length < 8) return `${digits.slice(0, 3)}-${digits.slice(3)}`;
    const mid = digits.length === 10 ? 3 : 4;
    return `${digits.slice(0, 3)}-${digits.slice(3, 3 + mid)}-${digits.slice(3 + mid)}`;
}

function SignupForm() {
    const router = useRouter();
    const next = useSearchParams().get("next");
    const [form, setForm] = useState({ name: "", email: "", password: "", confirm: "", phone: "" });
    const [agree, setAgree] = useState({ age_14_plus: false, terms: false, privacy: false });
    const [open, setOpen] = useState<"terms" | "privacy" | null>(null);
    const [errors, setErrors] = useState<Record<string, string>>({});
    const [busy, setBusy] = useState(false);

    const set = (key: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) =>
        setForm((f) => ({ ...f, [key]: key === "phone" ? formatPhone(e.target.value) : e.target.value }));
    const allAgreed = agree.age_14_plus && agree.terms && agree.privacy;
    const passwordOk = passwordRules(form.password, form.email).every((r) => r.ok);
    const emailOk = /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(form.email);
    const phoneOk = /^01[0-9]-\d{3,4}-\d{4}$/.test(form.phone);
    const valid = form.name.trim() && emailOk && passwordOk && form.password === form.confirm && phoneOk && allAgreed;

    async function submit(event: React.FormEvent) {
        event.preventDefault();
        if (!valid) return;
        setBusy(true);
        setErrors({});
        try {
            await api("/auth/signup", { body: { name: form.name, email: form.email, password: form.password, phone: form.phone, agreements: agree } });
            const query = new URLSearchParams({ joined: "1", email: form.email });
            if (next) query.set("next", next);
            router.push(`/login?${query}`);
        } catch (err) {
            const e = err as ApiError;
            if (e.code === "EMAIL_TAKEN") setErrors({ email: "이미 가입된 이메일입니다" });
            else if (e.code === "PASSWORD_POLICY") setErrors({ password: e.message });
            else setErrors({ form: e.message });
        } finally {
            setBusy(false);
        }
    }

    return (
        <main className="narrow" style={{ maxWidth: 560 }}>
            <div className="card stack" style={{ padding: 32 }}>
                <HugeLogo height={32} />
                <h1>회원가입</h1>
                <form className="stack" onSubmit={submit} noValidate>
                    <Field label="이름" required><input className="input" value={form.name} onChange={set("name")} autoComplete="name" maxLength={100} /></Field>
                    <Field label="이메일(아이디)" required error={errors.email ?? (form.email && !emailOk ? "이메일 형식을 확인해 주세요" : null)}>
                        <input className="input" type="email" value={form.email} onChange={set("email")} autoComplete="email" aria-invalid={!!errors.email} />
                    </Field>
                    <Field label="비밀번호" required error={errors.password}>
                        <input className="input" type="password" value={form.password} onChange={set("password")} autoComplete="new-password" />
                    </Field>
                    <PasswordChecklist password={form.password} email={form.email} />
                    <Field label="비밀번호 확인" required error={form.confirm && form.confirm !== form.password ? "비밀번호가 일치하지 않습니다" : null}
                        hint={form.confirm && form.confirm === form.password ? "✓ 일치합니다" : undefined}>
                        <input className="input" type="password" value={form.confirm} onChange={set("confirm")} autoComplete="new-password" />
                    </Field>
                    <Field label="휴대전화" required hint="장애 처리·다음 전형 연락용" error={form.phone && !phoneOk ? "010-0000-0000 형식으로 입력해 주세요" : null}>
                        <input className="input" inputMode="numeric" value={form.phone} onChange={set("phone")} placeholder="010-0000-0000" autoComplete="tel" />
                    </Field>
                    <fieldset className="card tight stack" style={{ border: "1px solid var(--color-line)" }}>
                        <legend className="sr-only">약관 동의</legend>
                        <label className="check"><input type="checkbox" checked={allAgreed}
                            onChange={(e) => setAgree({ age_14_plus: e.target.checked, terms: e.target.checked, privacy: e.target.checked })} />
                            <strong>전체 동의</strong></label>
                        <label className="check"><input type="checkbox" checked={agree.age_14_plus} onChange={(e) => setAgree({ ...agree, age_14_plus: e.target.checked })} />(필수) 만 14세 이상입니다</label>
                        {(["terms", "privacy"] as const).map((key) => (
                            <div key={key}>
                                <div className="row between">
                                    <label className="check"><input type="checkbox" checked={agree[key]} onChange={(e) => setAgree({ ...agree, [key]: e.target.checked })} />
                                        {key === "terms" ? "(필수) 이용약관 동의" : "(필수) 개인정보 수집·이용 동의"}</label>
                                    <button type="button" className="btn btn-text btn-sm" aria-expanded={open === key} onClick={() => setOpen(open === key ? null : key)}>보기 {open === key ? "▴" : "▾"}</button>
                                </div>
                                {open === key && <p className="small muted" style={{ marginLeft: 30 }}>{key === "terms" ? TERMS : PRIVACY}</p>}
                            </div>
                        ))}
                    </fieldset>
                    <p className="tiny muted">ⓘ 생년월일·성별·주소·사진은 받지 않습니다.</p>
                    {errors.form && <div className="notice notice-error" role="alert">{errors.form}</div>}
                    <div className="row" style={{ justifyContent: "flex-end" }}>
                        <Link className="btn btn-secondary" href="/login">취소</Link>
                        <button type="submit" className="btn btn-primary" disabled={!valid || busy}>{busy && <span className="spinner" />}가입하기</button>
                    </div>
                    {!valid && <p className="disabled-reason" style={{ textAlign: "right" }}>필수 항목을 모두 올바르게 입력하고 필수 동의 3개에 체크해 주세요</p>}
                </form>
            </div>
        </main>
    );
}

export default function SignupPage() {
    return <Suspense><SignupForm /></Suspense>;
}
