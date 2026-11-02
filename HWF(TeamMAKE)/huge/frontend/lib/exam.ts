// 면접 세션 정보 (start · resume 응답). 응시 창(sessionStorage)에만 둔다

export type ExamSession = {
    session_id: string;
    ws_url: string;
    question_total: number;
    questions_ready: boolean;
    recording_segment: number;
    phase?: "interview" | "coding";
    resume_seq?: number;
};

export const examSessionKey = (applicationId: string) => `huge:exam:${applicationId}`;

export function loadExamSession(applicationId: string): ExamSession | null {
    try {
        const raw = sessionStorage.getItem(examSessionKey(applicationId));
        return raw ? (JSON.parse(raw) as ExamSession) : null;
    } catch {
        return null;
    }
}

/** 창 닫기·새로고침 신호. Blob(JSON)으로 보내 사전 요청 없이 같은 출처로 간다 (API 명세서 6장) */
export function sendUnloadBeacon(sessionId: string, detail: string) {
    const body = new Blob([JSON.stringify({ type: "unload", at: new Date().toISOString(), detail })], { type: "application/json" });
    navigator.sendBeacon(`/api/interview/${sessionId}/events`, body);
}
