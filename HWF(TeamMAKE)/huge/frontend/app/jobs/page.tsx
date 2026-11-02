"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";

import { Mascot } from "@/components/Brand";
import { SiteShell } from "@/components/Shell";
import { Empty, ErrorBox, StatusBadge } from "@/components/Ui";
import { api, ApiError } from "@/lib/api";
import { shortDateTime, untilText } from "@/lib/format";
import { EMPLOYMENT_LABEL, type AttemptStatus } from "@/lib/status";

type JobCode = { code: string; name: string; status: "open" | "preparing" };
export type PostingCard = {
    posting_id: string; title: string; job_code: string; employment_type: string; location: string;
    headcount: number; open_at: string; close_at: string; release_at: string; has_coding_test: boolean; my_attempt_status: AttemptStatus | null;
};
type ListResponse = { items: PostingCard[]; total: number; page: number; size: number };

function Skeleton() {
    return <div className="card" style={{ height: 196, background: "linear-gradient(90deg,#F1F5F9,#F8FAFC,#F1F5F9)" }} aria-hidden />;
}

function JobList() {
    const router = useRouter();
    const pathname = usePathname();
    const params = useSearchParams();
    const q = params.get("q") ?? "";
    const job = params.get("job") ?? "";
    const page = Number(params.get("page") ?? "1");
    const [draft, setDraft] = useState(q);
    const [codes, setCodes] = useState<JobCode[]>([]);
    const [data, setData] = useState<ListResponse | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [nowMs] = useState(() => Date.now());

    const load = useCallback(async () => {
        setError(null);
        setData(null);
        try {
            const query = new URLSearchParams({ q, job_code: job, page: String(page) });
            setData(await api<ListResponse>(`/postings?${query}`));
        } catch (err) {
            setError((err as ApiError).message);
        }
    }, [q, job, page]);

    useEffect(() => {
        // 필터·검색·페이지가 바뀌면 다시 불러온다
        // eslint-disable-next-line react-hooks/set-state-in-effect
        void load();
    }, [load]);

    useEffect(() => {
        api<{ items: JobCode[] }>("/job-codes").then((r) => setCodes(r.items)).catch(() => setCodes([]));
    }, []);

    function go(next: { q?: string; job?: string; page?: number }) {
        const query = new URLSearchParams();
        const nq = next.q ?? q;
        const nj = next.job ?? job;
        if (nq) query.set("q", nq);
        if (nj) query.set("job", nj);
        if ((next.page ?? 1) > 1) query.set("page", String(next.page));
        router.push(`${pathname}${query.size ? `?${query}` : ""}`);
    }

    const filtered = Boolean(q || job);
    const pages = data ? Math.max(1, Math.ceil(data.total / data.size)) : 1;

    return (
        <div className="container stack">
            <section className="card mascot-hero" style={{ background: "linear-gradient(120deg,#EFF6FF,#FFFFFF)" }}>
                <Mascot name="01-guide" size={150} />
                <div>
                    <h1>AI 면접으로 시작하는 1차 전형</h1>
                    <p className="muted">공고를 고르고 지원하면, 준비가 끝난 뒤 원하는 시간에 AI 면접을 볼 수 있습니다. 결과는 마감 다음 날 10시에 공개됩니다.</p>
                </div>
            </section>

            <form className="row" role="search" onSubmit={(e) => { e.preventDefault(); go({ q: draft.trim() }); }}>
                <label className="sr-only" htmlFor="q">공고명 검색</label>
                <input id="q" className="input" style={{ flex: 1, minWidth: 240 }} value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="🔍 공고명 검색" />
                <button type="submit" className="btn btn-secondary">검색</button>
            </form>

            <div className="row" role="group" aria-label="직무 필터">
                <span className="small" style={{ fontWeight: 600 }}>직무</span>
                <button type="button" className={`badge ${job === "" ? "badge-blue" : "badge-gray"}`} style={{ border: 0, cursor: "pointer", height: 32 }}
                    aria-pressed={job === ""} onClick={() => go({ job: "" })}>전체</button>
                {codes.map((c) => c.status === "open" ? (
                    <button key={c.code} type="button" className={`badge ${job === c.code ? "badge-blue" : "badge-gray"}`} style={{ border: 0, cursor: "pointer", height: 32 }}
                        aria-pressed={job === c.code} onClick={() => go({ job: c.code })}>{c.name}</button>
                ) : (
                    <span key={c.code} className="badge badge-gray" style={{ height: 32, opacity: .6, cursor: "not-allowed" }} title="준비 중인 직무입니다" aria-disabled>
                        {c.name} 준비 중
                    </span>
                ))}
            </div>

            {error && <ErrorBox message={error} onRetry={load} />}
            {!error && !data && <div className="grid2">{Array.from({ length: 6 }, (_, i) => <Skeleton key={i} />)}</div>}
            {data && (
                <>
                    <p className="small muted">접수 중인 공고 {data.total}건</p>
                    {data.items.length === 0 ? (
                        filtered ? (
                            <Empty title="조건에 맞는 공고가 없습니다">
                                <button type="button" className="btn btn-secondary" style={{ marginTop: 12 }} onClick={() => { setDraft(""); router.push(pathname); }}>필터 초기화</button>
                            </Empty>
                        ) : <Empty title="지금 접수 중인 공고가 없습니다" />
                    ) : (
                        <div className="grid2">
                            {data.items.map((p) => {
                                const dday = untilText(nowMs, p.close_at);
                                const urgent = new Date(p.close_at).getTime() - nowMs <= 3 * 86_400_000;
                                return (
                                    <Link key={p.posting_id} href={`/jobs/${p.posting_id}`} className="card card-link stack">
                                        <div className="row">
                                            <span className="badge badge-blue">AI/AX 엔지니어</span>
                                            {p.has_coding_test && <span className="badge badge-gray">코딩테스트 포함</span>}
                                            <span style={{ flex: 1 }} />
                                            {p.my_attempt_status && <StatusBadge status={p.my_attempt_status} />}
                                        </div>
                                        <div>
                                            <h3 style={{ margin: "2px 0 6px" }}>{p.title}</h3>
                                            <div className="small muted">{EMPLOYMENT_LABEL[p.employment_type] ?? p.employment_type} · {p.location} · {p.headcount}명</div>
                                        </div>
                                        <div className="row between small">
                                            <span style={{ color: urgent ? "var(--color-danger)" : undefined, fontWeight: 600 }}>마감 {dday} ({shortDateTime(p.close_at).slice(0, 5)})</span>
                                            <span className="muted">결과 {shortDateTime(p.release_at).slice(0, 5)} 공개</span>
                                        </div>
                                    </Link>
                                );
                            })}
                        </div>
                    )}
                    {pages > 1 && (
                        <nav className="row" style={{ justifyContent: "center" }} aria-label="페이지">
                            <button type="button" className="btn btn-secondary btn-sm" disabled={page <= 1} onClick={() => go({ page: page - 1 })}>‹ 이전</button>
                            <span className="small">{page} / {pages}</span>
                            <button type="button" className="btn btn-secondary btn-sm" disabled={page >= pages} onClick={() => go({ page: page + 1 })}>다음 ›</button>
                        </nav>
                    )}
                </>
            )}
        </div>
    );
}

export default function JobsPage() {
    return <SiteShell><Suspense><JobList /></Suspense></SiteShell>;
}
