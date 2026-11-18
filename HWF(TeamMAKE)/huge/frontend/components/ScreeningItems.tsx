// 서류 평가 결과 (CONFLICTS C-25): 세 축(직무 적합·회사 적합·적응·성장)별 항목 단계와 근거 문장.
// 지원자 결과 화면은 단계·근거만, 관리자 지원자 상세는 점수까지 보여 준다

export type Axis = "job" | "company" | "growth";
export const AXIS_LABEL: Record<Axis, string> = { job: "직무 적합", company: "회사 적합 (인재상)", growth: "적응·성장" };
const AXIS_WEIGHT: Record<Axis, number> = { job: 50, company: 30, growth: 20 };
// 추가 서류 종류 (backend services/resume_screening.DOC_KINDS). 자기소개서 하나 — 다른 서류를 올려도 자기소개서로 본다
export const DOC_KIND_LABEL: Record<string, string> = { cover_letter: "자기소개서" };
// 서류 평가 예상 시간 안내 (실측 2026-11-18: 1차 25~45초, 2차까지 가면 5~7분. LLM 은 한 번에 한 건씩이라 앞 건을 기다림)
export const SCREENING_TIME_NOTE = "서류 평가는 보통 1분 안팎 걸립니다. 합격선 근처면 더 큰 AI가 한 번 더 확인해 5~7분 걸리고, "
    + "다른 지원자의 서류 평가나 면접 채점이 먼저 진행 중이면 그만큼 더 걸릴 수 있습니다.";

export type ScreeningItem = {
    item: string; label: string; axis: Axis; level: number; max_level: number; level_text: string;
    evidence: string; reason: string;
    // 지원자에게만
    appealable?: boolean;
    // 관리자에게만
    weight?: number; points?: number; grounded?: boolean; by?: "code";
};

export type AppealView = {
    status: "pending" | "running" | "accepted" | "rejected" | "error"; at: string | null; done_at: string | null;
    claims: { item: string; text: string }[];
    items: { item: string; label: string; before: number; after: number; accepted: boolean; evidence: string; reason: string }[];
};

export type ScreeningView = {
    stage: "first" | "second" | "done" | "error"; decision: "pass" | "fail" | null; decided_by: "ai" | "appeal" | null;
    used_round: "first" | "second" | null; items: ScreeningItem[]; finished_at: string | null; appeal: AppealView | null;
    // 관리자만
    pass_score?: number | null; band?: number | null; final_total?: number | null; first_total?: number | null;
    second_total?: number | null; appeal_total?: number | null;
    rounds?: { first?: ScreeningItem[]; second?: ScreeningItem[] }; error_count?: number; last_error?: string | null;
    timings?: { first_sec?: number; second_sec?: number };
};

export function ScreeningItems({ items, showPoints = false }: { items: ScreeningItem[]; showPoints?: boolean }) {
    return (
        <div className="stack" style={{ gap: 16 }}>
            {(Object.keys(AXIS_LABEL) as Axis[]).map((axis) => {
                const rows = items.filter((r) => r.axis === axis);
                if (rows.length === 0) return null;
                return (
                    <div key={axis} style={{ overflowX: "auto" }}>
                        <h4 style={{ margin: "0 0 6px" }}>{AXIS_LABEL[axis]}{showPoints && <span className="small muted"> ({AXIS_WEIGHT[axis]}점)</span>}</h4>
                        <table className="table">
                            <thead>
                                <tr>
                                    <th style={{ width: "22%" }}>항목</th><th style={{ width: "22%" }}>단계</th>
                                    {showPoints && <th style={{ textAlign: "right" }}>점수</th>}
                                    <th>근거 문장</th><th>이유</th>
                                </tr>
                            </thead>
                            <tbody>
                                {rows.map((r) => (
                                    <tr key={r.item}>
                                        <td><strong>{r.label}</strong></td>
                                        <td className="small">
                                            {r.level} / {r.max_level} · {r.level_text}
                                        </td>
                                        {showPoints && (
                                            <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                                                {`${(r.points ?? 0).toFixed(1)} / ${r.weight}`}
                                            </td>
                                        )}
                                        <td className="small">{r.evidence || <span className="muted">없음</span>}</td>
                                        <td className="small">
                                            {r.reason}
                                            {r.by === "code" && <span className="tiny muted"> ({r.item === "certificate" ? "직무 관련 자격증 표와 맞춰" : "공고 기술과 이름을 맞춰"} 시스템이 계산)</span>}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                );
            })}
        </div>
    );
}

export const APPEAL_STATUS_LABEL: Record<AppealView["status"], string> = {
    pending: "다시 평가 대기", running: "다시 평가하는 중", accepted: "받아들여짐 (서류 합격)", rejected: "반려", error: "다시 평가 대기 (AI 장애)",
};

/** 이의 신청 결과: 항목마다 처음 단계 → 다시 평가한 단계, 받아들였는지와 이유 */
export function AppealResult({ appeal }: { appeal: AppealView }) {
    if (appeal.items.length === 0) return null;
    return (
        <table className="table">
            <thead><tr><th>항목</th><th>단계</th><th>결과</th><th>근거 · 이유</th></tr></thead>
            <tbody>
                {appeal.items.map((r) => (
                    <tr key={r.item}>
                        <td><strong>{r.label}</strong></td>
                        <td style={{ whiteSpace: "nowrap" }}>{r.before} → {r.after}</td>
                        <td>{r.accepted ? "받아들임" : "반려"}</td>
                        <td className="small">{r.evidence && <div>“{r.evidence}”</div>}<div className="muted">{r.reason}</div></td>
                    </tr>
                ))}
            </tbody>
        </table>
    );
}
