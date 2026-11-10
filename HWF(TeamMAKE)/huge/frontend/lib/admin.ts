// 관리자 화면 공통 형식

export type Criteria = { version: number; locked: boolean; weights: Record<string, number>; coding_enabled: boolean; coding_ratio: number; pass_score: number };

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
