// 서류 평가 결과 (CONFLICTS C-24): 항목별 단계·점수·근거 문장. 지원자 결과 화면과 관리자 지원자 상세에서 같이 쓴다

export type ScreeningItem = {
    item: string; label: string; weight: number; level: number; max_level: number; points: number;
    evidence: string; reason: string; grounded: boolean; by?: "code";
};

export type ScreeningView = {
    stage: "first" | "second" | "done" | "error"; decision: "pass" | "fail" | null; decided_by: "ai" | "admin" | null;
    base_score: number; pass_score: number | null; band: number | null; final_total: number | null;
    used_round: "first" | "second" | null; items: ScreeningItem[]; finished_at: string | null; appeal_at: string | null;
    // 관리자만
    first_total?: number | null; second_total?: number | null; rounds?: { first?: ScreeningItem[]; second?: ScreeningItem[] };
    error_count?: number; last_error?: string | null; appeal_text?: string | null; override_note?: string | null; override_at?: string | null;
};

export function ScreeningItems({ items }: { items: ScreeningItem[] }) {
    return (
        <div style={{ overflowX: "auto" }}>
            <table className="table">
                <thead>
                    <tr><th>항목</th><th style={{ textAlign: "right" }}>단계</th><th style={{ textAlign: "right" }}>점수</th><th>근거 문장</th><th>이유</th></tr>
                </thead>
                <tbody>
                    {items.map((r) => (
                        <tr key={r.item}>
                            <td><strong>{r.label}</strong></td>
                            <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>{r.level} / {r.max_level}</td>
                            <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>{r.points.toFixed(1)} / {r.weight}</td>
                            <td className="small">{r.evidence || <span className="muted">없음</span>}</td>
                            <td className="small">
                                {r.reason}
                                {r.by === "code" && <span className="tiny muted"> (공고 기술과 이름을 맞춰 시스템이 계산)</span>}
                            </td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}

export function scoreLine(v: ScreeningView): string {
    return `기본 ${v.base_score}점 + 항목 점수 = ${v.final_total?.toFixed(1) ?? "-"}점 (합격선 ${v.pass_score ?? "-"}점)`;
}
