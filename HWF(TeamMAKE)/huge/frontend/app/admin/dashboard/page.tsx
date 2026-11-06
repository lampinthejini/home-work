"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { AdminShell } from "@/components/AdminShell";
import { useApp } from "@/components/Providers";
import { Button, ErrorBox, Loading, Modal } from "@/components/Ui";
import { api, ApiError } from "@/lib/api";
import { shortDateTime } from "@/lib/format";
import { EVAL_LABEL, QTYPE_LABEL, REVIEW_REASON } from "@/lib/status";

type Stats = {
    applications: number; taken: number; taken_this_month: number; completion_rate: number | null; pass_rate: number | null;
    average_total: string | null; item_averages: Record<string, string | null>; score_bins: { from: number; to: number; count: number }[];
    resumed: number; cheating_cancelled: number; monthly: { month: string; taken: number }[];
    postings: { posting_id: string; title: string; taken: number; pass_rate: number | null; average_total: string | null }[];
};
type Ops = {
    needs_review: { application_id: string; name: string; posting_title: string; since: string | null; reason: string | null }[];
    mail_failed: { count: number; items: { to: string; kind: string; title: string; reason: string | null; at: string }[] };
    questions: { bank: number; reserve_total: number };
    reserve_questions: { category: string; count: number; below_minimum: boolean }[];
    coding_problems: Record<string, number>;
    login_blocks: { code: string; fail_count: number; blocked_at: string; blocked_until: string }[];
};

function Bars({ data, label }: { data: { name: string; value: number }[]; label: string }) {
    // 막대와 같은 값을 표로도 둔다 (화면정의서 S-R09 접근성)
    const max = Math.max(1, ...data.map((d) => d.value));
    return (
        <div>
            <div aria-hidden style={{ display: "flex", alignItems: "flex-end", gap: 6, height: 120 }}>
                {data.map((d) => (
                    <div key={d.name} style={{ flex: 1, textAlign: "center" }}>
                        <div className="tiny">{d.value || ""}</div>
                        <div style={{ height: `${(d.value / max) * 90}px`, minHeight: d.value ? 2 : 0, background: "var(--color-primary)", borderRadius: 3 }} />
                        <div className="tiny muted">{d.name}</div>
                    </div>
                ))}
            </div>
            <details className="small"><summary>{label} 표로 보기</summary>
                <table className="table"><tbody>{data.map((d) => <tr key={d.name}><th scope="row">{d.name}</th><td>{d.value}</td></tr>)}</tbody></table>
            </details>
        </div>
    );
}

function Dashboard() {
    const { toast } = useApp();
    const [stats, setStats] = useState<Stats | null>(null);
    const [ops, setOps] = useState<Ops | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [reprocess, setReprocess] = useState<Ops["needs_review"][number] | null>(null);
    const [busy, setBusy] = useState(false);
    const [showMail, setShowMail] = useState(false);

    const load = useCallback(async () => {
        try {
            const [s, o] = await Promise.all([api<Stats>("/admin/stats"), api<Ops>("/admin/ops-status")]);
            setStats(s);
            setOps(o);
            setError(null);
        } catch (err) {
            setError((err as ApiError).message);
        }
    }, []);

    useEffect(() => {
        // eslint-disable-next-line react-hooks/set-state-in-effect
        void load();
    }, [load]);

    async function runReprocess() {
        if (!reprocess) return;
        setBusy(true);
        try {
            await api(`/admin/analysis/${reprocess.application_id}/reprocess`, { method: "POST" });
            toast("ok", "다시 채점을 시작했습니다");
            setReprocess(null);
            await load();
        } catch (err) {
            toast("error", (err as ApiError).message);
        } finally {
            setBusy(false);
        }
    }

    async function releaseBlock(code: string) {
        try {
            await api(`/admin/login-blocks/${code}/release`, { method: "POST" });
            toast("ok", "차단을 해제했습니다");
            await load();
        } catch (err) {
            toast("error", (err as ApiError).message);
        }
    }

    if (error) return <ErrorBox message={error} onRetry={load} />;
    if (!stats || !ops) return <Loading />;
    const empty = stats.taken === 0;
    const cards = [
        ["이번 달 응시", `${stats.taken_this_month}명`], ["1차 합격률", stats.pass_rate === null ? "—" : `${stats.pass_rate}%`],
        ["평균 종합 점수", stats.average_total ? `${stats.average_total}점` : "—"], ["장애 이어가기", `${stats.resumed}건`],
        ["부정행위 취소", `${stats.cheating_cancelled}건`],
    ];

    return (
        <div className="stack">
            <div className="row between"><h2 style={{ margin: 0 }}>통계</h2><span className="small muted">최근 12개월 · 보관 기간이 지나 지운 응시도 합쳐서 보여 줍니다</span></div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(5, minmax(0, 1fr))", gap: 12 }}>
                {cards.map(([label, value]) => (
                    <div key={label} className="card center"><div className="small muted">{label}</div><div style={{ fontSize: 26, fontWeight: 700 }}>{value}</div></div>
                ))}
            </div>
            {empty ? <div className="card center muted">아직 집계할 응시가 없습니다</div> : (
                <>
                    <div className="grid2" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
                        <div className="card"><h3 style={{ marginTop: 0 }}>월별 응시자 수</h3>
                            <Bars label="월별 응시자 수" data={stats.monthly.map((m) => ({ name: `${Number(m.month.slice(5))}월`, value: m.taken }))} /></div>
                        <div className="card"><h3 style={{ marginTop: 0 }}>종합 점수 분포</h3>
                            <Bars label="종합 점수 분포" data={stats.score_bins.map((b) => ({ name: `${b.from}`, value: b.count }))} /></div>
                    </div>
                    <div className="card" style={{ padding: 0, overflow: "hidden" }}>
                        <table className="table">
                            <thead><tr><th>공고별</th><th>응시자</th><th>1차 합격률</th><th>평균 점수</th></tr></thead>
                            <tbody>{stats.postings.map((p) => (
                                <tr key={p.posting_id}><td>{p.title}</td><td>{p.taken}</td><td>{p.pass_rate === null ? "—" : `${p.pass_rate}%`}</td><td>{p.average_total ?? "—"}</td></tr>
                            ))}</tbody>
                        </table>
                    </div>
                    <div className="small muted">항목별 평균: {Object.entries(stats.item_averages).map(([k, v]) => `${EVAL_LABEL[k] ?? k} ${v ?? "—"}`).join(" · ")}</div>
                </>
            )}

            <h2 style={{ margin: "16px 0 0" }}>운영 현황</h2>
            <div className="card stack">
                {ops.needs_review.length === 0 ? <div>✓ 평가 지연 건이 없습니다</div> : (
                    <div>
                        <strong>⚠ 평가 지연 {ops.needs_review.length}건</strong>
                        {ops.needs_review.map((r) => (
                            <div key={r.application_id} className="row between small" style={{ padding: "6px 0" }}>
                                <span>{r.name} · {r.posting_title} · {shortDateTime(r.since)}부터 — {REVIEW_REASON[r.reason ?? ""] ?? "자동 채점을 끝내지 못했습니다"}</span>
                                <span className="row">
                                    {/* 채점 지시 의심은 답변을 먼저 읽어야 하므로 상세에서만 진행한다 */}
                                    {r.reason !== "instruction_suspected" && <button type="button" className="btn btn-secondary btn-sm" onClick={() => setReprocess(r)}>재처리</button>}
                                    <Link className="btn btn-secondary btn-sm" href={`/admin/applicants/${r.application_id}`}>상세</Link>
                                </span>
                            </div>
                        ))}
                    </div>
                )}
                <hr style={{ border: 0, borderTop: "1px solid var(--color-line)", width: "100%" }} />
                {ops.login_blocks.length === 0 ? <div>✓ 로그인 차단 중인 곳이 없습니다</div> : (
                    <div>
                        <strong>🔒 로그인 차단 {ops.login_blocks.length}곳</strong>
                        {ops.login_blocks.map((b) => (
                            <div key={b.code} className="row between small" style={{ padding: "6px 0" }}>
                                <span>문의 코드 {b.code} · {shortDateTime(b.blocked_at)} 차단 · {shortDateTime(b.blocked_until)}에 자동 해제</span>
                                <button type="button" className="btn btn-secondary btn-sm" onClick={() => void releaseBlock(b.code)}>해제</button>
                            </div>
                        ))}
                    </div>
                )}
                <hr style={{ border: 0, borderTop: "1px solid var(--color-line)", width: "100%" }} />
                {ops.mail_failed.count === 0 ? <div>✓ 최근 7일 메일 발송 실패가 없습니다</div> : (
                    <div>
                        <div className="row between"><strong>✉ 메일 발송 실패 {ops.mail_failed.count}건 (최근 7일)</strong>
                            <button type="button" className="btn btn-text btn-sm" aria-expanded={showMail} onClick={() => setShowMail(!showMail)}>목록 보기 {showMail ? "▴" : "▾"}</button></div>
                        {showMail && ops.mail_failed.items.map((m) => (
                            <div key={`${m.at}-${m.to}`} className="small">{m.title} · {m.to} · {m.reason ?? "원인 불명"} · {shortDateTime(m.at)}</div>
                        ))}
                        <div className="tiny muted">사이트 알림(🔔)은 메일과 상관없이 남아 있습니다.</div>
                    </div>
                )}
                <hr style={{ border: 0, borderTop: "1px solid var(--color-line)", width: "100%" }} />
                <div className="small">
                    📚 <strong>문항 현황</strong> 면접 질문 {ops.questions.bank.toLocaleString()} · 예비 질문 {ops.questions.reserve_total}
                    {" ("}{ops.reserve_questions.map((r, i) => (
                        <span key={r.category} style={r.below_minimum ? { color: "var(--color-warning-text)", fontWeight: 600 } : undefined}>
                            {i > 0 && " · "}{QTYPE_LABEL[r.category] ?? r.category} {r.count}{r.below_minimum ? " ⚠" : ""}
                        </span>
                    ))}{")"}
                    <div>코딩테스트 문제 {Object.entries(ops.coding_problems).map(([level, n]) => `${level} ${n}`).join(" · ")}</div>
                    <div className="tiny muted">ⓘ 문항 추가·수정은 적재 명령(manage.py)으로 합니다. 예비 질문은 종류별 5개 이상이 필요합니다.</div>
                </div>
            </div>
            {reprocess && (
                <Modal title="다시 채점할까요?" onClose={() => setReprocess(null)} actions={(
                    <>
                        <button type="button" className="btn btn-secondary" onClick={() => setReprocess(null)}>취소</button>
                        <Button busy={busy} onClick={runReprocess}>다시 돌리기</Button>
                    </>
                )}>
                    <p>{reprocess.name} 님의 응시 자료로 처음부터 다시 채점합니다. 3일 기한은 늘어나지 않으며, 합격·불합격을 직접 정하려면 지원자 상세로 가 주세요.</p>
                </Modal>
            )}
        </div>
    );
}

export default function DashboardPage() {
    return <AdminShell title="대시보드"><Dashboard /></AdminShell>;
}
