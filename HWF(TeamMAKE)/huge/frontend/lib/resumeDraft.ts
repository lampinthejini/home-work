import type { ResumeData } from "@/components/ApplyFlow";

// S-A04 → S-A05 로 넘기는 이력서 임시값. 이 창(sessionStorage)에만 두고 제출하면 지운다
// low_conf_fields: OCR 신뢰도가 낮아 확인이 필요한 칸 (예: career[0].company)
export type Draft = { method: "upload" | "manual" | "saved"; upload_id: string | null; resume: ResumeData; low_conf_fields?: string[] };

export const draftKey = (applicationId: string) => `huge:resume-draft:${applicationId}`;
