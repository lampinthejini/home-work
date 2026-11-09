"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";

import { emptyResume, type ResumeData } from "@/components/ApplyFlow";
import { Mascot } from "@/components/Brand";
import { useApp } from "@/components/Providers";
import { ResumeForm } from "@/components/ResumeForm";
import { Guarded, SiteShell } from "@/components/Shell";
import { Button, Empty, ErrorBox, Field, Loading, Modal, StatusBadge } from "@/components/Ui";
import { api, ApiError } from "@/lib/api";
import { dateOnly, longDateTime, shortDateTime } from "@/lib/format";
import type { AttemptStatus } from "@/lib/status";

type Card = {
    application_id: string; posting: { posting_id: string; title: string; close_at: string };
    attempt_status: AttemptStatus; next_action: string | null; resume_until: string | null; release_status: string;
    release_at: string; result_until: string | null; applied_at: string; consented: boolean; connected: boolean;
};
type Tab = "applications" | "results" | "resume" | "account";
const TABS: { key: Tab; label: string }[] = [
    { key: "applications", label: "지원 내역" }, { key: "results", label: "결과" }, { key: "resume", label: "이력서" }, { key: "account", label: "계정" },
];

// 시작했지만 면접 화면이 서버에 붙지 않은 상태. 서버가 1~3분 안에 장애 중단으로 정하면 이어가기가 열린다 (E7)
const NOT_CONNECTED_TEXT = "면접 화면이 서버에 연결되지 않았습니다. 2~3분 뒤 새로고침하면 이어가기를 할 수 있습니다";

const CARD_TEXT: Partial<Record<AttemptStatus, (c: Card) => string>> = {
    drafting: () => "지원서 작성이 끝나지 않았습니다",
    ready: (c) => `환경 점검을 마치면 면접을 시작할 수 있습니다 · 접수 마감 ${shortDateTime(c.posting.close_at)}`,
    interviewing: (c) => (c.connected ? "다른 창에서 응시 중입니다" : NOT_CONNECTED_TEXT),
    coding: (c) => (c.connected ? "다른 창에서 응시 중입니다" : NOT_CONNECTED_TEXT),
    interrupted: (c) => `연결 문제로 중단되었습니다. ${shortDateTime(c.resume_until)}까지 이어갈 수 있습니다`,
    completed: (c) => `결과는 ${longDateTime(c.release_at)}에 공개됩니다`,
    ended: () => "지원자 조작으로 연결이 종료되어 답변한 문항까지 평가합니다",
    ended_closed: () => "마감이 되어 면접을 진행할 수 없습니다. 답변한 문항까지 평가합니다",
    cancelled: () => "화면 이탈 규칙에 따라 응시가 취소되었습니다",
    not_taken_closed: () => "마감이 되어 면접을 진행할 수 없습니다.",
};

function CardAction({ card }: { card: Card }) {
    const id = card.application_id;
    switch (card.next_action) {
        case "continue_draft": return <Link className="btn btn-secondary" href={`/apply/${id}/consent`}>이어서 작성</Link>;
        case "precheck": return <Link className="btn btn-primary" href={`/apply/${id}/precheck`}>응시 준비 계속하기</Link>;
        case "resume": return <Link className="btn btn-primary" href={`/exam/${id}/resume`}>면접 이어가기</Link>;
        case "view_result": return <Link className="btn btn-secondary" href={`/mypage/results/${id}`}>결과 보기</Link>;
        default:
            return card.attempt_status === "interviewing" || card.attempt_status === "coding" || card.attempt_status === "not_taken_closed"
                ? <button type="button" className="btn" disabled>{card.attempt_status === "not_taken_closed" ? "접수 마감" : "응시 진행 중"}</button> : null;
    }
}

function Applications({ cards }: { cards: Card[] }) {
    if (cards.length === 0) {
        return <Empty title="아직 지원한 공고가 없습니다"><Link className="btn btn-primary" style={{ marginTop: 12 }} href="/jobs">공고 보러 가기</Link></Empty>;
    }
    return (
        <div className="stack">
            {cards.map((c) => (
                <div key={c.application_id} className="card row between" style={c.attempt_status === "interrupted" ? { borderColor: "var(--color-warning)" } : undefined}>
                    <div className="stack" style={{ gap: 4 }}>
                        <div className="row"><strong>{c.posting.title}</strong><StatusBadge status={c.attempt_status} /></div>
                        <span className="small muted">지원 {dateOnly(c.applied_at)} · 접수 마감 {shortDateTime(c.posting.close_at)}</span>
                        <span className="small">{CARD_TEXT[c.attempt_status]?.(c)}</span>
                    </div>
                    <CardAction card={c} />
                </div>
            ))}
        </div>
    );
}

function Results({ cards }: { cards: Card[] }) {
    const [nowMs] = useState(() => Date.now());
    const rows = cards.filter((c) => !["drafting", "ready", "interviewing", "coding", "interrupted"].includes(c.attempt_status));
    if (rows.length === 0) return <Empty title="아직 표시할 결과가 없습니다">응시를 마치면 결과 공개일이 여기에 표시됩니다</Empty>;
    return (
        <table className="table card" style={{ padding: 0 }}>
            <thead><tr><th>공고</th><th>응시 상태</th><th>결과</th><th /></tr></thead>
            <tbody>
                {rows.map((c) => (
                    <tr key={c.application_id}>
                        <td>{c.posting.title}</td>
                        <td><StatusBadge status={c.attempt_status} /></td>
                        <td className="small">
                            {c.attempt_status === "not_taken_closed" ? "미응시(마감) — 접수 마감까지 응시하지 않아 평가되지 않았습니다"
                                : c.release_status === "delayed" ? "결과 산출이 늦어지고 있습니다. 산출이 끝나면 다음 날 공개됩니다"
                                    : c.next_action !== "view_result" && new Date(c.release_at).getTime() <= nowMs ? "결과 산출이 늦어지고 있습니다. 산출이 끝나는 대로 안내드립니다"
                                    : c.next_action === "view_result" ? `${dateOnly(c.result_until)}까지 열람 가능` : `${longDateTime(c.release_at)} 공개 예정`}
                        </td>
                        <td>{c.next_action === "view_result" && <Link className="btn btn-secondary btn-sm" href={`/mypage/results/${c.application_id}`}>결과 보기</Link>}</td>
                    </tr>
                ))}
            </tbody>
        </table>
    );
}

function SavedResume() {
    const { toast } = useApp();
    const [resume, setResume] = useState<ResumeData | null>(null);
    const [updatedAt, setUpdatedAt] = useState<string | null>(null);
    const [loaded, setLoaded] = useState(false);
    const [busy, setBusy] = useState(false);
    const [confirmDelete, setConfirmDelete] = useState(false);

    useEffect(() => {
        api<{ resume: ResumeData; updated_at: string }>("/me/resume")
            .then((r) => { setResume({ ...emptyResume(), ...r.resume }); setUpdatedAt(r.updated_at); })
            .catch(() => setResume(null)).finally(() => setLoaded(true));
    }, []);

    async function save() {
        setBusy(true);
        try {
            const r = await api<{ updated_at: string }>("/me/resume", { method: "PUT", body: { ...resume!, cover_letter: resume!.cover_letter || null } });
            setUpdatedAt(r.updated_at);
            toast("ok", "저장했습니다");
        } catch (err) {
            toast("error", (err as ApiError).message, save);
        } finally {
            setBusy(false);
        }
    }

    async function remove() {
        try {
            await api("/me/resume", { method: "DELETE" });
        } catch (err) {
            // 실패를 그냥 넘기면 확인 창이 닫히지 않고 아무 안내도 없었다 (E15)
            toast("error", (err as ApiError).message, remove);
            return;
        }
        setResume(null);
        setConfirmDelete(false);
        toast("ok", "등록 이력서를 삭제했습니다");
    }

    if (!loaded) return <Loading />;
    if (!resume) {
        return (
            <Empty title="등록된 이력서가 없습니다">
                등록해 두면 지원할 때 불러올 수 있습니다
                <div><button type="button" className="btn btn-primary" style={{ marginTop: 12 }} onClick={() => setResume(emptyResume())}>이력서 등록하기</button></div>
            </Empty>
        );
    }
    return (
        <div className="stack">
            <div className="notice notice-info small">여기서 바꿔도 이미 지원에 쓴 이력서는 바뀌지 않습니다.{updatedAt && ` · 최종 수정 ${shortDateTime(updatedAt)}`}</div>
            <div className="card"><ResumeForm value={resume} onChange={setResume} /></div>
            <div className="row" style={{ justifyContent: "flex-end" }}>
                {updatedAt && <button type="button" className="btn btn-danger" onClick={() => setConfirmDelete(true)}>삭제</button>}
                <Button busy={busy} onClick={save} disabled={!resume.name.trim()} reason="성명을 입력해 주세요">저장</Button>
            </div>
            {confirmDelete && (
                <Modal title="등록 이력서를 삭제할까요?" onClose={() => setConfirmDelete(false)} actions={(
                    <><button type="button" className="btn btn-secondary" onClick={() => setConfirmDelete(false)}>취소</button><button type="button" className="btn btn-danger" onClick={remove}>삭제</button></>
                )}><p>이미 지원에 쓴 이력서는 지워지지 않습니다.</p></Modal>
            )}
        </div>
    );
}

/** 지원별 동의 철회 (APP-03). 철회하면 진행 중 응시가 취소되고 그 지원의 데이터가 바로 지워진다 */
function Consents({ cards, onChange }: { cards: Card[]; onChange: () => void }) {
    const { toast } = useApp();
    const [target, setTarget] = useState<Card | null>(null);
    const [busy, setBusy] = useState(false);
    const consented = cards.filter((c) => c.consented);

    async function withdraw(card: Card) {
        setBusy(true);
        try {
            await api(`/applications/${card.application_id}/consent/withdraw`, { method: "POST" });
            toast("ok", "동의를 철회하고 지원 데이터를 삭제했습니다");
            setTarget(null);
            onChange();
        } catch (err) {
            toast("error", (err as ApiError).message);
        } finally {
            setBusy(false);
        }
    }

    return (
        <div className="card stack" style={{ maxWidth: 560 }}>
            <h3>지원별 동의</h3>
            {consented.length === 0 ? <p className="small muted" style={{ margin: 0 }}>동의한 지원이 없습니다</p> : (
                <ul className="stack" style={{ listStyle: "none", padding: 0, margin: 0, gap: 8 }}>
                    {consented.map((c) => (
                        <li key={c.application_id} className="row between">
                            <span><strong>{c.posting.title}</strong> <StatusBadge status={c.attempt_status} /> <span className="tiny muted">지원 {dateOnly(c.applied_at)}</span></span>
                            <button type="button" className="btn btn-danger btn-sm" onClick={() => setTarget(c)}>동의 철회</button>
                        </li>
                    ))}
                </ul>
            )}
            {target && (
                <Modal title="동의를 철회할까요?" onClose={() => setTarget(null)} actions={(
                    <><button type="button" className="btn btn-secondary" onClick={() => setTarget(null)}>취소</button><Button kind="danger" busy={busy} onClick={() => withdraw(target)}>동의 철회</Button></>
                )}>
                    <p>&apos;{target.posting.title}&apos; 지원의 동의를 철회합니다.</p>
                    <p>동의를 철회하면 진행 중 응시가 취소되고 이 지원의 응시 데이터가 즉시 삭제됩니다. 되돌릴 수 없습니다.</p>
                </Modal>
            )}
        </div>
    );
}

/** 회원 탈퇴: '탈퇴'를 입력해야 버튼이 켜진다. 진행 중 응시 취소, 응시 데이터·계정 즉시 삭제 */
function Withdraw() {
    const [open, setOpen] = useState(false);
    const [password, setPassword] = useState("");
    const [text, setText] = useState("");
    const [error, setError] = useState<string | null>(null);
    const [busy, setBusy] = useState(false);

    function close() {
        setOpen(false);
        setPassword("");
        setText("");
        setError(null);
    }

    async function withdraw() {
        setBusy(true);
        setError(null);
        try {
            await api("/me/withdraw", { body: { password, confirm_text: text } });
            window.location.replace("/jobs");  // 쿠키가 지워졌으므로 새로 불러 로그아웃 상태로 연다
        } catch (err) {
            setError((err as ApiError).message);
            setBusy(false);
        }
    }

    return (
        <div className="card stack" style={{ maxWidth: 560 }}>
            <h3>회원 탈퇴</h3>
            <p className="small muted" style={{ margin: 0 }}>탈퇴하면 진행 중인 응시가 취소되고, 모든 지원·응시 데이터와 계정이 바로 삭제됩니다.</p>
            <div><button type="button" className="btn btn-danger" onClick={() => setOpen(true)}>회원 탈퇴</button></div>
            {open && (
                <Modal title="정말 탈퇴할까요?" onClose={close} actions={(
                    <><button type="button" className="btn btn-secondary" onClick={close}>취소</button>
                        <Button kind="danger" busy={busy} disabled={text.trim() !== "탈퇴" || !password} onClick={withdraw}>탈퇴</Button></>
                )}>
                    <p>진행 중 응시가 취소되고, 응시 데이터와 계정이 즉시 삭제됩니다. 되돌릴 수 없습니다.</p>
                    <Field label="비밀번호" required>
                        <input className="input" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
                    </Field>
                    <Field label="확인을 위해 '탈퇴'를 입력해 주세요" required error={error}>
                        <input className="input" value={text} onChange={(e) => setText(e.target.value)} />
                    </Field>
                </Modal>
            )}
        </div>
    );
}

function Account({ cards, onChange }: { cards: Card[] | null; onChange: () => void }) {
    const { me, refreshMe, toast } = useApp();
    const [name, setName] = useState(me?.name ?? "");
    const [phone, setPhone] = useState(me?.phone ?? "");
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);

    async function save() {
        setBusy(true);
        setError(null);
        try {
            await api("/me", { method: "PATCH", body: { name, phone } });
            await refreshMe();
            toast("ok", "저장했습니다");
        } catch (err) {
            setError((err as ApiError).message);
        } finally {
            setBusy(false);
        }
    }

    return (
        <div className="stack">
            <div className="card stack" style={{ maxWidth: 560 }}>
                <h3>회원 정보</h3>
                <Field label="이메일"><input className="input" value={me?.email ?? ""} disabled /></Field>
                <Field label="이름" required><input className="input" value={name} onChange={(e) => setName(e.target.value)} maxLength={100} /></Field>
                <Field label="휴대전화" required error={error}><input className="input" value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="010-0000-0000" /></Field>
                <div className="row between">
                    <Link href="/password/change">비밀번호 변경</Link>
                    <Button busy={busy} onClick={save}>저장</Button>
                </div>
            </div>
            {cards ? <Consents cards={cards} onChange={onChange} /> : <Loading />}
            <Withdraw />
        </div>
    );
}

function MyPage() {
    const params = useSearchParams();
    const router = useRouter();
    const pathname = usePathname();
    const tab = (params.get("tab") as Tab) || "applications";
    const [cards, setCards] = useState<Card[] | null>(null);
    const [error, setError] = useState<string | null>(null);

    const load = useCallback(async () => {
        try {
            setCards((await api<{ items: Card[] }>("/me/applications")).items);
            setError(null);
        } catch (err) {
            setError((err as ApiError).message);
        }
    }, []);

    useEffect(() => {
        // eslint-disable-next-line react-hooks/set-state-in-effect
        void load();
    }, [load]);

    const interrupted = cards?.find((c) => c.attempt_status === "interrupted");

    return (
        <div className="container stack">
            {interrupted && (
                <div className="notice notice-warn row between" role="status">
                    <span><strong>⚠ 이어갈 면접이 있습니다</strong> · {interrupted.posting.title} · {shortDateTime(interrupted.resume_until)}(접수 마감)까지</span>
                    <Link className="btn btn-primary btn-sm" href={`/exam/${interrupted.application_id}/resume`}>면접 이어가기</Link>
                </div>
            )}
            <div className="row" style={{ gap: 16 }}>
                <Mascot name="05-report" size={72} />
                <h1 style={{ margin: 0 }}>마이페이지</h1>
            </div>
            <div className="tabs" role="tablist">
                {TABS.map((t) => (
                    <button key={t.key} type="button" role="tab" aria-selected={tab === t.key} onClick={() => router.replace(`${pathname}?tab=${t.key}`)}>{t.label}</button>
                ))}
            </div>
            {error && <ErrorBox message={error} onRetry={load} />}
            {!error && !cards && (tab === "applications" || tab === "results") && <Loading />}
            {cards && tab === "applications" && <Applications cards={cards} />}
            {cards && tab === "results" && <Results cards={cards} />}
            {tab === "resume" && <SavedResume />}
            {tab === "account" && <Account cards={cards} onChange={load} />}
        </div>
    );
}

export default function MyPageRoute() {
    return <SiteShell><Guarded role="applicant"><Suspense><MyPage /></Suspense></Guarded></SiteShell>;
}
