"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { AdminShell } from "@/components/AdminShell";
import { Empty, ErrorBox, Loading } from "@/components/Ui";
import { api, ApiError } from "@/lib/api";
import type { AdminPosting } from "@/lib/admin";
import { dateOnly, longDateTime } from "@/lib/format";

type Passed = {
    items: { application_id: string; name: string; email: string; phone: string | null; total_score: string; decided_at: string; purge_at: string | null }[];
    undecided: number; purge_at: string | null;
};
const SOON_MS = 2 * 24 * 3600 * 1000;

function NextStage() {
    const params = useSearchParams();
    const router = useRouter();
    const [postings, setPostings] = useState<AdminPosting[] | null>(null);
    const [data, setData] = useState<Passed | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [q, setQ] = useState("");
    const postingId = params.get("posting") ?? "";

    useEffect(() => {
        api<{ items: AdminPosting[] }>("/admin/postings").then((r) => {
            const list = r.items.filter((p) => p.status !== "draft");
            setPostings(list);
            if (!postingId && list[0]) router.replace(`/admin/next-stage?posting=${list[0].posting_id}`);
        }).catch((err) => setError((err as ApiError).message));
    }, [postingId, router]);

    useEffect(() => {
        if (!postingId) return;
        api<Passed>(`/admin/postings/${postingId}/passed`).then((r) => { setData(r); setError(null); })
            .catch((err) => setError((err as ApiError).message));
    }, [postingId]);

    if (error) return <ErrorBox message={error} />;
    if (!postings) return <Loading />;
    if (postings.length === 0) return <Empty title="게시한 공고가 없습니다" />;
    const shown = (data?.items ?? []).filter((r) => !q.trim() || r.name.includes(q.trim()));
    // 화면에 보이는 '지금'은 렌더 시각으로 충분하다 (D-2 배너 색만 정함)
    // eslint-disable-next-line react-hooks/purity
    const soon = data?.purge_at ? new Date(data.purge_at).getTime() - Date.now() <= SOON_MS : false;

    return (
        <div className="stack">
            <div className="row" style={{ gap: 12 }}>
                <label className="row small" style={{ gap: 6 }}>공고
                    <select className="input" style={{ width: 280 }} value={postingId} onChange={(e) => { setData(null); router.replace(`/admin/next-stage?posting=${e.target.value}`); }}>
                        {postings.map((p) => <option key={p.posting_id} value={p.posting_id}>{p.title}</option>)}
                    </select>
                </label>
                <input className="input" style={{ width: 200 }} placeholder="🔍 이름 검색" aria-label="이름 검색" value={q} onChange={(e) => setQ(e.target.value)} />
            </div>
            {data?.purge_at && (
                <div className={`notice ${soon ? "notice-warn" : "notice-info"} small`}>
                    ⚠ 응시 데이터와 연락처는 {longDateTime(data.purge_at)}에 삭제됩니다{soon ? " (2일 안)" : ""}. 그 전에 연락하세요.
                </div>
            )}
            {!data && <Loading />}
            {data && data.items.length === 0 && (
                <Empty title={data.undecided > 0 ? "아직 1차 판정이 끝나지 않았습니다" : "이 공고의 1차 합격자가 없습니다"} />
            )}
            {shown.length > 0 && (
                <div className="card" style={{ padding: 0, overflow: "hidden" }}>
                    <table className="table">
                        <thead><tr><th>이름</th><th>이메일</th><th>휴대전화</th><th>종합 총점</th><th>판정일</th><th /></tr></thead>
                        <tbody>
                            {shown.map((r) => (
                                <tr key={r.application_id}>
                                    <td style={{ fontWeight: 600 }}>{r.name}</td><td className="small">{r.email}</td><td className="small">{r.phone ?? "—"}</td>
                                    <td>{r.total_score}</td><td className="small">{dateOnly(r.decided_at)}</td>
                                    <td><Link className="btn btn-secondary btn-sm" href={`/admin/applicants/${r.application_id}`}>상세</Link></td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}
            {data && data.items.length > 0 && data.undecided > 0 && <div className="small muted">판정이 끝나지 않은 지원 {data.undecided}건은 끝나면 여기에 더해집니다.</div>}
            <div className="small muted">ⓘ 2차 전형 일정 관리·통보 기능은 제공하지 않습니다.</div>
        </div>
    );
}

export default function NextStagePage() {
    return <AdminShell title="다음 전형 대상자 (1차 합격자)"><Suspense><NextStage /></Suspense></AdminShell>;
}
