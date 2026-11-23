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

export const DEFAULT_WEIGHTS: Record<string, number> = { expertise: 30, logic: 25, relevance: 25, delivery: 5, culture_fit: 15 };


// 기술 이름이 아닌 영문 약어 (공고 글에서 기술을 뽑을 때 뺀다)
const NOT_SKILLS = new Set(["ai", "ax", "it", "db", "api", "ui", "ux", "os", "pc", "sw", "hw", "kpi", "poc", "b2b", "b2c", "saas", "qa", "pm", "cs", "ml", "dl"]);

/**
 * 공고 글에서 기술 이름(영문 표기)을 뽑는다 (2026-11-22 사용자: 서류 평가 필수 기술을 자동으로 채우고 고칠 수 있게).
 * LLM 을 쓰지 않는다 — 공고에 적힌 영문 기술 이름을 그대로 옮기고, 같은 이름은 한 번만 쓴다.
 */
export function skillsInText(text: string): string[] {
    const found: string[] = [];
    for (const m of text.matchAll(/(?<![A-Za-z0-9.+#-])[A-Za-z][A-Za-z0-9.+#-]*[A-Za-z0-9+#]|(?<![A-Za-z0-9])[CR](?![A-Za-z0-9])/g)) {
        const name = m[0];
        if (NOT_SKILLS.has(name.toLowerCase()) || found.some((f) => f.toLowerCase() === name.toLowerCase())) continue;
        found.push(name);
    }
    return found;
}

/** 필수 기술 = 자격 요건(없으면 주요 업무)의 기술, 우대 기술 = 우대 사항의 기술 가운데 필수가 아닌 것 */
export function suggestSkills(requirements: string, duties: string, preferred: string): { required: string[]; preferred: string[] } {
    const required = skillsInText(requirements).length ? skillsInText(requirements) : skillsInText(duties);
    const lower = new Set(required.map((s) => s.toLowerCase()));
    return { required: required.slice(0, 20), preferred: skillsInText(preferred).filter((s) => !lower.has(s.toLowerCase())).slice(0, 20) };
}
