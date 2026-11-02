"use client";

import { useCallback, useEffect, useState } from "react";

import { AdminShell } from "@/components/AdminShell";
import { Button, Empty, ErrorBox, Loading } from "@/components/Ui";
import { api, ApiError } from "@/lib/api";

type Status = "pending" | "active" | "rejected";
type Kind = "personality" | "company" | "job";
type Item = { id: number; kind: Kind; text: string; status: Status };
type List = { items: Item[]; counts: Record<Status, number> };

const TABS: { key: Status; label: string }[] = [
    { key: "pending", label: "검토 대기" },
    { key: "active", label: "사용 중" },
    { key: "rejected", label: "제외" },
];
const KIND_LABEL: Record<Kind, string> = { personality: "인성", company: "회사 관련", job: "직무" };

function Questions() {
    const [tab, setTab] = useState<Status>("pending");
    const [kind, setKind] = useState<"" | Kind>("");
    const [data, setData] = useState<List | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [busyId, setBusyId] = useState<number | null>(null);

    const load = useCallback(() => {
        api<List>(`/admin/questions?status=${tab}${kind ? `&kind=${kind}` : ""}`)
            .then((r) => { setData(r); setError(null); })
            .catch((err) => setError((err as ApiError).message));
    }, [tab, kind]);

    useEffect(() => { load(); }, [load]);

    async function change(id: number, action: "approve" | "reject") {
        setBusyId(id);
        try {
            await api(`/admin/questions/${id}/${action}`, { method: "POST" });
            load();
        } catch (err) {
            setError((err as ApiError).message);
        } finally {
            setBusyId(null);
        }
    }

    if (error) return <ErrorBox message={error} onRetry={load} />;
    return (
        <div className="stack">
            <div className="notice notice-info small">
                AI 가 면접 질문을 만들 때 나온 인성·회사·직무 질문 중 지원자 정보가 들어 있지 않은 것만 모았습니다.
                [추가]하면 질문은행에 들어가 다른 지원자 면접에도 쓰입니다.
            </div>
            <div className="row" style={{ gap: 12, justifyContent: "space-between" }}>
                <div className="tabs" role="tablist">
                    {TABS.map((t) => (
                        <button key={t.key} type="button" role="tab" aria-selected={tab === t.key} onClick={() => { setData(null); setTab(t.key); }}>
                            {t.label}{data ? ` ${data.counts[t.key]}` : ""}
                        </button>
                    ))}
                </div>
                <label className="row small" style={{ gap: 6 }}>종류
                    <select className="input" style={{ width: 140 }} value={kind} onChange={(e) => { setData(null); setKind(e.target.value as "" | Kind); }}>
                        <option value="">전체</option>
                        {(Object.keys(KIND_LABEL) as Kind[]).map((k) => <option key={k} value={k}>{KIND_LABEL[k]}</option>)}
                    </select>
                </label>
            </div>
            {!data && <Loading />}
            {data && data.items.length === 0 && <Empty title={tab === "pending" ? "검토할 질문이 없습니다" : "질문이 없습니다"} />}
            {data && data.items.length > 0 && (
                <div className="card" style={{ padding: 0, overflow: "hidden" }}>
                    <table className="table">
                        <thead><tr><th style={{ width: 100 }}>종류</th><th>질문</th><th style={{ width: 180 }} /></tr></thead>
                        <tbody>
                            {data.items.map((q) => (
                                <tr key={q.id}>
                                    <td><span className="badge badge-gray">{KIND_LABEL[q.kind]}</span></td>
                                    <td>{q.text}</td>
                                    <td>
                                        <div className="row" style={{ gap: 6, justifyContent: "flex-end" }}>
                                            {q.status !== "active" && (
                                                <Button size="sm" busy={busyId === q.id} disabled={busyId !== null} onClick={() => change(q.id, "approve")}>추가</Button>
                                            )}
                                            {q.status !== "rejected" && (
                                                <Button size="sm" kind="secondary" busy={busyId === q.id} disabled={busyId !== null} onClick={() => change(q.id, "reject")}>
                                                    {q.status === "active" ? "빼기" : "제외"}
                                                </Button>
                                            )}
                                        </div>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}
            {data && data.items.length >= 200 && <div className="small muted">최근 200개까지 보입니다.</div>}
        </div>
    );
}

export default function QuestionsPage() {
    return <AdminShell title="질문 관리"><Questions /></AdminShell>;
}
