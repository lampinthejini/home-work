"use client";

import { useCallback, useEffect, useState } from "react";

import { AdminShell } from "@/components/AdminShell";
import { useApp } from "@/components/Providers";
import { Button, Empty, ErrorBox, Loading } from "@/components/Ui";
import { api, ApiError } from "@/lib/api";
import { dateOnly, shortDateTime } from "@/lib/format";

// 회사 정보 (2026-11-16 사용자 결정 CONFLICTS C-20, 2026-11-17 C-21). 회사 질문(RAG)과 AI 공고 초안이 이 내용을 쓴다
type Profile = {
    name: string; basics: string; intro: string; mission: string; talent: string; jobs_intro: string; ai_ax_role: string;
    tech_stack: string; tech_feed_url: string; tech_source_name: string; tech_refreshed_at: string | null;
};
type TechPost = { id: number; title: string; url: string; summary: string; published_at: string | null };
type Project = { id: number; title: string; period: string; summary: string };
type ProjectForm = Omit<Project, "id">;
type Company = {
    profile: Profile; projects: Project[]; project_limit: number; tech_posts: TechPost[]; tech_post_limit: number;
    refresh?: { ok: boolean; added: number; total: number };
};
type Field = Exclude<keyof Profile, "tech_refreshed_at">;
type Busy = "save" | "add" | "refresh" | `save-${number}` | `delete-${number}` | `hide-${number}`;

const EMPTY_PROJECT: ProjectForm = { title: "", period: "", summary: "" };
const DIVIDER = { borderTop: "1px solid var(--line, #e5e7eb)", paddingTop: 12 };

const FIELDS: { key: Field; label: string; rows?: number; hint?: string }[] = [
    { key: "name", label: "회사 이름", hint: "공고와 면접 질문에 이 이름이 쓰입니다." },
    { key: "basics", label: "기본 정보", rows: 6 },
    { key: "intro", label: "회사 소개", rows: 5 },
    { key: "mission", label: "경영 이념", rows: 5, hint: "미션·비전·핵심 가치·AI 윤리 원칙. 회사 질문에 씁니다." },
    { key: "talent", label: "인재상과 일하는 방식", rows: 6, hint: "회사 질문과 AI 공고 초안(자격 요건)에 씁니다." },
    { key: "jobs_intro", label: "직무 소개", rows: 6 },
    { key: "ai_ax_role", label: "AI/AX 가 하는 일", rows: 6 },
    { key: "tech_stack", label: "사내 기술 스택", rows: 5, hint: "AI 공고 초안(필요 기술)에 씁니다." },
    { key: "tech_feed_url", label: "기술 블로그 주소 (Atom/RSS)", hint: "https 주소만 됩니다. 비우면 가져오지 않습니다." },
    { key: "tech_source_name", label: "기술 블로그에서 회사 이름으로 바꿀 말", hint: "쉼표로 여러 개. 화면과 질문에서 이 말을 회사 이름으로 바꿔 보여 줍니다." },
];

function ProjectFields({ value, onChange }: { value: ProjectForm; onChange: (next: ProjectForm) => void }) {
    return (
        <>
            <div className="row" style={{ gap: 8 }}>
                <label className="field" style={{ flex: 3 }}>
                    <span>프로젝트 이름</span>
                    <input className="input" maxLength={100} value={value.title} onChange={(e) => onChange({ ...value, title: e.target.value })} />
                </label>
                <label className="field" style={{ flex: 1 }}>
                    <span>기간</span>
                    <input className="input" maxLength={50} placeholder="예: 2023~2024" value={value.period}
                        onChange={(e) => onChange({ ...value, period: e.target.value })} />
                </label>
            </div>
            <label className="field">
                <span>내용</span>
                <textarea className="input" rows={3} maxLength={1000} value={value.summary}
                    onChange={(e) => onChange({ ...value, summary: e.target.value })} />
            </label>
        </>
    );
}

function CompanyBody() {
    const { toast } = useApp();
    const [data, setData] = useState<Company | null>(null);
    const [form, setForm] = useState<Profile | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [busy, setBusy] = useState<Busy | null>(null);
    const [edits, setEdits] = useState<Record<number, ProjectForm>>({});
    const [draft, setDraft] = useState<ProjectForm>(EMPTY_PROJECT);

    const apply = useCallback((c: Company) => { setData(c); setForm(c.profile); setError(null); }, []);

    const load = useCallback(() => {
        api<Company>("/admin/company").then(apply).catch((err) => setError((err as ApiError).message));
    }, [apply]);

    useEffect(() => { load(); }, [load]);

    async function run(kind: Busy, request: () => Promise<Company>, done?: (c: Company) => void) {
        setBusy(kind);
        try {
            const c = await request();
            if (kind === "save") apply(c);
            else setData(c); // 프로젝트를 고쳐도 쓰고 있던 회사 정보 칸은 그대로 둔다
            done?.(c);
        } catch (err) {
            toast("error", (err as ApiError).message);
        } finally {
            setBusy(null);
        }
    }

    function dropEdit(id: number) {
        const rest = { ...edits };
        delete rest[id];
        setEdits(rest);
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
                            <input className="input" maxLength={f.key === "tech_feed_url" ? 500 : 100} value={form[f.key]}
                                onChange={(e) => setForm({ ...form, [f.key]: e.target.value })} />
                        )}
                        {f.hint && <div className="field-hint">{f.hint}</div>}
                    </label>
                ))}
            </section>
            <section className="card stack">
                <div>
                    <h2 style={{ margin: 0, fontSize: 17 }}>
                        회사가 진행한 프로젝트 <span className="small muted">{data.projects.length}/{data.project_limit}</span>
                    </h2>
                    <div className="small muted">
                        회사 관련 면접 질문과 AI 공고 초안을 만들 때 내용이 가까운 프로젝트를 골라 씁니다. 무엇을 왜 했고, 어떤 기술과 결과가 있었는지 적어 주세요.
                    </div>
                </div>
                {data.projects.length === 0 && <Empty title="적은 프로젝트가 없습니다" />}
                {data.projects.map((p) => {
                    const edit = edits[p.id] ?? { title: p.title, period: p.period, summary: p.summary };
                    const dirty = edit.title !== p.title || edit.period !== p.period || edit.summary !== p.summary;
                    return (
                        <div key={p.id} className="stack" style={DIVIDER}>
                            <ProjectFields value={edit} onChange={(next) => setEdits({ ...edits, [p.id]: next })} />
                            <div className="row" style={{ gap: 8, justifyContent: "flex-end" }}>
                                <Button size="sm" kind="secondary" busy={busy === `delete-${p.id}`} disabled={busy !== null}
                                    onClick={() => {
                                        if (!window.confirm(`'${p.title}' 프로젝트를 지울까요?`)) return;
                                        run(`delete-${p.id}`, () => api<Company>(`/admin/company/projects/${p.id}`, { method: "DELETE" }), () => dropEdit(p.id));
                                    }}>
                                    삭제
                                </Button>
                                <Button size="sm" busy={busy === `save-${p.id}`} disabled={!dirty || !edit.title.trim() || busy !== null}
                                    onClick={() => run(`save-${p.id}`, () => api<Company>(`/admin/company/projects/${p.id}`, { method: "PATCH", body: edit }), () => {
                                        dropEdit(p.id);
                                        toast("ok", "저장했습니다.");
                                    })}>
                                    저장
                                </Button>
                            </div>
                        </div>
                    );
                })}
                {data.projects.length < data.project_limit && (
                    <div className="stack" style={DIVIDER}>
                        <div className="small muted">새 프로젝트</div>
                        <ProjectFields value={draft} onChange={setDraft} />
                        <div className="row" style={{ justifyContent: "flex-end" }}>
                            <Button size="sm" busy={busy === "add"} disabled={!draft.title.trim() || busy !== null}
                                onClick={() => run("add", () => api<Company>("/admin/company/projects", { method: "POST", body: draft }), () => {
                                    setDraft(EMPTY_PROJECT);
                                    toast("ok", "프로젝트를 더했습니다.");
                                })}>
                                더하기
                            </Button>
                        </div>
                    </div>
                )}
            </section>
            <section className="card stack">
                <div className="row between">
                    <div>
                        <h2 style={{ margin: 0, fontSize: 17 }}>
                            회사 기술 블로그 최신 글 <span className="small muted">{data.tech_posts.length}/{data.tech_post_limit}</span>
                        </h2>
                        <div className="small muted">
                            앱을 켤 때 위 주소에서 가져옵니다. 회사 관련·직무 면접 질문을 만들 때 내용이 가까운 글을 질문마다 하나씩 골라 씁니다.
                            {data.profile.tech_refreshed_at && ` 마지막으로 가져온 시각: ${shortDateTime(data.profile.tech_refreshed_at)}`}
                        </div>
                    </div>
                    <Button size="sm" kind="secondary" busy={busy === "refresh"} disabled={busy !== null}
                        onClick={() => run("refresh", () => api<Company>("/admin/company/tech/refresh", { method: "POST" }), (c) => {
                            if (c.refresh?.ok) toast("ok", `새 글 ${c.refresh.added}개를 가져왔습니다.`);
                            else toast("warn", "글을 가져오지 못했습니다. 주소와 인터넷 연결을 확인해 주세요. 있던 글은 그대로 둡니다.");
                        })}>
                        새로 가져오기
                    </Button>
                </div>
                {data.tech_posts.length === 0 ? <Empty title="가져온 글이 없습니다" /> : (
                    <table className="table">
                        <thead><tr><th>제목</th><th style={{ width: 120 }}>날짜</th><th style={{ width: 80 }} /></tr></thead>
                        <tbody>
                            {data.tech_posts.map((p) => (
                                <tr key={p.id}>
                                    <td>
                                        <a href={p.url} target="_blank" rel="noopener noreferrer">{p.title}</a>
                                        {p.summary && <div className="small muted">{p.summary.slice(0, 120)}{p.summary.length > 120 ? "…" : ""}</div>}
                                    </td>
                                    <td className="small">{dateOnly(p.published_at)}</td>
                                    <td>
                                        <Button size="sm" kind="secondary" busy={busy === `hide-${p.id}`} disabled={busy !== null}
                                            onClick={() => run(`hide-${p.id}`, () => api<Company>(`/admin/company/tech/${p.id}/hide`, { method: "POST" }))}>
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
