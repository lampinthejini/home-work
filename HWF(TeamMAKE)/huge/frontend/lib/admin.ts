// 관리자 화면 공통 형식

export type Criteria = {
    version: number; locked: boolean; weights: Record<string, number>; coding_enabled: boolean; coding_ratio: number; pass_score: number;
    // 서류 평가 (CONFLICTS C-25, 모든 공고)
    screening_required_skills?: string[]; screening_preferred_skills?: string[];
    screening_pass_score?: number; screening_band?: number;
};

export type AdminPosting = {
    posting_id: string; status: "draft" | "published" | "closed"; source: string; title: string; job_code: string;
    company_intro: string; duties: string; requirements: string; preferred: string; employment_type: string; location: string;
    headcount: number; open_at: string | null; close_at: string | null; release_at: string | null; contact_email: string;
    has_coding_test: boolean; criteria: Criteria | null; created_at: string; updated_at: string; applicant_count?: number;
    revisions?: { revised_at: string; field: string; summary: string }[];
};

/** GET /admin/postings/{id}/draft-ai/status. stage: retrieve(참고 공고) · draft(초안) · check(점검) · rewrite(다시 쓰기) */
export type DraftStatus = {
    status: "running" | "done" | "failed"; stage: string | null; bias_warnings: { text: string; reason: string }[];
    notes: string[]; revision: { section: string; text: string } | null; error: string | null;
};

export const DEFAULT_WEIGHTS: Record<string, number> = { expertise: 30, logic: 25, relevance: 20, delivery: 10, culture_fit: 15 };

const WEIGHT_STEP = 5;
const WEIGHT_UNITS = 100 / WEIGHT_STEP;

/**
 * 합계가 100%가 아닌 가중치를 비율을 지켜 100%로 맞춘다 (2026-11-17 사용자 요청).
 * 5% 단위·항목당 5% 이상 규칙 때문에 비율은 가장 가깝게만 맞는다: 내림한 뒤 남는 칸은 소수점이 큰 항목부터,
 * 같으면 원래 값이 큰 항목, 그다음 화면 순서로 준다.
 */
export function fitWeights(weights: Record<string, number>): Record<string, number> {
    const keys = Object.keys(weights);
    const sum = keys.reduce((a, k) => a + weights[k], 0);
    if (sum <= 0) return { ...weights };
    const raw = keys.map((k) => (weights[k] / sum) * WEIGHT_UNITS);
    const units = raw.map((r) => Math.max(1, Math.floor(r)));
    const order = keys.map((_, i) => i).sort((a, b) => (raw[b] - units[b]) - (raw[a] - units[a]) || weights[keys[b]] - weights[keys[a]] || a - b);
    let left = WEIGHT_UNITS - units.reduce((a, b) => a + b, 0);
    for (let i = 0; left > 0; i = (i + 1) % order.length, left--) units[order[i]]++;
    for (let i = order.length - 1; left < 0; i = (i - 1 + order.length) % order.length) {
        if (units[order[i]] > 1) { units[order[i]]--; left++; }
    }
    return Object.fromEntries(keys.map((k, i) => [k, units[i] * WEIGHT_STEP]));
}
