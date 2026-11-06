"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { AdminShell } from "@/components/AdminShell";
import { Mascot } from "@/components/Brand";
import { useApp } from "@/components/Providers";
import { Button, Field, Spinner } from "@/components/Ui";
import { api, ApiError } from "@/lib/api";
import { fromLocalInput } from "@/lib/format";
import { EMPLOYMENT_LABEL } from "@/lib/status";

type JobCode = { code: string; name: string; status: "open" | "preparing" };
type Answers = {
    job_code: string; career_level: "junior" | "experienced" | "any"; career_years: number; employment_type: string; location: string;
    headcount: number; open_at: string; close_at: string; duties: string[]; skills: string[]; preferred: string; company_intro: string;
    emphasis: string; coding_test: boolean | null;
};
type Phase = { kind: "form" } | { kind: "running"; postingId: string; startedAt: number } | { kind: "failed"; postingId: string };

const DUTY_OPTIONS = ["LLM 서비스 개발", "RAG·검색", "모델 파인튜닝", "MLOps", "데이터 파이프라인", "컴퓨터 비전", "업무 자동화(AX)"];
const SKILL_OPTIONS = ["Python", "PyTorch", "LangChain", "SQL", "Docker", "FastAPI", "Kubernetes"];
const CAREER = [{ v: "junior", l: "신입" }, { v: "experienced", l: "경력" }, { v: "any", l: "무관" }] as const;
const POLL_MS = 2000;

function Chips({ options, value, onChange, label }: { options: string[]; value: string[]; onChange: (v: string[]) => void; label: string }) {
    const [custom, setCustom] = useState("");
    const all = [...options, ...value.filter((v) => !options.includes(v))];
    const toggle = (item: string) => onChange(value.includes(item) ? value.filter((v) => v !== item) : [...value, item]);
    function add() {
        const item = custom.trim().slice(0, 50);
        if (item && !value.includes(item)) onChange([...value, item]);
        setCustom("");
    }
    return (
        <div className="stack" style={{ gap: 8 }}>
            <div className="row" style={{ gap: 6, flexWrap: "wrap" }} role="group" aria-label={label}>
                {all.map((item) => (
                    <button key={item} type="button" className={`btn btn-sm ${value.includes(item) ? "btn-primary" : "btn-secondary"}`}
                        aria-pressed={value.includes(item)} onClick={() => toggle(item)}>{value.includes(item) ? "✓ " : ""}{item}</button>
                ))}
            </div>
            <div className="row" style={{ gap: 6 }}>
                <input className="input" style={{ maxWidth: 240 }} placeholder="직접 입력" value={custom} maxLength={50} aria-label={`${label} 직접 입력`}
                    onChange={(e) => setCustom(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); add(); } }} />
                <button type="button" className="btn btn-secondary btn-sm" onClick={add} disabled={!custom.trim()}>+ 추가</button>
            </div>
        </div>
    );
}

/** S-R02 AI 공고 자동 만들기. 회사명은 묻지 않는다 (단일 기업 서비스) */
export default function AiPostingPage() {
    const router = useRouter();
    const { toast } = useApp();
    const [jobs, setJobs] = useState<JobCode[]>([]);
    const [a, setA] = useState<Answers>({
        job_code: "AI_AX", career_level: "junior", career_years: 3, employment_type: "full_time", location: "", headcount: 1,
        open_at: "", close_at: "", duties: [], skills: [], preferred: "", company_intro: "", emphasis: "", coding_test: null,
    });
    const [phase, setPhase] = useState<Phase>({ kind: "form" });
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [elapsed, setElapsed] = useState(0);
    const lastBody = useRef<Record<string, unknown> | null>(null);

    useEffect(() => { api<{ items: JobCode[] }>("/job-codes").then((r) => setJobs(r.items)).catch(() => undefined); }, []);

    // 진행 상태 조회. 완료되면 공고 작성 1단계(S-R03)로 이동
    useEffect(() => {
        if (phase.kind !== "running") return;
        const timer = window.setInterval(async () => {
            setElapsed(Math.round((Date.now() - phase.startedAt) / 1000));
            try {
                const s = await api<{ status: string }>(`/admin/postings/${phase.postingId}/draft-ai/status`);
                if (s.status === "done") router.push(`/admin/postings/${phase.postingId}/edit`);
                else if (s.status === "failed") setPhase({ kind: "failed", postingId: phase.postingId });
            } catch {
                // 일시적인 조회 실패는 다음 주기에 다시 묻는다
            }
        }, POLL_MS);
        return () => window.clearInterval(timer);
    }, [phase, router]);

    const set = <K extends keyof Answers>(key: K, value: Answers[K]) => setA((v) => ({ ...v, [key]: value }));
    const required: [boolean, string][] = [
        [Boolean(a.job_code), "직무"], [Boolean(a.career_level), "경력 수준"], [Boolean(a.employment_type), "고용 형태"],
        [Boolean(a.location.trim()), "근무지"], [a.headcount >= 1, "모집 인원"], [Boolean(a.open_at && a.close_at), "접수 기간"],
        [a.coding_test !== null, "코딩테스트 여부"],
    ];
    const doneCount = required.filter(([ok]) => ok).length;
    const missing = required.filter(([ok]) => !ok).map(([, label]) => label);

    async function requestDraft(postingId: string, body: Record<string, unknown>) {
        await api(`/admin/postings/${postingId}/draft-ai`, { body });
        setElapsed(0);
        setPhase({ kind: "running", postingId, startedAt: Date.now() });
    }

    async function submit() {
        setError(null);
        if (a.open_at && a.close_at && a.open_at > a.close_at) { setError("접수 시작일은 마감일보다 앞이어야 합니다"); return; }
        if (a.close_at && new Date(a.close_at).getTime() <= Date.now()) { setError("마감일은 지금 이후여야 합니다"); return; }
        setBusy(true);
        const body = {
            job_code: a.job_code, career_level: a.career_level, career_years: a.career_level === "experienced" ? a.career_years : null,
            employment_type: a.employment_type, location: a.location.trim(), headcount: a.headcount,
            open_at: fromLocalInput(a.open_at), close_at: fromLocalInput(a.close_at), duties: a.duties, skills: a.skills,
            preferred: a.preferred.trim(), company_intro: a.company_intro.trim(), emphasis: a.emphasis.trim(), coding_test: a.coding_test,
        };
        lastBody.current = body;
        try {
            // 빈 임시저장 공고를 먼저 만들고 그 공고에 초안을 채운다 (API 명세서 draft-ai)
            const created = await api<{ posting_id: string }>("/admin/postings", { body: {} });
            await requestDraft(created.posting_id, body);
        } catch (err) {
            setError((err as ApiError).message);
        } finally {
            setBusy(false);
        }
    }

    async function retry(postingId: string) {
        try {
            await requestDraft(postingId, lastBody.current ?? {});
        } catch (err) {
            toast("error", (err as ApiError).message);
        }
    }

    if (phase.kind === "running") {
        const step = elapsed < 3 ? 0 : elapsed < 60 ? 1 : 2;
        return (
            <AdminShell title="AI로 공고 자동 만들기">
                <div className="card stack center" style={{ maxWidth: 640, margin: "40px auto" }} role="status">
                    <Mascot name="02-analysis" size={140} />
                    <h2 style={{ margin: 0 }}>AI가 공고 초안을 쓰고 있습니다</h2>
                    <ol className="stepper">
                        {["답변 정리", "초안 작성 중", "표현 점검"].map((label, i) => (
                            <li key={label} className={i < step ? "done" : i === step ? "current" : ""}><span className="dot">{i < step ? "✓" : i + 1}</span>{label}</li>
                        ))}
                    </ol>
                    <div><Spinner /> 보통 1분 안에 끝납니다 ({elapsed}초)</div>
                    <p className="small muted">이 화면을 떠나도 계속 작성되며, 완성되면 공고 관리의 &apos;임시저장&apos;에서 열 수 있습니다.</p>
                    <Link className="btn btn-secondary" href="/admin/postings">목록으로 가기</Link>
                </div>
            </AdminShell>
        );
    }

    if (phase.kind === "failed") {
        return (
            <AdminShell title="AI로 공고 자동 만들기">
                <div className="card stack center" style={{ maxWidth: 640, margin: "40px auto" }} role="alert">
                    <h2 style={{ margin: 0 }}>초안을 만들지 못했습니다</h2>
                    <p className="muted">고용 형태·근무지·모집 인원·접수 기간·코딩테스트 여부는 공고에 채워 두었습니다.</p>
                    <div className="row" style={{ justifyContent: "center" }}>
                        <button type="button" className="btn btn-primary" onClick={() => retry(phase.postingId)}>다시 시도</button>
                        <Link className="btn btn-secondary" href={`/admin/postings/${phase.postingId}/edit`}>직접 작성으로</Link>
                    </div>
                </div>
            </AdminShell>
        );
    }

    return (
        <AdminShell title="AI로 공고 자동 만들기" actions={<span className="small muted">필수 답변 {doneCount} / {required.length} 완료</span>}>
            <div className="card stack" style={{ maxWidth: 880 }}>
                <Link href="/admin/postings/new" className="small">← 작성 방식 선택</Link>
                <Field label="1. 직무" required hint="그 외 직무는 준비 중입니다">
                    <select className="input" value={a.job_code} onChange={(e) => set("job_code", e.target.value)}>
                        {(jobs.length ? jobs : [{ code: "AI_AX", name: "AI/AX 엔지니어", status: "open" as const }]).map((j) => (
                            <option key={j.code} value={j.code} disabled={j.status !== "open"}>{j.name}{j.status !== "open" ? " (준비 중)" : ""}</option>
                        ))}
                    </select>
                </Field>
                <fieldset className="field" style={{ border: 0, padding: 0, margin: 0 }}>
                    <legend>2. 경력 수준 <span className="req" aria-hidden>*</span></legend>
                    <div className="row">
                        {CAREER.map((c) => (
                            <label key={c.v} className="row" style={{ gap: 4 }}>
                                <input type="radio" name="career" checked={a.career_level === c.v} onChange={() => set("career_level", c.v)} />{c.l}
                            </label>
                        ))}
                        {a.career_level === "experienced" && (
                            <label className="row small" style={{ gap: 4 }}>경력
                                <input className="input" type="number" min={0} max={30} style={{ width: 80 }} value={a.career_years}
                                    onChange={(e) => set("career_years", Math.max(0, Math.min(30, Number(e.target.value))))} />년 이상
                            </label>
                        )}
                    </div>
                </fieldset>
                <fieldset className="field" style={{ border: 0, padding: 0, margin: 0 }}>
                    <legend>3. 고용 형태 <span className="req" aria-hidden>*</span></legend>
                    <div className="row">
                        {Object.entries(EMPLOYMENT_LABEL).map(([k, v]) => (
                            <label key={k} className="row" style={{ gap: 4 }}>
                                <input type="radio" name="employment" checked={a.employment_type === k} onChange={() => set("employment_type", k)} />{v}
                            </label>
                        ))}
                    </div>
                </fieldset>
                <div className="grid2">
                    <Field label="4. 근무지" required><input className="input" value={a.location} maxLength={200} placeholder="서울 강남구" onChange={(e) => set("location", e.target.value)} /></Field>
                    <Field label="5. 모집 인원 (명)" required><input className="input" type="number" min={1} max={999} value={a.headcount} onChange={(e) => set("headcount", Math.max(1, Number(e.target.value)))} /></Field>
                    <Field label="6. 접수 시작" required><input className="input" type="datetime-local" value={a.open_at} onChange={(e) => set("open_at", e.target.value)} /></Field>
                    <Field label="6. 접수 마감" required hint="결과는 마감 다음 날 10:00에 공개됩니다"><input className="input" type="datetime-local" value={a.close_at} onChange={(e) => set("close_at", e.target.value)} /></Field>
                </div>
                <div className="field">
                    <span>7. 주로 맡을 일 (선택 · 비우면 AI가 직무에 맞게 씁니다. 직접 입력한 말은 AI가 다듬습니다)</span>
                    <Chips label="주로 맡을 일" options={DUTY_OPTIONS} value={a.duties} onChange={(v) => set("duties", v.slice(0, 10))} />
                </div>
                <div className="field">
                    <span>8. 필요한 기술 (복수 선택)</span>
                    <Chips label="필요한 기술" options={SKILL_OPTIONS} value={a.skills} onChange={(v) => set("skills", v.slice(0, 20))} />
                </div>
                <Field label="9. 우대 사항 (선택)"><input className="input" value={a.preferred} maxLength={500} placeholder="사내 AI 도입 경험" onChange={(e) => set("preferred", e.target.value)} /></Field>
                <Field label="10. 부서 소개 (선택 · 비우면 맡을 일로 AI가 작성)">
                    <textarea className="input" rows={3} value={a.company_intro} maxLength={1000} placeholder="제조 데이터를 다루는 AI 조직…" onChange={(e) => set("company_intro", e.target.value)} />
                </Field>
                <Field label="11. 지금 회사 상황·강조할 점 (선택)">
                    <input className="input" value={a.emphasis} maxLength={500} placeholder="신규 AI 조직 신설, 초기 멤버로서 주도적으로 일할 사람" onChange={(e) => set("emphasis", e.target.value)} />
                </Field>
                <fieldset className="field" style={{ border: 0, padding: 0, margin: 0 }}>
                    <legend>12. 코딩테스트를 볼까요? <span className="req" aria-hidden>*</span></legend>
                    <div className="row">
                        <label className="row" style={{ gap: 4 }}><input type="radio" name="coding" checked={a.coding_test === true} onChange={() => set("coding_test", true)} />예</label>
                        <label className="row" style={{ gap: 4 }}><input type="radio" name="coding" checked={a.coding_test === false} onChange={() => set("coding_test", false)} />아니요</label>
                    </div>
                    <span className="tiny muted">ⓘ AI 면접 뒤 Python 2문항(60분)을 봅니다. 문제는 자동 출제되며, 반영 비중은 다음 단계에서 정합니다 (기본 AI 면접 70 : 코딩 30).</span>
                </fieldset>
                {error && <div className="notice notice-error" role="alert">⚠ {error}</div>}
                <div className="row between">
                    <Link className="btn btn-secondary" href="/admin/postings">취소</Link>
                    <Button busy={busy} disabled={missing.length > 0} reason={missing.length ? `${missing.join(", ")}을(를) 입력해 주세요` : undefined} onClick={submit}>
                        AI 초안 만들기 ▶
                    </Button>
                </div>
            </div>
        </AdminShell>
    );
}
