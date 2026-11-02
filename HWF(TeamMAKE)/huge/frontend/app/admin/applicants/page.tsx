"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { AdminShell } from "@/components/AdminShell";
import { Button, Empty, ErrorBox, Loading, StatusBadge } from "@/components/Ui";
import { api, ApiError } from "@/lib/api";
import type { AdminPosting } from "@/lib/admin";
import { shortDateTime } from "@/lib/format";
import { ATTEMPT_LABEL, type AttemptStatus } from "@/lib/status";

type Row = {
    application_id: string; name: string; email: string; attempt_status: AttemptStatus; analysis_status: string;
    submitted_at: string | null; completed_at: string | null; away_count: number; fault_count: number;
    interview_score: string | null; coding_score: string | null; total_score: string | null; decision: "pass" | "fail" | null;
    review_reason: string | null;
};
// 채점 상태 (API 명세서 2-4 analysis_status). 확인 필요는 관리자 화면에서 '평가 지연'으로 보인다 (EVL-08)
const ANALYSIS_LABEL: Record<string, string> = { pending: "분석 대기", running: "분석 중", decided: "확정", needs_review: "평가 지연" };
const SORTS = [{ v: "-applied_at", l: "최근 지원순" }, { v: "-total_score", l: "총점 높은순" }, { v: "total_score", l: "총점 낮은순" }];
// 상세를 열 수 있는 상태: 응시 기록이 있는 지원 (미응시(마감)·준비 중은 볼 것이 없다)
const OPENABLE: AttemptStatus[] = ["completed", "ended", "ended_closed", "cancelled", "interrupted", "interviewing", "coding"];

function Applicants() {
    const params = useSearchParams();
    const router = useRouter();
    const [postings, setPostings] = useState<AdminPosting[] | null>(null);
    const [rows, setRows] = useState<Row[] | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [status, setStatus] = useState("");
    const [decision, setDecision] = useState("");
    const [sort, setSort] = useState("-applied_at");
    const [q, setQ] = useState("");
    const [picked, setPicked] = useState<string[]>([]);
    const postingId = params.get("posting") ?? "";

    // 비교는 같은 공고 안에서 2~3명 (S-R07)
    function togglePick(id: string) {
        setPicked((cur) => cur.includes(id) ? cur.filter((x) => x !== id) : cur.length < 3 ? [...cur, id] : cur);
    }

    useEffect(() => {
        api<{ items: AdminPosting[] }>("/admin/postings").then((r) => {
            const list = r.items.filter((p) => p.status !== "draft");
            setPostings(list);
            if (!postingId && list[0]) router.replace(`/admin/applicants?posting=${list[0].posting_id}`);
        }).catch((err) => setError((err as ApiError).message));
    }, [postingId, router]);

    useEffect(() => {
        if (!postingId) return;
        const query = new URLSearchParams({ size: "200", sort });
        if (decision) query.set("result", decision);
        api<{ items: Row[] }>(`/admin/postings/${postingId}/applicants?${query}`)
            .then((r) => { setRows(r.items); setError(null); })
            .catch((err) => setError((err as ApiError).message));
    }, [postingId, decision, sort]);

    if (error) return <ErrorBox message={error} />;
    if (!postings) return <Loading />;
    if (postings.length === 0) {
        return <Empty title="공고를 먼저 만들어 주세요"><Link className="btn btn-primary" style={{ marginTop: 12 }} href="/admin/postings">공고 관리로</Link></Empty>;
    }
    const posting = postings.find((p) => p.posting_id === postingId);
    const shown = (rows ?? []).filter((r) => (!status || r.attempt_status === status) && (!q.trim() || r.name.includes(q.trim())));

    return (
        <div className="stack">
            <div className="row" style={{ gap: 12 }}>
                <label className="row small" style={{ gap: 6 }}>공고
                    <select className="input" style={{ width: 280 }} value={postingId} onChange={(e) => { setRows(null); setPicked([]); router.replace(`/admin/applicants?posting=${e.target.value}`); }}>
                        {postings.map((p) => <option key={p.posting_id} value={p.posting_id}>{p.title}</option>)}
                    </select>
                </label>
                <label className="row small" style={{ gap: 6 }}>응시 상태
                    <select className="input" style={{ width: 160 }} value={status} onChange={(e) => setStatus(e.target.value)}>
                        <option value="">전체</option>
                        {Object.entries(ATTEMPT_LABEL).filter(([k]) => k !== "drafting").map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                    </select>
                </label>
                <label className="row small" style={{ gap: 6 }}>1차 결과
                    <select className="input" style={{ width: 130 }} value={decision} onChange={(e) => setDecision(e.target.value)}>
                        <option value="">전체</option><option value="pass">1차 합격</option><option value="fail">1차 불합격</option><option value="undecided">판정 전</option>
                    </select>
                </label>
                <label className="row small" style={{ gap: 6 }}>정렬
                    <select className="input" style={{ width: 140 }} value={sort} onChange={(e) => setSort(e.target.value)}>
                        {SORTS.map((s) => <option key={s.v} value={s.v}>{s.l}</option>)}
                    </select>
                </label>
                <input className="input" style={{ width: 200 }} placeholder="🔍 이름 검색" aria-label="이름 검색" value={q} onChange={(e) => setQ(e.target.value)} />
                <span style={{ flex: 1 }} />
                <Button kind="secondary" disabled={picked.length < 2} reason="비교할 지원자를 2~3명 골라 주세요"
                    onClick={() => router.push(`/admin/compare?ids=${picked.join(",")}`)}>선택한 {picked.length}명 비교</Button>
            </div>
            <div className="notice notice-info small">ⓘ 1차 결과는 AI가 정한 점수로 “총점 ≥ 합격 기준”이면 합격입니다. 이 화면에서는 결과를 바꿀 수 없습니다.</div>
            {!rows && <Loading />}
            {rows && rows.length === 0 && <Empty title="아직 지원자가 없습니다" />}
            {rows && rows.length > 0 && shown.length === 0 && (
                <Empty title="조건에 맞는 지원자가 없습니다"><button type="button" className="btn btn-secondary" style={{ marginTop: 12 }} onClick={() => { setStatus(""); setQ(""); setDecision(""); }}>필터 초기화</button></Empty>
            )}
            {shown.length > 0 && (
                <div className="card" style={{ padding: 0, overflow: "hidden" }}>
                    <table className="table">
                        <thead><tr>
                            <th aria-label="비교 선택" style={{ width: 36 }} /><th>이름</th><th>지원일</th><th>응시 상태</th><th>AI 면접</th>{posting?.has_coding_test && <th>코딩</th>}<th>종합</th><th>AI 1차 판정</th><th>기록</th>
                        </tr></thead>
                        <tbody>
                            {shown.map((r) => {
                                const open = OPENABLE.includes(r.attempt_status);
                                return (
                                    <tr key={r.application_id}>
                                        <td>
                                            {r.decision && (
                                                <input type="checkbox" aria-label={`${r.name} 비교에 넣기`} checked={picked.includes(r.application_id)}
                                                    disabled={!picked.includes(r.application_id) && picked.length >= 3} onChange={() => togglePick(r.application_id)} />
                                            )}
                                        </td>
                                        <td>{open ? <Link href={`/admin/applicants/${r.application_id}`} style={{ fontWeight: 600 }}>{r.name}</Link> : r.name}<div className="tiny muted">{r.email}</div></td>
                                        <td className="small">{shortDateTime(r.submitted_at)}</td>
                                        <td><StatusBadge status={r.attempt_status} /></td>
                                        <td>{r.interview_score ?? "—"}</td>
                                        {posting?.has_coding_test && <td>{r.coding_score ?? "—"}</td>}
                                        <td>{r.total_score ?? "—"}</td>
                                        <td>
                                            {r.decision === "pass" && <span className="badge badge-green">1차 합격</span>}
                                            {r.decision === "fail" && <span className="badge badge-gray">1차 불합격</span>}
                                            {!r.decision && (
                                                <span className={`badge ${r.analysis_status === "needs_review" ? "badge-orange" : "badge-gray"}`}>
                                                    {r.attempt_status === "not_taken_closed" ? "평가 없음" : ANALYSIS_LABEL[r.analysis_status] ?? "판정 전"}
                                                </span>
                                            )}
                                        </td>
                                        <td className="small">
                                            {r.fault_count > 0 && <span title={`장애 이어가기 ${r.fault_count}회`}>⚡{r.fault_count} </span>}
                                            {r.away_count > 0 && <span title={`화면 이탈 ${r.away_count}회`}>👁{r.away_count} </span>}
                                            {r.attempt_status === "ended" && <span title="응시 종료">⏹</span>}
                                            {r.attempt_status === "ended_closed" && <span title="접수 마감으로 종료, 남은 문항 0점">⏰</span>}
                                        </td>
                                    </tr>
                                );
                            })}
                        </tbody>
                    </table>
                </div>
            )}
        </div>
    );
}

export default function ApplicantsPage() {
    return <AdminShell title="지원자"><Suspense><Applicants /></Suspense></AdminShell>;
}
