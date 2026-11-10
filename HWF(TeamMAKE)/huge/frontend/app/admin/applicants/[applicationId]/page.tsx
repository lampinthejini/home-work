"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { type ReactNode, useCallback, useEffect, useRef, useState } from "react";

import { AdminShell } from "@/components/AdminShell";
import { useApp } from "@/components/Providers";
import { RESUME_SECTIONS } from "@/components/ResumeForm";
import { Button, Empty, ErrorBox, Loading, Modal, StatusBadge } from "@/components/Ui";
import { api, ApiError } from "@/lib/api";
import type { AdminPosting } from "@/lib/admin";
import { dateOnly, longDateTime, mmss } from "@/lib/format";
import { type AttemptStatus, EVAL_LABEL, EVENT_LABEL, JUDGED_LABEL, QTYPE_LABEL, REVIEW_REASON } from "@/lib/status";

type ScoreRow = { item: string; score: number; quote: string | null; quote_verified: boolean };
type Highlight = { seq: number | null; kind: "good" | "deducted"; item: string; start_ms: number; end_ms: number; quote: string; media_url: string | null };
type ResultView = {
    decision: "pass" | "fail"; reason: string; quotes: string[]; item_scores: Record<string, string>;
    interview_score: string | null; coding_score: string | null; total_score: string | null; pass_score: string;
    strengths: string[]; improvements: string[]; summary: string | null; decision_check: string;
    model_version: string; prompt_version: string; rubric_version: string; decided_at: string;
};
type Detail = {
    application_id: string; applicant: { name: string; email: string; phone: string }; posting: AdminPosting;
    attempt_status: AttemptStatus; analysis_status: string; review_reason: string | null; release_at: string | null; review_deadline: string | null;
    result: ResultView | null; highlights: Highlight[]; instruction_hits: { seq: number; phrase: string }[];
    resume: Record<string, unknown> | null; resume_method: string | null;
    edited_fields: string[] | null; submitted_at: string | null; completed_at: string | null;
    questions: {
        seq: number; kind: "base" | "follow_up"; qtype: string; text: string; source: string; substituted: boolean; substitute_reason: string | null;
        regen_count: number; followup_reason: string | null; asked_at: string | null; scores: ScoreRow[];
        answer: { transcript: string | null; audio_sec: number | null; end_reason: string | null; media_url: string | null } | null;
    }[];
    events: { type: string; detail: Record<string, unknown> | string | null; judged: string | null; seq: number | null; at: string }[];
    coding: {
        problem_no: number; code: string; passed: number | null; total: number | null; paste_blocked: number; grade_status: string | null;
        saved_at: string | null; feedback: string | null;
    }[];
    memos: Memo[];
    recordings: { segment_no: number; media_url: string; size_bytes: number; started_at: string; last_chunk_at: string | null }[];
    recording_until: string | null;
};
type Memo = { memo_id: string; body: string; created_at: string; updated_at: string | null };
type Tab = "report" | "qa" | "resume" | "coding" | "events" | "memo";
const MEMO_MAX = 2000;

const END_REASON: Record<string, string> = { done: "답변 완료", timeout: "시간 종료", interrupted: "중단" };
const ANALYSIS_TEXT: Record<string, string> = {
    pending: "분석 대기 중입니다. 응시가 끝나면 자동으로 채점합니다.",
    running: "AI가 채점하고 있습니다. 보통 몇 분 안에 끝납니다.",
};

type ResumeItem = Record<string, unknown>;

function text(v: unknown): string {
    return typeof v === "string" ? v.trim() : typeof v === "number" ? String(v) : "";
}

function list(v: unknown): ResumeItem[] {
    return Array.isArray(v) ? v.filter((x): x is ResumeItem => !!x && typeof x === "object") : [];
}

/** 이력서 항목 한 줄: 제목(학교·회사 등) · 기간 · 설명. 비어 있는 칸은 빼고 보여 준다 */
function ResumeEntry({ title, period, description, skills }: { title: string; period?: string; description?: string; skills?: string[] }) {
    return (
        <li style={{ padding: "10px 0", borderBottom: "1px solid var(--color-line)" }}>
            <div className="row" style={{ justifyContent: "space-between", gap: 12 }}>
                <strong>{title || "—"}</strong>
                {period && <span className="small muted">{period}</span>}
            </div>
            {description && <p className="pre small" style={{ margin: "4px 0 0" }}>{description}</p>}
            {skills && skills.length > 0 && (
                <div className="row" style={{ gap: 4, marginTop: 6 }}>{skills.map((k) => <span key={k} className="badge badge-blue">{k}</span>)}</div>
            )}
        </li>
    );
}

function span(start: unknown, end: unknown, ongoing = ""): string {
    const a = text(start);
    const b = text(end) || ongoing;
    return a || b ? `${a} ~ ${b}` : "";
}

function ResumeSection({ title, children, empty }: { title: string; children: ReactNode; empty: boolean }) {
    if (empty) return null;
    return (
        <section>
            <h3 style={{ marginBottom: 4 }}>{title}</h3>
            <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>{children}</ul>
        </section>
    );
}

/** 지원자가 제출한 이력서를 지원자 화면과 같은 이름(학력·경력…)으로 보여 준다. 글자로만 보여 준다 (HTML 해석 안 함) */
function ResumeView({ resume }: { resume: Record<string, unknown> }) {
    const education = list(resume.education);
    const career = list(resume.career);
    const projects = list(resume.projects);
    const certificates = list(resume.certificates);
    const skills = Array.isArray(resume.skills) ? resume.skills.map(text).filter(Boolean) : [];
    const coverLetter = text(resume.cover_letter);
    const nothing = !education.length && !career.length && !projects.length && !certificates.length && !skills.length && !coverLetter;
    if (nothing) return <p className="muted">입력된 내용이 없습니다.</p>;
    return (
        <div className="stack" style={{ gap: 20 }}>
            <ResumeSection title={RESUME_SECTIONS.education.title} empty={!education.length}>
                {education.map((e, i) => (
                    <ResumeEntry key={i} title={[e.school, e.major, e.degree].map(text).filter(Boolean).join(" · ")} period={span(e.start, e.end)} />
                ))}
            </ResumeSection>
            <ResumeSection title={RESUME_SECTIONS.career.title} empty={!career.length}>
                {career.map((c, i) => (
                    <ResumeEntry key={i} title={[c.company, c.role].map(text).filter(Boolean).join(" · ")} period={span(c.start, c.end, "재직 중")}
                        description={text(c.description)} />
                ))}
            </ResumeSection>
            <ResumeSection title={RESUME_SECTIONS.projects.title} empty={!projects.length}>
                {projects.map((p, i) => (
                    <ResumeEntry key={i} title={text(p.name)} period={text(p.period)} description={text(p.description)}
                        skills={Array.isArray(p.skills) ? p.skills.map(text).filter(Boolean) : []} />
                ))}
            </ResumeSection>
            <ResumeSection title={RESUME_SECTIONS.certificates.title} empty={!certificates.length}>
                {certificates.map((c, i) => <ResumeEntry key={i} title={text(c.name)} period={text(c.acquired)} />)}
            </ResumeSection>
            {skills.length > 0 && (
                <section>
                    <h3 style={{ marginBottom: 8 }}>기술</h3>
                    <div className="row" style={{ gap: 4 }}>{skills.map((k) => <span key={k} className="badge badge-blue">{k}</span>)}</div>
                </section>
            )}
            {coverLetter && (
                <section>
                    <h3 style={{ marginBottom: 8 }}>자기소개서</h3>
                    <p className="pre" style={{ margin: 0 }}>{coverLetter}</p>
                </section>
            )}
        </div>
    );
}

function ScoreBar({ value }: { value: number }) {
    return (
        <div className="timebar" style={{ width: 120, display: "inline-block", verticalAlign: "middle" }} aria-hidden>
            <div style={{ width: `${Math.min(100, value)}%` }} />
        </div>
    );
}

/** 자동 채점을 끝내지 못한 건만 관리자가 정한다 (CONFLICTS U8). 자동 채점 결과는 여기서 바꿀 수 없다 */
function ManualDecision({ deadline, onDecide, busy }: { deadline: string | null; onDecide: (decision: "pass" | "fail", reason: string) => void; busy: boolean }) {
    const [reason, setReason] = useState("");
    const [confirm, setConfirm] = useState<"pass" | "fail" | null>(null);
    const ready = reason.trim().length >= 10;
    return (
        <div className="stack" style={{ gap: 6 }}>
            <strong className="small">직접 결정{deadline && ` · ${longDateTime(deadline)}까지 결정하지 않으면 재채점 실패 시 평가 미완료로 불합격 처리됩니다`}</strong>
            <textarea rows={3} maxLength={1000} aria-label="결정 사유" placeholder="응시 자료를 확인한 내용과 결정 사유를 10자 이상 적어 주세요. 관리자에게만 보입니다." value={reason} onChange={(e) => setReason(e.target.value)} />
            <div className="row">
                <Button kind="secondary" busy={busy} disabled={!ready} onClick={() => setConfirm("pass")}>1차 합격으로 결정</Button>
                <Button kind="secondary" busy={busy} disabled={!ready} onClick={() => setConfirm("fail")}>1차 불합격으로 결정</Button>
            </div>
            {confirm && (
                <Modal title={`1차 ${confirm === "pass" ? "합격" : "불합격"}으로 결정할까요?`} onClose={() => setConfirm(null)}
                    actions={<><Button kind="secondary" onClick={() => setConfirm(null)}>취소</Button><Button busy={busy} onClick={() => { onDecide(confirm, reason.trim()); setConfirm(null); }}>결정</Button></>}>
                    <p>결정하면 바꿀 수 없습니다. 담당자가 정한 결과로 기록되고 지원자에게도 그렇게 안내됩니다.</p>
                </Modal>
            )}
        </div>
    );
}

/** 판정 카드: 결과·총점·기준·이유. 자동 채점 결과를 바꾸는 버튼은 없다 (EVL-05, AC-14). 확인 필요면 [다시 돌리기]와 직접 결정 */
function DecisionCard({ d, onReprocess, onDecide, busy }: { d: Detail; onReprocess: () => void; onDecide: (decision: "pass" | "fail", reason: string) => void; busy: boolean }) {
    const c = d.posting.criteria;
    const r = d.result;
    return (
        <div className="card stack" style={{ gap: 8 }}>
            <div className="row">
                <strong>AI 1차 판정</strong>
                {r?.decision === "pass" && <span className="badge badge-green">1차 합격</span>}
                {r?.decision === "fail" && <span className="badge badge-gray">1차 불합격</span>}
                {!r && d.analysis_status === "needs_review" && <span className="badge badge-orange">평가 지연</span>}
                {!r && d.analysis_status !== "needs_review" && <span className="badge badge-gray">판정 전</span>}
                {r?.decision_check === "manual" && <span className="badge badge-orange">담당자 결정</span>}
                {r?.decision_check === "incomplete" && <span className="badge badge-orange">평가 미완료</span>}
                {r?.total_score != null && <span className="small">총점 <strong>{r.total_score}</strong> / 기준 {r.pass_score}</span>}
                {r?.total_score != null && <span className="small muted">AI 면접 {r.interview_score}{r.coding_score != null && ` · 코딩 ${r.coding_score}`}</span>}
            </div>
            {r && (
                <>
                    <p style={{ margin: 0 }}>{r.reason}</p>
                    {r.quotes.length > 0 && (
                        <ul className="small" style={{ margin: 0 }}>{r.quotes.map((q) => <li key={q}>“{q}”</li>)}</ul>
                    )}
                    {r.decision_check === "rejudged" && <span className="tiny muted">이유를 한 번 다시 쓰게 해서 검증을 통과했습니다.</span>}
                    {d.release_at && <span className="tiny muted">지원자 공개 {longDateTime(d.release_at)}</span>}
                </>
            )}
            {!r && d.analysis_status !== "needs_review" && <span className="small muted">{ANALYSIS_TEXT[d.analysis_status] ?? "분석이 끝나면 점수와 판정이 표시됩니다."}</span>}
            {!r && d.analysis_status === "needs_review" && (
                <div className="row">
                    <span className="small">{REVIEW_REASON[d.review_reason ?? ""] ?? "자동 채점을 끝내지 못했습니다."} 같은 응시 자료로 처음부터 다시 채점합니다.</span>
                    <Button kind="secondary" busy={busy} onClick={onReprocess}>{d.review_reason === "instruction_suspected" ? "확인했습니다, 채점하기" : "다시 돌리기"}</Button>
                </div>
            )}
            {!r && d.analysis_status === "needs_review" && <ManualDecision deadline={d.review_deadline} onDecide={onDecide} busy={busy} />}
            {d.instruction_hits.length > 0 && (
                <div className="notice notice-warn small">
                    ⚠ 답변에 채점을 바꾸려는 말로 보이는 구절이 있습니다. AI는 이런 지시를 따르지 않도록 되어 있지만, 점수가 흔들렸을 수 있으니 답변을 직접 확인해 주세요.
                    <ul style={{ margin: "6px 0 0" }}>{d.instruction_hits.map((h, i) => <li key={i}>Q{h.seq}: “…{h.phrase}…”</li>)}</ul>
                </div>
            )}
            {c && (
                <span className="tiny muted">
                    적용 기준 v{c.version} · 비율 {Object.keys(EVAL_LABEL).map((k) => c.weights[k]).join("/")}
                    {c.coding_enabled && ` · 반영 ${100 - c.coding_ratio}:${c.coding_ratio}`} · 기준 {c.pass_score}점
                    {r && ` · ${r.model_version} · ${r.prompt_version} · 기준표 ${r.rubric_version}`}
                </span>
            )}
        </div>
    );
}

function Report({ r }: { r: ResultView }) {
    return (
        <div className="stack">
            <div className="card stack" style={{ gap: 6 }}>
                <h3 style={{ margin: 0 }}>항목별 점수</h3>
                {Object.keys(EVAL_LABEL).map((k) => (
                    <div key={k} className="row" style={{ gap: 12 }}>
                        <span style={{ width: 150 }}>{EVAL_LABEL[k]}</span>
                        <ScoreBar value={Number(r.item_scores[k] ?? 0)} />
                        <span className="small">{r.item_scores[k] ?? "—"}</span>
                    </div>
                ))}
            </div>
            {r.summary && <div className="card"><h3 style={{ marginTop: 0 }}>총평</h3><p style={{ margin: 0 }}>{r.summary}</p></div>}
            <div className="grid2">
                <div className="card"><h3 style={{ marginTop: 0 }}>강점</h3>{r.strengths.length ? <ol>{r.strengths.map((s) => <li key={s}>{s}</li>)}</ol> : <p className="small muted">없음</p>}</div>
                <div className="card"><h3 style={{ marginTop: 0 }}>개선점</h3>{r.improvements.length ? <ol>{r.improvements.map((s) => <li key={s}>{s}</li>)}</ol> : <p className="small muted">없음</p>}</div>
            </div>
            <p className="tiny muted">ⓘ AI가 만든 리포트입니다. 문항별 점수와 근거 문장은 “질문별 답변” 탭에서 볼 수 있습니다.</p>
        </div>
    );
}

/** 카메라 녹화 다시 보기 (응시 끝 + 3일). 부정행위 확인용이며 평가에는 쓰지 않는다 */
function Recordings({ d }: { d: Detail }) {
    const [nowMs] = useState(() => Date.now());
    if (d.recordings.length === 0) return <p className="small muted" style={{ margin: 0 }}>카메라 녹화가 없습니다.</p>;
    const expired = d.recording_until != null && new Date(d.recording_until).getTime() <= nowMs;
    return (
        <div className="card stack" style={{ gap: 8 }}>
            <div className="row between">
                <h3 style={{ margin: 0 }}>카메라 녹화 <span className="tiny muted">(평가 미사용)</span></h3>
                <span className="small muted">{expired ? "보관 기간 만료" : `${longDateTime(d.recording_until)}까지 재생 가능`}</span>
            </div>
            {!expired && (
                <>
                    <p className="tiny muted" style={{ margin: 0 }}>ⓘ 재생 기록이 남습니다.</p>
                    {d.recordings.map((r) => (
                        <div key={r.segment_no} className="stack" style={{ gap: 4 }}>
                            <span className="small">접속 구간 {r.segment_no}{r.segment_no > 1 && " (이어가기)"} · {longDateTime(r.started_at)} 시작</span>
                            <video controls preload="none" src={r.media_url} style={{ width: "100%", maxWidth: 640 }} aria-label={`접속 구간 ${r.segment_no} 녹화`} />
                        </div>
                    ))}
                </>
            )}
        </div>
    );
}

/** 내부 메모 (ADM-05). 지원자에게는 보이지 않는다 */
function Memos({ applicationId, memos, onChange }: { applicationId: string; memos: Memo[]; onChange: () => void }) {
    const { toast } = useApp();
    const [draft, setDraft] = useState("");
    const [editing, setEditing] = useState<{ id: string; body: string } | null>(null);
    const [deleting, setDeleting] = useState<Memo | null>(null);
    const [busy, setBusy] = useState(false);

    async function run(action: () => Promise<unknown>, done: string) {
        setBusy(true);
        try {
            await action();
            toast("ok", done);
            onChange();
            return true;
        } catch (err) {
            toast("error", (err as ApiError).message);
            return false;
        } finally {
            setBusy(false);
        }
    }

    async function create() {
        if (await run(() => api(`/admin/applicants/${applicationId}/memo`, { body: { body: draft } }), "메모를 저장했습니다")) setDraft("");
    }

    async function save() {
        if (!editing) return;
        if (await run(() => api(`/admin/memos/${editing.id}`, { method: "PATCH", body: { body: editing.body } }), "메모를 고쳤습니다")) setEditing(null);
    }

    async function remove(m: Memo) {
        if (await run(() => api(`/admin/memos/${m.memo_id}`, { method: "DELETE" }), "메모를 삭제했습니다")) setDeleting(null);
    }

    return (
        <div className="stack">
            <p className="small muted" style={{ margin: 0 }}>관리자만 볼 수 있고 지원자에게는 보이지 않습니다.</p>
            {memos.length === 0 && <p className="small muted" style={{ margin: 0 }}>아직 작성한 메모가 없습니다</p>}
            <div className="card stack" style={{ gap: 8 }}>
                <label htmlFor="memo-new" className="small">새 메모</label>
                <textarea id="memo-new" rows={3} maxLength={MEMO_MAX} value={draft} onChange={(e) => setDraft(e.target.value)} />
                <div className="row" style={{ justifyContent: "space-between" }}>
                    <span className="tiny muted">{draft.length} / {MEMO_MAX}</span>
                    <Button busy={busy} disabled={!draft.trim()} onClick={create}>저장</Button>
                </div>
            </div>
            {memos.map((m) => (
                <div key={m.memo_id} className="card stack" style={{ gap: 8 }}>
                    {editing?.id === m.memo_id ? (
                        <>
                            <textarea rows={3} maxLength={MEMO_MAX} aria-label="메모 고치기" value={editing.body}
                                onChange={(e) => setEditing({ id: m.memo_id, body: e.target.value })} />
                            <div className="row" style={{ justifyContent: "flex-end" }}>
                                <button type="button" className="btn btn-secondary" onClick={() => setEditing(null)}>취소</button>
                                <Button busy={busy} disabled={!editing.body.trim()} onClick={save}>저장</Button>
                            </div>
                        </>
                    ) : (
                        <>
                            <p className="pre" style={{ margin: 0 }}>{m.body}</p>
                            <div className="row" style={{ justifyContent: "space-between" }}>
                                <span className="tiny muted">{longDateTime(m.created_at)}{m.updated_at && ` · 고침 ${longDateTime(m.updated_at)}`}</span>
                                <span className="row">
                                    <button type="button" className="btn btn-text" onClick={() => setEditing({ id: m.memo_id, body: m.body })}>수정</button>
                                    <button type="button" className="btn btn-text" onClick={() => setDeleting(m)}>삭제</button>
                                </span>
                            </div>
                        </>
                    )}
                </div>
            ))}
            {deleting && (
                <Modal title="메모를 삭제할까요?" onClose={() => setDeleting(null)} actions={(
                    <><button type="button" className="btn btn-secondary" onClick={() => setDeleting(null)}>취소</button><Button kind="danger" busy={busy} onClick={() => remove(deleting)}>삭제</Button></>
                )}><p>삭제한 메모는 되돌릴 수 없습니다.</p></Modal>
            )}
        </div>
    );
}

/** S-R06 지원자 상세. 판정·점수를 바꾸는 버튼은 두지 않는다 (EVL-05, AC-14) */
function ApplicantDetail() {
    const { applicationId } = useParams<{ applicationId: string }>();
    const { toast } = useApp();
    const [d, setD] = useState<Detail | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [tab, setTab] = useState<Tab>("report");
    const [busy, setBusy] = useState(false);
    const [confirmReprocess, setConfirmReprocess] = useState(false);  // T-55 확인 모달
    const players = useRef<Record<number, HTMLAudioElement | null>>({});

    const load = useCallback(() => {
        api<Detail>(`/admin/applicants/${applicationId}`).then(setD).catch((err) => setError((err as ApiError).message));
    }, [applicationId]);
    useEffect(load, [load]);

    async function reprocess() {
        setBusy(true);
        try {
            await api(`/admin/analysis/${applicationId}/reprocess`, { method: "POST" });
            toast("ok", "다시 채점을 시작했습니다");
            setConfirmReprocess(false);
            load();
        } catch (err) {
            toast("error", (err as ApiError).message);
        } finally {
            setBusy(false);
        }
    }

    async function decide(decision: "pass" | "fail", reason: string) {
        setBusy(true);
        try {
            await api(`/admin/analysis/${applicationId}/decision`, { body: { decision, reason } });
            toast("info", "결정을 저장했습니다");
            load();
        } catch (err) {
            toast("error", (err as ApiError).message);
        } finally {
            setBusy(false);
        }
    }

    // 하이라이트: 그 구간부터 재생 (ADM-04)
    function playFrom(h: Highlight) {
        setTab("qa");
        window.setTimeout(() => {
            const player = h.seq != null ? players.current[h.seq] : null;
            if (!player) return;
            player.currentTime = h.start_ms / 1000;
            player.scrollIntoView({ behavior: "smooth", block: "center" });
            void player.play().catch(() => undefined);
        }, 50);
    }

    if (error) return <ErrorBox message={error} />;
    if (!d) return <Loading />;
    const hasCoding = d.posting.has_coding_test;
    const tabs: { key: Tab; label: string }[] = [
        { key: "report", label: "리포트" }, { key: "qa", label: "질문별 답변" }, { key: "resume", label: "이력서" },
        ...(hasCoding ? [{ key: "coding" as Tab, label: "코딩테스트" }] : []), { key: "events", label: "장애·이탈 기록" },
        { key: "memo", label: `메모${d.memos.length ? ` ${d.memos.length}` : ""}` },
    ];
    const answered = d.questions.filter((q) => q.answer);

    return (
        <div className="stack">
            <Link href={`/admin/applicants?posting=${d.posting.posting_id}`} className="small">← 지원자 목록</Link>
            <div className="row">
                <strong>{d.applicant.name}</strong>
                <span className="muted small">{d.applicant.email} · {d.applicant.phone} · 지원 {dateOnly(d.submitted_at)}</span>
                <StatusBadge status={d.attempt_status} />
            </div>
            <DecisionCard d={d} onReprocess={() => setConfirmReprocess(true)} onDecide={decide} busy={busy} />
            {confirmReprocess && (() => {
                const suspected = d.review_reason === "instruction_suspected";
                return (
                    <Modal title={suspected ? "확인한 내용으로 채점할까요?" : "다시 채점할까요?"} onClose={() => setConfirmReprocess(false)} actions={(
                        <>
                            <button type="button" className="btn btn-secondary" onClick={() => setConfirmReprocess(false)}>취소</button>
                            <Button busy={busy} onClick={reprocess}>{suspected ? "확인했습니다, 채점하기" : "다시 돌리기"}</Button>
                        </>
                    )}>
                        <p>{suspected
                            ? "걸린 구절을 읽고 문제가 없다고 확인한 것으로 기록하고, 그대로 채점합니다."
                            : `${d.applicant.name} 님의 응시 자료로 처음부터 다시 채점합니다. 3일 기한은 늘어나지 않습니다.`}</p>
                    </Modal>
                );
            })()}
            <div className="tabs" role="tablist">
                {tabs.map((t) => <button key={t.key} type="button" role="tab" aria-selected={tab === t.key} onClick={() => setTab(t.key)}>{t.label}</button>)}
            </div>

            {tab === "report" && (d.result ? (
                <>
                    <Report r={d.result} />
                    {d.highlights.length > 0 && (
                        <div className="card stack" style={{ gap: 6 }}>
                            <h3 style={{ margin: 0 }}>하이라이트</h3>
                            {d.highlights.map((h, i) => (
                                <button key={i} type="button" className="btn btn-text" style={{ justifyContent: "flex-start", textAlign: "left" }}
                                    onClick={() => playFrom(h)} disabled={!h.media_url}>
                                    <span className={`badge ${h.kind === "good" ? "badge-green" : "badge-orange"}`}>{h.kind === "good" ? "잘함" : "깎임"}</span>{" "}
                                    Q{h.seq} · {EVAL_LABEL[h.item]} · ▶ {mmss(Math.round(h.start_ms / 1000))} “{h.quote.slice(0, 80)}”
                                </button>
                            ))}
                        </div>
                    )}
                </>
            ) : <Empty title="분석이 끝나면 리포트가 표시됩니다">질문별 답변과 기록은 지금도 볼 수 있습니다.</Empty>)}

            {tab === "qa" && (answered.length === 0 ? <Empty title="답변한 질문이 없습니다" /> : (
                <div className="stack">
                    {d.questions.map((q, i) => (
                        <details key={i} className="card" open={i < 2}>
                            <summary style={{ cursor: "pointer" }}>
                                <strong>Q{q.seq}{q.kind === "follow_up" ? "-꼬리" : ""}</strong>{" "}
                                <span className="badge badge-gray">{QTYPE_LABEL[q.qtype] ?? q.qtype}</span>{" "}
                                {q.substituted && <span className="badge badge-blue" title={q.substitute_reason ?? undefined}>대체 질문</span>}{" "}
                                {q.text}
                            </summary>
                            <div className="stack" style={{ marginTop: 12, gap: 8 }}>
                                {q.followup_reason && <span className="tiny muted">꼬리질문 이유: {q.followup_reason}</span>}
                                {!q.answer ? <span className="small muted">{q.asked_at ? "답변이 없습니다" : "제시되지 않은 문항입니다 (0점)"}</span> : (
                                    <>
                                        <p className="pre" style={{ margin: 0 }}>{q.answer.transcript || "(인식된 말이 없습니다)"}</p>
                                        <span className="tiny muted">
                                            {q.answer.audio_sec != null && `길이 ${mmss(Math.round(q.answer.audio_sec))} · `}{END_REASON[q.answer.end_reason ?? ""] ?? q.answer.end_reason}
                                        </span>
                                        {q.answer.media_url && (
                                            <audio controls preload="none" src={q.answer.media_url} aria-label={`Q${q.seq} 답변 음성`}
                                                ref={(el) => { if (q.kind === "base") players.current[q.seq] = el; }} />
                                        )}
                                    </>
                                )}
                                {q.scores.length > 0 && (
                                    <table className="table">
                                        <thead><tr><th>평가 항목</th><th>점수</th><th>근거 문장</th></tr></thead>
                                        <tbody>
                                            {q.scores.map((s) => (
                                                <tr key={s.item}>
                                                    <td>{EVAL_LABEL[s.item] ?? s.item}</td>
                                                    <td>{s.score} / 5</td>
                                                    <td className="small">{s.quote ? `“${s.quote}”` : <span className="muted">{s.score === 0 ? "답 없음" : "근거 없음 (1점)"}</span>}</td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                )}
                                {q.kind === "base" && q.scores.length > 0 && d.questions.some((f) => f.seq === q.seq && f.kind === "follow_up") && (
                                    <span className="tiny muted">꼬리질문 답변을 합쳐 채점했습니다.</span>
                                )}
                            </div>
                        </details>
                    ))}
                </div>
            ))}

            {tab === "resume" && (d.resume ? (
                <div className="card stack">
                    <span className="small muted">제출 방식: {d.resume_method === "upload" ? "파일 업로드 (자동 추출)" : d.resume_method === "saved" ? "등록 이력서" : "직접 작성"}
                        {d.edited_fields && d.edited_fields.length > 0 && ` · 지원자가 고친 항목: ${d.edited_fields.join(", ")}`}</span>
                    <ResumeView resume={d.resume} />
                </div>
            ) : <Empty title="제출된 이력서가 없습니다" />)}

            {tab === "coding" && (d.coding.length === 0 ? <Empty title="코딩테스트를 시작하지 않았습니다" /> : (
                <div className="stack">
                    {d.coding.map((s) => (
                        <div key={s.problem_no} className="card stack" style={{ gap: 8 }}>
                            <div className="row">
                                <strong>문제 {s.problem_no}</strong>
                                <span className="small">{s.grade_status === "infra_error" ? "채점 오류 (자동 재채점 대기)" : s.total != null ? `통과 ${s.passed} / ${s.total}` : "채점 전"}</span>
                                <span className="small muted">붙여넣기 차단 {s.paste_blocked}회 · 마지막 저장 {longDateTime(s.saved_at)}</span>
                            </div>
                            <pre style={{ maxHeight: 360, overflow: "auto" }}>{s.code || "(작성한 코드 없음)"}</pre>
                            {s.feedback && <div className="notice notice-info small"><strong>AI 코드 리뷰</strong> (점수에 반영하지 않음) — {s.feedback}</div>}
                        </div>
                    ))}
                </div>
            ))}

            {tab === "events" && <Recordings d={d} />}
            {tab === "events" && (d.events.length === 0 ? <Empty title="장애·이탈 기록이 없습니다" /> : (
                <div className="card" style={{ padding: 0, overflow: "hidden" }}>
                    <table className="table">
                        <thead><tr><th>시각</th><th>유형</th><th>판정</th><th>질문</th><th>내용</th></tr></thead>
                        <tbody>
                            {d.events.map((e, i) => (
                                <tr key={i}>
                                    <td className="small">{longDateTime(e.at)}</td>
                                    <td>{EVENT_LABEL[e.type] ?? e.type}</td>
                                    <td>{e.judged ? JUDGED_LABEL[e.judged] ?? e.judged : "—"}</td>
                                    <td>{e.seq ?? "—"}</td>
                                    <td className="tiny muted">{e.detail == null ? "" : typeof e.detail === "string" ? e.detail : JSON.stringify(e.detail)}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            ))}
            {tab === "memo" && <Memos applicationId={d.application_id} memos={d.memos} onChange={load} />}
            <p className="tiny muted">판정·점수는 이 화면에서 바꿀 수 없습니다.</p>
        </div>
    );
}

export default function ApplicantDetailPage() {
    return <AdminShell title="지원자 상세"><ApplicantDetail /></AdminShell>;
}
