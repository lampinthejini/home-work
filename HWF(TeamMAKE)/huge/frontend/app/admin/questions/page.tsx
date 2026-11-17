"use client";

import { useCallback, useEffect, useState } from "react";

import { AdminShell } from "@/components/AdminShell";
import { useApp } from "@/components/Providers";
import { Button, Empty, ErrorBox, Loading, Modal } from "@/components/Ui";
import { api, ApiError } from "@/lib/api";

// 예비 질문 (2026-11-16 사용자 결정, CONFLICTS C-20. 예전 '질문 관리'를 바꿈)
// AI 가 질문을 만들 때 보는 예시이고, 못 만들었을 때 대신 내는 질문이다. AI 질문은 승인 없이 들어온다
type Kind = "personality" | "company" | "resume" | "job";
type Item = { id: number; kind: Kind; text: string; category: string; job_code: string; job_name: string; job_only: boolean; is_new: boolean };
type List = { items: Item[]; counts: Record<Kind, number>; limit: number };

const KIND_LABEL: Record<Kind, string> = { personality: "인성", company: "회사 관련", resume: "이력서 기반", job: "직무" };
const KINDS = Object.keys(KIND_LABEL) as Kind[];

function Questions() {
    const { toast } = useApp();
    const [kind, setKind] = useState<"" | Kind>("");
    const [data, setData] = useState<List | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [checked, setChecked] = useState<Set<number>>(new Set());
    const [editing, setEditing] = useState<{ id: number; text: string } | null>(null);
    const [busy, setBusy] = useState(false);
    const [confirmIds, setConfirmIds] = useState<number[] | null>(null);

    const load = useCallback(() => {
        api<List>(`/admin/questions${kind ? `?kind=${kind}` : ""}`)
            .then((r) => { setData(r); setError(null); setChecked(new Set()); })
            .catch((err) => setError((err as ApiError).message));
    }, [kind]);

    useEffect(() => { load(); }, [load]);

    async function patch(id: number, body: { text: string }) {
        setBusy(true);
        try {
            const updated = await api<Item>(`/admin/questions/${id}`, { method: "PATCH", body });
            setData((d) => d && { ...d, items: d.items.map((q) => (q.id === id ? updated : q)) });
            setEditing(null);
        } catch (err) {
            toast("error", (err as ApiError).message);
        } finally {
            setBusy(false);
        }
    }

    async function remove(ids: number[]) {
        setBusy(true);
        try {
            const r = await api<{ deleted: number }>("/admin/questions/delete", { method: "POST", body: { ids } });
            toast("ok", `${r.deleted}개를 지웠습니다.`);
            setConfirmIds(null);
            load();
        } catch (err) {
            toast("error", (err as ApiError).message);
        } finally {
            setBusy(false);
        }
    }

    function toggle(id: number) {
        setChecked((s) => {
            const next = new Set(s);
            if (next.has(id)) next.delete(id);
            else next.add(id);
            return next;
        });
    }

    if (error) return <ErrorBox message={error} onRetry={load} />;
    const items = data?.items ?? [];
    const allChecked = items.length > 0 && items.every((q) => checked.has(q.id));
    return (
        <div className="stack">
            <div className="notice notice-info small">
                AI 가 면접 질문을 만들 때 보는 <b>예시</b>이고, 질문을 만들지 못했을 때 <b>대신 내는 질문</b>입니다.
                AI 가 만든 질문 중 지원자 개인 정보가 없고 기존 예비 질문과 많이 비슷하지 않은(유사도 0.8 미만) 것이 자동으로 들어옵니다.
                분야마다 최대 {data?.limit ?? 100}개이며, 다 차면 더 들어오지 않습니다. 들어온 지 하루가 안 된 질문에는 NEW 가 붙습니다.
            </div>
            <div className="row" style={{ gap: 12, justifyContent: "space-between" }}>
                <div className="tabs" role="tablist">
                    <button type="button" role="tab" aria-selected={kind === ""} onClick={() => { setData(null); setKind(""); }}>전체</button>
                    {KINDS.map((k) => (
                        <button key={k} type="button" role="tab" aria-selected={kind === k} onClick={() => { setData(null); setKind(k); }}>
                            {KIND_LABEL[k]}{data ? ` ${data.counts[k]}/${data.limit}` : ""}
                        </button>
                    ))}
                </div>
                <Button kind="secondary" size="sm" disabled={checked.size === 0 || busy} onClick={() => setConfirmIds([...checked])}>
                    고른 질문 삭제{checked.size ? ` (${checked.size})` : ""}
                </Button>
            </div>
            {!data && <Loading />}
            {data && items.length === 0 && <Empty title="예비 질문이 없습니다" />}
            {data && items.length > 0 && (
                <div className="card" style={{ padding: 0, overflow: "hidden" }}>
                    <table className="table">
                        <thead>
                            <tr>
                                <th style={{ width: 40 }}>
                                    <input type="checkbox" aria-label="모두 고르기" checked={allChecked}
                                        onChange={() => setChecked(allChecked ? new Set() : new Set(items.map((q) => q.id)))} />
                                </th>
                                <th style={{ width: 100 }}>질문분야</th>
                                <th>질문</th>
                                <th style={{ width: 80 }} />
                            </tr>
                        </thead>
                        <tbody>
                            {items.map((q) => (
                                <tr key={q.id}>
                                    <td><input type="checkbox" aria-label="이 질문 고르기" checked={checked.has(q.id)} onChange={() => toggle(q.id)} /></td>
                                    <td><span className="badge badge-gray">{KIND_LABEL[q.kind]}</span></td>
                                    <td>
                                        {editing?.id === q.id ? (
                                            <div className="stack" style={{ gap: 6 }}>
                                                <textarea className="input" aria-label="질문 고치기" maxLength={200} value={editing.text}
                                                    onChange={(e) => setEditing({ id: q.id, text: e.target.value })} />
                                                <div className="row" style={{ gap: 6 }}>
                                                    <Button size="sm" busy={busy} onClick={() => patch(q.id, { text: editing.text })}>저장</Button>
                                                    <Button size="sm" kind="secondary" disabled={busy} onClick={() => setEditing(null)}>취소</Button>
                                                </div>
                                            </div>
                                        ) : (
                                            <div className="row" style={{ gap: 6, alignItems: "flex-start" }}>
                                                {q.is_new && <span className="badge badge-orange">NEW</span>}
                                                <span style={{ flex: 1 }}>{q.text}</span>
                                                <button type="button" className="btn btn-text btn-sm" disabled={busy}
                                                    onClick={() => setEditing({ id: q.id, text: q.text })}>수정</button>
                                            </div>
                                        )}
                                        {q.category && <div className="small muted">{q.category}</div>}
                                    </td>
                                    <td>
                                        <Button size="sm" kind="secondary" disabled={busy} onClick={() => setConfirmIds([q.id])}>삭제</Button>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}
            {confirmIds && (
                <Modal title="예비 질문 삭제" onClose={() => setConfirmIds(null)} actions={
                    <>
                        <button type="button" className="btn btn-secondary" onClick={() => setConfirmIds(null)}>취소</button>
                        <Button kind="danger" busy={busy} onClick={() => remove(confirmIds)}>삭제</Button>
                    </>
                }>
                    <p>질문 {confirmIds.length}개를 지웁니다. 지운 질문은 되돌릴 수 없습니다. 이미 끝난 면접 기록은 그대로 남습니다.</p>
                </Modal>
            )}
        </div>
    );
}

export default function QuestionsPage() {
    return <AdminShell title="예비 질문"><Questions /></AdminShell>;
}
