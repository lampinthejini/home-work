"use client";

import { useCallback, useEffect, useState } from "react";

import { AdminShell } from "@/components/AdminShell";
import { useApp } from "@/components/Providers";
import { Button, Empty, ErrorBox, Loading } from "@/components/Ui";
import { api, ApiError } from "@/lib/api";
import { dateOnly, shortDateTime } from "@/lib/format";

// 회사 정보 (2026-11-16 사용자 결정, CONFLICTS C-20). 회사 질문(RAG)과 AI 공고 초안이 이 내용을 쓴다
type Profile = { name: string; basics: string; intro: string; jobs_intro: string; ai_ax_role: string; news_query: string; news_refreshed_at: string | null };
type News = { id: number; title: string; url: string; publisher: string; published_at: string | null };
type Company = { profile: Profile; news: News[]; news_limit: number; refresh?: { ok: boolean; added: number; total: number } };
type Field = Exclude<keyof Profile, "news_refreshed_at">;

const FIELDS: { key: Field; label: string; rows?: number; hint?: string }[] = [
    { key: "name", label: "회사 이름", hint: "공고와 면접 질문에 이 이름이 쓰입니다." },
    { key: "basics", label: "기본 정보", rows: 6 },
    { key: "intro", label: "회사 소개", rows: 5 },
    { key: "jobs_intro", label: "직무 소개", rows: 6 },
    { key: "ai_ax_role", label: "AI/AX 가 하는 일", rows: 6 },
    { key: "news_query", label: "최근 소식 검색어", hint: "앱을 켤 때 이 말로 최근 6개월 뉴스를 찾습니다. 질문에 넣을 때는 검색어를 회사 이름으로 바꿉니다." },
];

function CompanyBody() {
    const { toast } = useApp();
    const [data, setData] = useState<Company | null>(null);
    const [form, setForm] = useState<Profile | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [busy, setBusy] = useState<"save" | "refresh" | number | null>(null);

    const apply = useCallback((c: Company) => { setData(c); setForm(c.profile); setError(null); }, []);

    const load = useCallback(() => {
        api<Company>("/admin/company").then(apply).catch((err) => setError((err as ApiError).message));
    }, [apply]);

    useEffect(() => { load(); }, [load]);

    async function run(kind: "save" | "refresh" | number, request: () => Promise<Company>, done?: (c: Company) => void) {
        setBusy(kind);
        try {
            const c = await request();
            if (kind === "save") apply(c);
            else setData(c);
            done?.(c);
        } catch (err) {
            toast("error", (err as ApiError).message);
        } finally {
            setBusy(null);
        }
    }

    if (error) return <ErrorBox message={error} onRetry={load} />;
    if (!data || !form) return <Loading />;
    const changed = FIELDS.some((f) => form[f.key] !== data.profile[f.key]);
    return (
        <div className="stack">
            <section className="card stack">
                <div className="row between">
                    <h2 style={{ margin: 0, fontSize: 17 }}>회사 정보</h2>
                    <Button size="sm" busy={busy === "save"} disabled={!changed || busy !== null}
                        onClick={() => run("save", () => api<Company>("/admin/company", { method: "PUT", body: form }), () => toast("ok", "저장했습니다."))}>
                        저장
                    </Button>
                </div>
                {FIELDS.map((f) => (
                    <label key={f.key} className="field">
                        <span>{f.label}</span>
                        {f.rows ? (
                            <textarea className="input" rows={f.rows} maxLength={3000} value={form[f.key]}
                                onChange={(e) => setForm({ ...form, [f.key]: e.target.value })} />
                        ) : (
                            <input className="input" maxLength={100} value={form[f.key]} onChange={(e) => setForm({ ...form, [f.key]: e.target.value })} />
                        )}
                        {f.hint && <div className="field-hint">{f.hint}</div>}
                    </label>
                ))}
            </section>
            <section className="card stack">
                <div className="row between">
                    <div>
                        <h2 style={{ margin: 0, fontSize: 17 }}>회사 최근 소식 <span className="small muted">{data.news.length}/{data.news_limit}</span></h2>
                        <div className="small muted">
                            최근 6개월 뉴스·게시글입니다. 회사 관련 질문을 만들 때 관련 있는 소식을 골라 씁니다.
                            {data.profile.news_refreshed_at && ` 마지막으로 찾은 시각: ${shortDateTime(data.profile.news_refreshed_at)}`}
                        </div>
                    </div>
                    <Button size="sm" kind="secondary" busy={busy === "refresh"} disabled={busy !== null}
                        onClick={() => run("refresh", () => api<Company>("/admin/company/news/refresh", { method: "POST" }), (c) => {
                            if (c.refresh?.ok) toast("ok", `새 소식 ${c.refresh.added}개를 찾았습니다.`);
                            else toast("warn", "소식을 찾지 못했습니다. 인터넷 연결을 확인해 주세요. 있던 소식은 그대로 둡니다.");
                        })}>
                        새로 찾기
                    </Button>
                </div>
                {data.news.length === 0 ? <Empty title="최근 소식이 없습니다" /> : (
                    <table className="table">
                        <thead><tr><th>제목</th><th style={{ width: 140 }}>출처</th><th style={{ width: 120 }}>날짜</th><th style={{ width: 80 }} /></tr></thead>
                        <tbody>
                            {data.news.map((n) => (
                                <tr key={n.id}>
                                    <td><a href={n.url} target="_blank" rel="noopener noreferrer">{n.title}</a></td>
                                    <td className="small">{n.publisher}</td>
                                    <td className="small">{dateOnly(n.published_at)}</td>
                                    <td>
                                        <Button size="sm" kind="secondary" busy={busy === n.id} disabled={busy !== null}
                                            onClick={() => run(n.id, () => api<Company>(`/admin/company/news/${n.id}/hide`, { method: "POST" }))}>
                                            제거
                                        </Button>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                )}
            </section>
        </div>
    );
}

export default function CompanyPage() {
    return <AdminShell title="회사 정보"><CompanyBody /></AdminShell>;
}
