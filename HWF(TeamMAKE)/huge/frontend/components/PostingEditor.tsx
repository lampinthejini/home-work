"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { PostingBody, type PostingDetail } from "@/components/PostingBody";
import { useApp } from "@/components/Providers";
import { Button, Field, Modal } from "@/components/Ui";
import { api, ApiError } from "@/lib/api";
import { type AdminPosting, DEFAULT_WEIGHTS } from "@/lib/admin";
import { fromLocalInput, toLocalInput } from "@/lib/format";
import { EMPLOYMENT_LABEL, EVAL_LABEL } from "@/lib/status";

type JobCode = { code: string; name: string; status: "open" | "preparing" };
type Form = {
    title: string; job_code: string; company_intro: string; duties: string; requirements: string; preferred: string;
    employment_type: string; location: string; headcount: number; open_at: string; close_at: string; contact_email: string;
    weights: Record<string, number>; coding_enabled: boolean; coding_ratio: number; pass_score: number;
};
type FieldKey = keyof Form;

const LONG_FIELDS: { key: FieldKey; label: string; required: boolean }[] = [
    { key: "company_intro", label: "부서 소개", required: true }, { key: "duties", label: "주요 업무", required: true },
    { key: "requirements", label: "자격 요건", required: true }, { key: "preferred", label: "우대 사항", required: false },
];
const LOCKED_AFTER_PUBLISH: FieldKey[] = ["job_code", "open_at", "close_at"];
// 차별로 보일 수 있는 표현 (JOB-02). 막지 않고 알려 준다
const BIAS_PATTERNS: { re: RegExp; kind: string }[] = [
    { re: /\d{2}\s*~\s*\d{2}\s*대|\d{2}세\s*(이하|미만|이상)|만\s*\d{2}세|나이\s*제한/g, kind: "나이" },
    { re: /남성|여성|남자|여자|남녀/g, kind: "성별" },
    { re: /기혼|미혼|결혼/g, kind: "혼인" },
    { re: /용모\s*단정|키\s*\d{3}/g, kind: "외모·신체" },
    { re: /출신\s*지역|고향/g, kind: "출신" },
];

function toForm(p: AdminPosting | null): Form {
    const c = p?.criteria;
    return {
        title: p?.title ?? "", job_code: p?.job_code || "AI_AX", company_intro: p?.company_intro ?? "",
        duties: p?.duties ?? "", requirements: p?.requirements ?? "", preferred: p?.preferred ?? "", employment_type: p?.employment_type || "full_time",
        location: p?.location ?? "", headcount: p?.headcount || 1, open_at: toLocalInput(p?.open_at), close_at: toLocalInput(p?.close_at),
        contact_email: p?.contact_email ?? "", weights: { ...(c?.weights ?? DEFAULT_WEIGHTS) }, coding_enabled: c?.coding_enabled ?? false,
        coding_ratio: c?.coding_ratio ?? 30, pass_score: c?.pass_score ?? 70,
    };
}

function step1Errors(f: Form, published: boolean): Partial<Record<FieldKey, string>> {
    const e: Partial<Record<FieldKey, string>> = {};
    const required: FieldKey[] = ["title", "company_intro", "duties", "requirements", "location", "open_at", "close_at", "contact_email"];
    for (const k of required) if (!String(f[k]).trim()) e[k] = "필수 항목입니다";
    if (f.headcount < 1 || f.headcount > 999) e.headcount = "1~999명으로 입력해 주세요";
    if (f.contact_email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(f.contact_email)) e.contact_email = "이메일 형식이 아닙니다";
    if (f.open_at && f.close_at && f.open_at > f.close_at) e.close_at = "접수 시작일은 마감일보다 앞이어야 합니다";
    if (!published && f.close_at && new Date(f.close_at).getTime() <= Date.now()) e.close_at = "마감일은 지금 이후여야 합니다";
    return e;
}

function weightError(w: Record<string, number>): string | null {
    const sum = Object.values(w).reduce((a, b) => a + b, 0);
    if (Object.values(w).some((v) => v < 5 || v % 5)) return "비율은 5% 단위, 항목마다 5% 이상이어야 합니다";
    return sum === 100 ? null : `합계가 ${sum}%입니다. 100%로 맞춰 주세요`;
}

/** S-R03 공고 작성·수정 3단계 (새 공고는 posting 이 null) */
export function PostingEditor({ posting }: { posting: AdminPosting | null }) {
    const router = useRouter();
    const { toast } = useApp();
    const [id, setId] = useState(posting?.posting_id ?? null);
    const [form, setForm] = useState<Form>(() => toForm(posting));
    const [saved, setSaved] = useState<Form>(() => toForm(posting));
    const [step, setStep] = useState(1);
    const [errors, setErrors] = useState<Partial<Record<FieldKey, string>>>({});
    const [jobs, setJobs] = useState<JobCode[]>([]);
    const [busy, setBusy] = useState<"save" | "publish" | null>(null);
    const [leaving, setLeaving] = useState(false);
    const [confirmPublish, setConfirmPublish] = useState(false);
    const published = posting?.status === "published";
    const criteriaLocked = Boolean(posting?.criteria?.locked);
    const dirty = JSON.stringify(form) !== JSON.stringify(saved);

    useEffect(() => { api<{ items: JobCode[] }>("/job-codes").then((r) => setJobs(r.items)).catch(() => undefined); }, []);
    useEffect(() => {
        const warn = (e: BeforeUnloadEvent) => { if (dirty) e.preventDefault(); };
        window.addEventListener("beforeunload", warn);
        return () => window.removeEventListener("beforeunload", warn);
    }, [dirty]);

    const bias = useMemo(() => {
        const found: { word: string; kind: string }[] = [];
        const text = [form.title, form.company_intro, form.duties, form.requirements, form.preferred].join("\n");
        for (const p of BIAS_PATTERNS) for (const m of text.matchAll(p.re)) found.push({ word: m[0], kind: p.kind });
        return found;
    }, [form]);

    const set = <K extends FieldKey>(key: K, value: Form[K]) => setForm((f) => ({ ...f, [key]: value }));
    const locked = (key: FieldKey) => published && LOCKED_AFTER_PUBLISH.includes(key);

    function payload() {
        const body: Record<string, unknown> = {
            title: form.title, company_intro: form.company_intro, duties: form.duties,
            requirements: form.requirements, preferred: form.preferred, employment_type: form.employment_type, location: form.location,
            headcount: form.headcount, contact_email: form.contact_email,
        };
        if (!published) Object.assign(body, { job_code: form.job_code, open_at: fromLocalInput(form.open_at), close_at: fromLocalInput(form.close_at) });
        const criteriaChanged = JSON.stringify([form.weights, form.coding_enabled, form.coding_ratio, form.pass_score])
            !== JSON.stringify([saved.weights, saved.coding_enabled, saved.coding_ratio, saved.pass_score]);
        if (!criteriaLocked && (criteriaChanged || !posting?.criteria) && !weightError(form.weights)) {
            body.criteria = { weights: form.weights, coding_enabled: form.coding_enabled, coding_ratio: form.coding_ratio, pass_score: form.pass_score };
        }
        return body;
    }

    async function save(quiet = false): Promise<string | null> {
        setBusy("save");
        try {
            const res = id
                ? await api<AdminPosting>(`/admin/postings/${id}`, { method: "PATCH", body: payload() })
                : await api<AdminPosting>("/admin/postings", { body: payload() });
            setSaved(form);
            if (!id) {
                setId(res.posting_id);
                window.history.replaceState(null, "", `/admin/postings/${res.posting_id}/edit`);
            }
            if (!quiet) toast("ok", published ? "수정 내용을 저장했습니다. 지원자 화면에 수정 이력이 표시됩니다" : "임시저장했습니다");
            return res.posting_id;
        } catch (err) {
            toast("error", (err as ApiError).message);
            return null;
        } finally {
            setBusy(null);
        }
    }

    function next() {
        if (step === 1) {
            const e = step1Errors(form, published);
            setErrors(e);
            const first = Object.keys(e)[0];
            if (first) { document.getElementById(`f-${first}`)?.scrollIntoView({ behavior: "smooth", block: "center" }); return; }
        }
        if (step === 2 && !criteriaLocked && weightError(form.weights)) return;
        setStep((s) => s + 1);
        window.scrollTo(0, 0);
    }

    async function publish() {
        const savedId = await save(true);
        if (!savedId) return;
        setBusy("publish");
        try {
            await api(`/admin/postings/${savedId}/publish`, { method: "POST" });
            toast("ok", "게시했습니다");
            router.push("/admin/postings");
        } catch (err) {
            toast("error", (err as ApiError).message);
        } finally {
            setBusy(null);
            setConfirmPublish(false);
        }
    }

    const preview: PostingDetail = {
        posting_id: id ?? "preview", status: "published", title: form.title, job_code: form.job_code,
        company_intro: form.company_intro, duties: form.duties, requirements: form.requirements, preferred: form.preferred,
        employment_type: form.employment_type, location: form.location, headcount: form.headcount, open_at: fromLocalInput(form.open_at) ?? "",
        close_at: fromLocalInput(form.close_at) ?? "", release_at: posting?.release_at ?? "", contact_email: form.contact_email,
        has_coding_test: form.coding_enabled, revisions: posting?.revisions,
    };
    const wErr = weightError(form.weights);
    const sum = Object.values(form.weights).reduce((a, b) => a + b, 0);

    return (
        <div className="stack">
            <ol className="stepper">
                {["공고 내용", "평가 기준", "미리보기·게시"].map((label, i) => (
                    <li key={label} className={step > i + 1 ? "done" : step === i + 1 ? "current" : ""}><span className="dot">{step > i + 1 ? "✓" : i + 1}</span>{label}</li>
                ))}
            </ol>
            {posting?.source === "ai_draft" && !published && (
                <div className="notice notice-info">✨ AI가 만든 초안입니다. 내용을 확인하고 고쳐 주세요.</div>
            )}
            {published && <div className="notice notice-info small">게시 중인 공고입니다. 직무·접수 기간은 바꿀 수 없고, 고친 내용은 지원자 화면에 수정 이력으로 표시됩니다.</div>}

            {step === 1 && (
                <div className="card stack">
                    {bias.length > 0 && (
                        <div className="notice notice-warn small" role="status">
                            <strong>⚠ 차별로 보일 수 있는 표현이 {bias.length}건 있습니다</strong><br />
                            나이·성별 등으로 지원을 제한하면 채용 차별로 문제가 될 수 있습니다. 게시는 가능하지만 내용을 확인하고 고쳐 주세요.
                            <div style={{ marginTop: 4 }}>{bias.map((b, i) => <span key={i} style={{ color: "var(--color-warning-text)", fontWeight: 700, marginRight: 12 }}>&apos;{b.word}&apos; ({b.kind})</span>)}</div>
                        </div>
                    )}
                    <div id="f-title"><Field label="제목" required error={errors.title}><input className="input" value={form.title} maxLength={200} onChange={(e) => set("title", e.target.value)} /></Field></div>
                    <div className="grid2">
                        <Field label="직무" required hint={locked("job_code") ? "게시 후에는 바꿀 수 없습니다" : "그 외 직무는 준비 중입니다"}>
                            <select className="input" value={form.job_code} disabled={locked("job_code")} onChange={(e) => set("job_code", e.target.value)}>
                                {(jobs.length ? jobs : [{ code: "AI_AX", name: "AI/AX 엔지니어", status: "open" as const }]).map((j) => (
                                    <option key={j.code} value={j.code} disabled={j.status !== "open"}>{j.name}{j.status !== "open" ? " (준비 중)" : ""}</option>
                                ))}
                            </select>
                        </Field>
                    </div>
                    {LONG_FIELDS.map((f) => (
                        <div key={f.key} id={`f-${f.key}`}>
                            <Field label={f.label} required={f.required} error={errors[f.key]}>
                                <textarea className="input" rows={5} value={String(form[f.key])} onChange={(e) => set(f.key, e.target.value as never)} />
                            </Field>
                        </div>
                    ))}
                    <div className="grid2">
                        <Field label="고용 형태" required>
                            <select className="input" value={form.employment_type} onChange={(e) => set("employment_type", e.target.value)}>
                                {Object.entries(EMPLOYMENT_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                            </select>
                        </Field>
                        <div id="f-location"><Field label="근무지" required error={errors.location}><input className="input" value={form.location} maxLength={200} onChange={(e) => set("location", e.target.value)} /></Field></div>
                        <div id="f-headcount"><Field label="모집 인원 (명)" required error={errors.headcount}><input className="input" type="number" min={1} max={999} value={form.headcount} onChange={(e) => set("headcount", Number(e.target.value))} /></Field></div>
                        <div id="f-contact_email"><Field label="문의 이메일" required error={errors.contact_email} hint="지원자 결과 화면에 표시됩니다"><input className="input" type="email" value={form.contact_email} onChange={(e) => set("contact_email", e.target.value)} /></Field></div>
                        <div id="f-open_at"><Field label="접수 시작" required error={errors.open_at} hint={locked("open_at") ? "게시 후에는 바꿀 수 없습니다" : undefined}><input className="input" type="datetime-local" value={form.open_at} disabled={locked("open_at")} onChange={(e) => set("open_at", e.target.value)} /></Field></div>
                        <div id="f-close_at"><Field label="접수 마감" required error={errors.close_at} hint={locked("close_at") ? "게시 후에는 바꿀 수 없습니다" : "결과는 마감 다음 날 10:00에 공개됩니다"}><input className="input" type="datetime-local" value={form.close_at} disabled={locked("close_at")} onChange={(e) => set("close_at", e.target.value)} /></Field></div>
                    </div>
                </div>
            )}

            {step === 2 && (
                <div className="card stack">
                    <div className="notice notice-info small">
                        <strong>판정 방식</strong> — AI가 항목별로 평가 → 시스템이 가중치로 합산 → 종합 총점이 합격 기준 이상이면 시스템이 1차 합격으로 판정합니다.
                        AI는 항목별 점수와 판정 이유만 씁니다. 판정 결과는 관리자를 포함해 누구도 바꿀 수 없습니다.
                    </div>
                    {criteriaLocked && <div className="notice notice-warn small">🔒 첫 응시가 시작되어 평가 기준을 바꿀 수 없습니다.</div>}
                    <div className="row between">
                        <h3 style={{ margin: 0 }}>① 평가 항목 가중치 <span className="small muted">(5% 단위 · 항목당 5% 이상 · 합계 100%)</span></h3>
                        <button type="button" className="btn btn-text btn-sm" disabled={criteriaLocked} onClick={() => set("weights", { ...DEFAULT_WEIGHTS })}>기본값으로</button>
                    </div>
                    {Object.keys(DEFAULT_WEIGHTS).map((k) => (
                        <div key={k} className="row" style={{ gap: 12 }}>
                            <span style={{ width: 160 }}>{EVAL_LABEL[k] ?? k}</span>
                            <button type="button" className="btn btn-secondary btn-sm" aria-label={`${EVAL_LABEL[k]} 5% 줄이기`} disabled={criteriaLocked || form.weights[k] <= 5}
                                onClick={() => set("weights", { ...form.weights, [k]: form.weights[k] - 5 })}>−</button>
                            <strong style={{ width: 48, textAlign: "center" }} aria-live="polite">{form.weights[k]}%</strong>
                            <button type="button" className="btn btn-secondary btn-sm" aria-label={`${EVAL_LABEL[k]} 5% 늘리기`} disabled={criteriaLocked || form.weights[k] >= 80}
                                onClick={() => set("weights", { ...form.weights, [k]: form.weights[k] + 5 })}>+</button>
                            <div className="level" style={{ flex: 1, maxWidth: 240 }}><div style={{ width: `${form.weights[k]}%` }} /></div>
                        </div>
                    ))}
                    <p className="small" style={{ color: wErr ? "var(--color-danger)" : "var(--color-success-text)" }}>합계 {sum}% {wErr ? `— ${wErr}` : "✓"}</p>
                    <p className="tiny muted">ⓘ 평가 항목과 채점 기준(루브릭)은 바꿀 수 없습니다.</p>

                    <h3>② 코딩테스트</h3>
                    <label className="row" style={{ gap: 8 }}>
                        <input type="checkbox" role="switch" checked={form.coding_enabled} disabled={criteriaLocked} onChange={(e) => set("coding_enabled", e.target.checked)} />
                        <span>{form.coding_enabled ? "사용" : "사용 안 함"}</span>
                        <span className="tiny muted">사용하면 AI 면접이 끝난 뒤 코딩테스트를 진행합니다</span>
                    </label>
                    {form.coding_enabled && (
                        <div className="stack" style={{ gap: 4 }}>
                            <div className="row" style={{ gap: 12 }}>
                                <span className="small">AI 면접 {100 - form.coding_ratio}</span>
                                <input type="range" min={10} max={90} step={10} value={form.coding_ratio} disabled={criteriaLocked} aria-label="코딩테스트 반영 비중"
                                    onChange={(e) => set("coding_ratio", Number(e.target.value))} style={{ width: 280 }} />
                                <span className="small">{form.coding_ratio} 코딩테스트 (10% 단위)</span>
                            </div>
                            <p className="tiny muted">ⓘ 문제는 운영 문제 은행에서 자동 출제됩니다 (Python 3 · 2문항 · 60분)</p>
                        </div>
                    )}

                    <h3>③ 1차 합격 기준 점수</h3>
                    <div className="row" style={{ gap: 8 }}>
                        <input className="input" style={{ width: 100 }} type="number" min={0} max={100} value={form.pass_score} disabled={criteriaLocked}
                            onChange={(e) => set("pass_score", Math.max(0, Math.min(100, Number(e.target.value))))} aria-label="합격 기준 점수" /> 점 (0~100)
                    </div>
                    <p className="tiny muted">ⓘ 종합 총점이 이 점수 이상이면 1차 합격으로 판정합니다.</p>
                    <p className="tiny muted">ⓘ 면접 질문은 시스템이 자동으로 구성합니다 (인성 2 · 이력서 기반 2 · 기업 관련 2 · 직무 4 = 10문항)</p>
                </div>
            )}

            {step === 3 && (
                <div className="card">
                    <p className="small muted">지원자에게 보이는 모습입니다.</p>
                    <PostingBody posting={preview} action={<button type="button" className="btn btn-primary" disabled>지원하기</button>} />
                </div>
            )}

            <div className="bottom-bar" style={{ position: "sticky", margin: "0 -24px -24px" }}><div className="container" style={{ maxWidth: "none" }}>
                <button type="button" className="btn btn-secondary" onClick={() => (dirty ? setLeaving(true) : router.push("/admin/postings"))}>취소</button>
                <span style={{ flex: 1 }} />
                <Button kind="secondary" busy={busy === "save"} onClick={() => save()}>{published ? "수정 저장" : "임시저장"}</Button>
                {step > 1 && <button type="button" className="btn btn-secondary" onClick={() => setStep((s) => s - 1)}>이전</button>}
                {step < 3 && <Button onClick={next} disabled={step === 2 && !criteriaLocked && Boolean(wErr)} reason={wErr ?? undefined}>다음 ▶</Button>}
                {step === 3 && !published && <Button busy={busy === "publish"} onClick={() => setConfirmPublish(true)}>게시하기</Button>}
            </div></div>

            {leaving && (
                <Modal title="저장하지 않은 내용이 있습니다" onClose={() => setLeaving(false)} actions={(
                    <><button type="button" className="btn btn-secondary" onClick={() => setLeaving(false)}>계속 작성</button><button type="button" className="btn btn-danger" onClick={() => router.push("/admin/postings")}>나가기</button></>
                )}><p>저장하지 않은 내용이 있습니다. 나갈까요?</p></Modal>
            )}
            {confirmPublish && (
                <Modal title="공고를 게시할까요?" onClose={() => setConfirmPublish(false)} actions={(
                    <><button type="button" className="btn btn-secondary" onClick={() => setConfirmPublish(false)}>취소</button><Button busy={busy === "publish"} onClick={publish}>게시</Button></>
                )}>
                    <p>게시하면 직무·접수 기간은 바꿀 수 없습니다. 평가 기준은 첫 응시가 시작되면 잠깁니다.</p>
                    {bias.length > 0 && <p className="small" style={{ color: "var(--color-warning-text)" }}>⚠ 차별로 보일 수 있는 표현 {bias.length}건이 남아 있습니다.</p>}
                </Modal>
            )}
        </div>
    );
}
