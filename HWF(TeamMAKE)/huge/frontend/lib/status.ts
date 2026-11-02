// 응시 상태 이름·배지 색 (PRD 6-2, 화면정의서 §3.4 · §4.4)

export type AttemptStatus =
    | "drafting" | "ready" | "interviewing" | "coding" | "interrupted"
    | "completed" | "ended" | "ended_closed" | "cancelled" | "not_taken_closed";

export const ATTEMPT_LABEL: Record<AttemptStatus, string> = {
    drafting: "작성 중",
    ready: "면접 준비 중",
    interviewing: "면접 진행 중",
    coding: "코딩테스트 진행 중",
    interrupted: "장애 중단",
    completed: "응시 완료",
    ended: "응시 종료",
    ended_closed: "응시 종료(마감)",
    cancelled: "응시 취소",
    not_taken_closed: "미응시(마감)",
};

export const ATTEMPT_BADGE: Record<AttemptStatus, string> = {
    drafting: "badge-gray",
    ready: "badge-gray",
    interviewing: "badge-blue",
    coding: "badge-blue",
    interrupted: "badge-orange",
    completed: "badge-green",
    ended: "badge-gray",
    ended_closed: "badge-gray",
    cancelled: "badge-red",
    not_taken_closed: "badge-gray",
};

/** 공고 상세(S-A02)의 버튼·안내 (§3.4). 응시로 들어가는 버튼은 마이페이지에만 둔다 */
export const POSTING_BUTTON: Record<AttemptStatus, { label: string; active: boolean; hint: string }> = {
    drafting: { label: "지원 이어서 작성", active: true, hint: "지원서 작성이 끝나지 않았습니다" },
    ready: { label: "마이페이지에서 확인", active: true, hint: "환경 점검을 마치면 면접을 시작할 수 있습니다" },
    interviewing: { label: "응시 진행 중", active: false, hint: "다른 창에서 응시 중입니다" },
    coding: { label: "응시 진행 중", active: false, hint: "다른 창에서 응시 중입니다" },
    interrupted: { label: "마이페이지에서 확인", active: true, hint: "연결 문제로 중단되었습니다. 마이페이지에서 이어갈 수 있습니다" },
    completed: { label: "응시 완료", active: false, hint: "결과 공개일에 마이페이지에서 확인할 수 있습니다" },
    ended: { label: "응시 종료", active: false, hint: "지원자 조작으로 연결이 종료되어 답변한 문항까지 평가합니다" },
    ended_closed: { label: "접수 마감", active: false, hint: "마감이 되어 면접을 진행할 수 없습니다. 답변한 문항까지 평가합니다" },
    cancelled: { label: "응시 취소", active: false, hint: "화면 이탈 규칙에 따라 응시가 취소되었습니다" },
    not_taken_closed: { label: "접수 마감", active: false, hint: "마감이 되어 면접을 진행할 수 없습니다." },
};

export const EMPLOYMENT_LABEL: Record<string, string> = { full_time: "정규직", contract: "계약직", intern: "인턴" };

export const POSTING_STATUS: Record<string, { label: string; badge: string }> = {
    draft: { label: "임시저장", badge: "badge-gray" },
    published: { label: "게시 중", badge: "badge-green" },
    closed: { label: "마감", badge: "badge-dark" },
};

export const EVAL_LABEL: Record<string, string> = {
    expertise: "직무 전문성",
    logic: "논리성",
    relevance: "내용 관련성·구체성",
    delivery: "전달력",
    culture_fit: "조직 적합성",
};

export const QTYPE_LABEL: Record<string, string> = { personality: "인성", company: "기업", resume: "이력서", job: "직무" };

export const EVENT_LABEL: Record<string, string> = {
    visibility: "다른 탭으로 전환", blur: "다른 창으로 이동", fullscreen: "전체 화면 해제", navigate: "다른 주소로 이동",
    unload: "창 닫기·새로고침", permission: "장치 권한 해제", disconnect: "연결 끊김", interrupted: "장애 중단",
    device_error: "장치 오류", upload_error: "녹화 저장 실패 (서버)", resume_limit: "이어가기 횟수 초과",
    beacon_unknown: "알 수 없는 신호", beacon_unparsed: "읽지 못한 신호",
};

export const JUDGED_LABEL: Record<string, string> = { fault: "장애", not_fault: "장애 아님", cheating: "화면 이탈", info: "기록" };

// 확인 필요(평가 지연) 사유 (API 명세서 10장 needs_review[].reason + instruction_suspected)
export const REVIEW_REASON: Record<string, string> = {
    threshold_mismatch: "AI가 쓴 결과 이유가 판정과 맞지 않았습니다",
    invalid_format: "AI 결과의 형식이 맞지 않았습니다",
    quote_not_found: "AI가 든 근거 문장이 답변에 없었습니다",
    analysis_timeout: "채점이 3번 실패했거나 30분을 넘었습니다",
    sandbox_error: "코딩테스트 채점이 끝나지 않았습니다",
    instruction_suspected: "답변에 채점 지시로 보이는 말이 있어 사람이 먼저 확인해야 합니다. 답변을 읽고 문제가 없으면 채점을 진행하세요.",
};
