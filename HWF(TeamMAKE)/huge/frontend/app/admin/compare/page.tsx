"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { AdminShell } from "@/components/AdminShell";
import { ErrorBox, Loading } from "@/components/Ui";
import { api, ApiError } from "@/lib/api";
import { EVAL_LABEL } from "@/lib/status";

type Item = {
    application_id: string; name: string; posting_title: string; analysis_status: string; decision: "pass" | "fail" | null;
    total_score: string | null; interview_score: string | null; coding_score: string | null; pass_score: string | null;
    item_scores: Record<string, string | number | null>; strengths: string[]; improvements: string[];
};
const ITEMS = Object.keys(EVAL_LABEL);
const COLORS = ["var(--color-primary)", "var(--color-warning)", "var(--color-success)"];

function Radar({ items }: { items: Item[] }) {
    // 항목 점수 레이더 (0~100). 같은 값은 위 표에도 있다 (접근성)
    const size = 280, center = size / 2, radius = 100;
    const point = (i: number, value: number) => {
        const angle = -Math.PI / 2 + (2 * Math.PI * i) / ITEMS.length;
        return [center + Math.cos(angle) * radius * value / 100, center + Math.sin(angle) * radius * value / 100];
    };
    return (
        <svg width={size} height={size} role="img" aria-label="항목 점수 레이더 차트 (값은 표와 같습니다)">
            {[25, 50, 75, 100].map((ring) => (
                <polygon key={ring} points={ITEMS.map((_, i) => point(i, ring).join(",")).join(" ")} fill="none" stroke="var(--color-line)" />
            ))}
            {ITEMS.map((item, i) => {
                const [x, y] = point(i, 118);
                return <text key={item} x={x} y={y} fontSize="11" textAnchor="middle" dominantBaseline="middle" fill="var(--color-neutral)">{EVAL_LABEL[item]}</text>;
            })}
            {items.map((it, n) => (
                <polygon key={it.application_id} fill={COLORS[n]} fillOpacity={0.12} stroke={COLORS[n]} strokeWidth={2}
                    points={ITEMS.map((item, i) => point(i, Number(it.item_scores[item] ?? 0)).join(",")).join(" ")} />
            ))}
        </svg>
    );
}

function Compare() {
    const params = useSearchParams();
    const ids = params.get("ids") ?? "";
    const [data, setData] = useState<{ items: Item[]; same_posting: boolean } | null>(null);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        api<{ items: Item[]; same_posting: boolean }>(`/admin/applicants/compare?ids=${encodeURIComponent(ids)}`)
            .then(setData).catch((err) => setError((err as ApiError).message));
    }, [ids]);

    if (error) return <ErrorBox message={error} />;
    if (!data) return <Loading />;
    const rows: [string, (it: Item) => React.ReactNode][] = [
        ["AI 1차 판정", (it) => it.decision === "pass" ? <span className="badge badge-green">1차 합격</span> : it.decision === "fail" ? <span className="badge badge-gray">1차 불합격</span> : "판정 전"],
        ["종합 총점", (it) => it.total_score ?? "—"],
        ["AI 면접", (it) => it.interview_score ?? "—"],
        ["코딩테스트", (it) => it.coding_score ?? "—"],
        ...ITEMS.map((item) => [EVAL_LABEL[item], (it: Item) => it.item_scores[item] ?? "—"] as [string, (it: Item) => React.ReactNode]),
        ["강점", (it) => <ul className="small" style={{ margin: 0, paddingLeft: 16 }}>{it.strengths.map((s) => <li key={s}>{s}</li>)}</ul>],
        ["개선점", (it) => <ul className="small" style={{ margin: 0, paddingLeft: 16 }}>{it.improvements.map((s) => <li key={s}>{s}</li>)}</ul>],
    ];
    return (
        <div className="stack">
            <div className="row between">
                <Link href="/admin/applicants" className="small">← 지원자 목록</Link>
                <span className="small muted">ⓘ 참고용이며 결과는 바뀌지 않습니다</span>
            </div>
            {!data.same_posting && <div className="notice notice-warn small">서로 다른 공고의 지원자입니다. 공고마다 평가 기준이 달라 점수를 그대로 비교하기 어렵습니다.</div>}
            <div className="card" style={{ padding: 0, overflow: "auto" }}>
                <table className="table">
                    <thead><tr>
                        <th style={{ width: 160 }} />
                        {data.items.map((it, n) => (
                            <th key={it.application_id}><span aria-hidden style={{ color: COLORS[n] }}>● </span>{it.name}<div className="tiny muted">{it.posting_title}</div></th>
                        ))}
                    </tr></thead>
                    <tbody>
                        {rows.map(([label, cell]) => (
                            <tr key={label}><th scope="row" className="small">{label}</th>{data.items.map((it) => <td key={it.application_id}>{cell(it)}</td>)}</tr>
                        ))}
                        <tr><th scope="row" /> {data.items.map((it) => (
                            <td key={it.application_id}><Link className="btn btn-secondary btn-sm" href={`/admin/applicants/${it.application_id}`}>상세 보기</Link></td>
                        ))}</tr>
                    </tbody>
                </table>
            </div>
            <div className="card center"><h3 style={{ marginTop: 0 }}>항목 점수 레이더</h3><Radar items={data.items} /></div>
        </div>
    );
}

export default function ComparePage() {
    return <AdminShell title="지원자 비교"><Suspense><Compare /></Suspense></AdminShell>;
}
