"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { AdminShell } from "@/components/AdminShell";
import { useApp } from "@/components/Providers";
import { Button, Empty, ErrorBox, Loading, Modal } from "@/components/Ui";
import { api, ApiError } from "@/lib/api";
import type { AdminPosting } from "@/lib/admin";
import { longDateTime, shortDateTime, untilText } from "@/lib/format";
import { POSTING_STATUS } from "@/lib/status";

type Tab = "" | "draft" | "published" | "closed";

export default function AdminPostingsPage() {
    const router = useRouter();
    const { toast } = useApp();
    const [items, setItems] = useState<AdminPosting[] | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [tab, setTab] = useState<Tab>("");
    const [q, setQ] = useState("");
    const [closing, setClosing] = useState<AdminPosting | null>(null);
    const [deleting, setDeleting] = useState<AdminPosting | null>(null);
    const [busy, setBusy] = useState(false);
    const [nowMs] = useState(() => Date.now());

    const load = useCallback(async () => {
        try {
            setItems((await api<{ items: AdminPosting[] }>("/admin/postings")).items);
            setError(null);
        } catch (err) {
            setError((err as ApiError).message);
        }
    }, []);

    useEffect(() => {
        // eslint-disable-next-line react-hooks/set-state-in-effect
        void load();
    }, [load]);

    async function close(p: AdminPosting) {
        setBusy(true);
        try {
            const r = await api<{ not_taken: number; ended_by_close: number }>(`/admin/postings/${p.posting_id}/close`, { method: "POST" });
            toast("ok", `마감했습니다 (미응시 ${r.not_taken}건 · 진행 중 종료 ${r.ended_by_close}건)`);
            setClosing(null);
            await load();
        } catch (err) {
            toast("error", (err as ApiError).message);
        } finally {
            setBusy(false);
        }
    }

    async function remove(p: AdminPosting) {
        setBusy(true);
        try {
            await api(`/admin/postings/${p.posting_id}`, { method: "DELETE" });
            toast("ok", "삭제했습니다");
            setDeleting(null);
            await load();
        } catch (err) {
            toast("error", (err as ApiError).message);
        } finally {
            setBusy(false);
        }
    }

    const counts = { "": items?.length ?? 0, draft: 0, published: 0, closed: 0 } as Record<Tab, number>;
    items?.forEach((p) => { counts[p.status] += 1; });
    const shown = (items ?? []).filter((p) => (!tab || p.status === tab) && (!q.trim() || p.title.includes(q.trim())));

    return (
        <AdminShell title="공고 관리" actions={<Link className="btn btn-primary btn-sm" href="/admin/postings/new">+ 새 공고 만들기</Link>}>
            <div className="stack">
                <div className="row between">
                    <div className="tabs" role="tablist" style={{ marginBottom: 0, borderBottom: 0 }}>
                        {(["", "draft", "published", "closed"] as Tab[]).map((t) => (
                            <button key={t} type="button" role="tab" aria-selected={tab === t} onClick={() => setTab(t)}>
                                {t ? POSTING_STATUS[t].label : "전체"} {counts[t]}
                            </button>
                        ))}
                    </div>
                    <input className="input" style={{ width: 240 }} placeholder="🔍 공고명 검색" value={q} onChange={(e) => setQ(e.target.value)} aria-label="공고명 검색" />
                </div>
                {error && <ErrorBox message={error} onRetry={load} />}
                {!items && !error && <Loading />}
                {items && items.length === 0 && (
                    <Empty title="아직 만든 공고가 없습니다"><Link className="btn btn-primary" style={{ marginTop: 12 }} href="/admin/postings/new">+ 새 공고 만들기</Link></Empty>
                )}
                {items && items.length > 0 && shown.length === 0 && (
                    <Empty title="조건에 맞는 공고가 없습니다"><button type="button" className="btn btn-secondary" style={{ marginTop: 12 }} onClick={() => { setTab(""); setQ(""); }}>전체 보기</button></Empty>
                )}
                {shown.length > 0 && (
                    <div className="card" style={{ padding: 0, overflow: "hidden" }}>
                        <table className="table">
                            <thead><tr><th>공고명</th><th>상태</th><th>접수 기간</th><th>지원자</th><th>평가 기준</th><th>결과 공개</th><th>관리</th></tr></thead>
                            <tbody>
                                {shown.map((p) => {
                                    const status = POSTING_STATUS[p.status];
                                    const locked = p.criteria?.locked;
                                    return (
                                        <tr key={p.posting_id}>
                                            <td>
                                                <Link href={p.status === "draft" ? `/admin/postings/${p.posting_id}/edit` : `/admin/applicants?posting=${p.posting_id}`} style={{ fontWeight: 600 }}>
                                                    {p.title || "(제목 없음)"}
                                                </Link>
                                                <div className="row" style={{ gap: 6, marginTop: 4 }}>
                                                    {p.source === "ai_draft" && <span className="badge badge-blue">✨ AI 초안</span>}
                                                    {p.has_coding_test && <span className="badge badge-gray">코딩테스트</span>}
                                                    {p.status === "published" && p.close_at && <span className="tiny muted">{untilText(nowMs, p.close_at)}</span>}
                                                </div>
                                            </td>
                                            <td><span className={`badge ${status.badge}`}>{status.label}</span></td>
                                            <td className="small">{p.open_at ? `${shortDateTime(p.open_at).slice(0, 5)}~${shortDateTime(p.close_at).slice(0, 5)}` : "—"}</td>
                                            <td>{p.status === "draft" ? "—" : <Link href={`/admin/applicants?posting=${p.posting_id}`}>{p.applicant_count ?? 0}명</Link>}</td>
                                            <td className="small">{locked ? "🔒 잠금" : "수정 가능"}</td>
                                            <td className="small">{p.release_at ? `${shortDateTime(p.release_at).slice(0, 5)} ${p.status === "closed" && new Date(p.release_at).getTime() <= nowMs ? "공개됨" : "예정"}` : "—"}</td>
                                            <td>
                                                <div className="row" style={{ gap: 4 }}>
                                                    {p.status !== "closed" && <button type="button" className="btn btn-secondary btn-sm" onClick={() => router.push(`/admin/postings/${p.posting_id}/edit`)}>수정</button>}
                                                    {p.status === "published" && <button type="button" className="btn btn-secondary btn-sm" onClick={() => setClosing(p)}>마감</button>}
                                                    {p.status === "draft" && (
                                                        <button type="button" className="btn btn-secondary btn-sm" disabled={(p.applicant_count ?? 0) > 0}
                                                            title={(p.applicant_count ?? 0) > 0 ? "지원자가 있는 공고는 삭제할 수 없고 마감만 가능합니다" : undefined}
                                                            onClick={() => setDeleting(p)}>삭제</button>
                                                    )}
                                                </div>
                                            </td>
                                        </tr>
                                    );
                                })}
                            </tbody>
                        </table>
                    </div>
                )}
            </div>
            {closing && (
                <Modal title="공고를 마감할까요?" onClose={() => setClosing(null)} actions={(
                    <><button type="button" className="btn btn-secondary" onClick={() => setClosing(null)}>취소</button><Button kind="danger" busy={busy} onClick={() => close(closing)}>마감</Button></>
                )}>
                    <p>마감하면 더 이상 지원을 받지 않고, <strong>진행 중인 면접도 바로 종료됩니다</strong>(답변한 문항까지 평가).</p>
                    <p className="small muted">결과는 마감 다음 날 10:00에 공개됩니다. 지금 마감하면 {longDateTime(new Date(nowMs + 86_400_000).toISOString()).replace(/\d\d:\d\d$/, "10:00")} 공개 예정입니다.</p>
                </Modal>
            )}
            {deleting && (
                <Modal title="공고를 삭제할까요?" onClose={() => setDeleting(null)} actions={(
                    <><button type="button" className="btn btn-secondary" onClick={() => setDeleting(null)}>취소</button><Button kind="danger" busy={busy} onClick={() => remove(deleting)}>삭제</Button></>
                )}><p>&apos;{deleting.title || "(제목 없음)"}&apos; 임시저장 공고를 삭제합니다. 되돌릴 수 없습니다.</p></Modal>
            )}
        </AdminShell>
    );
}
