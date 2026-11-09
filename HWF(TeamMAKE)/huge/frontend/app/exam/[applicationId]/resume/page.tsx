"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Precheck } from "@/components/Precheck";
import { useApp } from "@/components/Providers";
import { DesktopOnly, Footer, Gnb, useGuard } from "@/components/Shell";
import { Button, Loading, Spinner } from "@/components/Ui";
import { api, ApiError } from "@/lib/api";
import { examSessionKey, type ExamSession } from "@/lib/exam";
import { longDateTime } from "@/lib/format";

type State = {
    attempt_status: string; phase: "interview" | "coding"; current_seq: number; end_detail: string | null;
    interruption: { judged: string; reason: string; at: string } | null; resume_until: string; server_time: string; resumes_left: number;
};

const REASON: Record<string, string> = {
    heartbeat_timeout: "네트워크 연결 끊김", ws_abnormal_close: "네트워크 연결 끊김", offline: "인터넷 연결 끊김", device_error: "장치 오류",
    upload_failed: "업로드 실패", server_error: "일시적인 서버 오류", unknown: "원인 미상 (지원자에게 유리하게 장애로 처리)",
    unload: "창 닫기·새로고침으로 연결 종료", permission_revoked: "마이크·카메라 권한 해제",
    resume_limit: "연결 끊김으로 이어가기 횟수를 모두 사용", exit_twice: "화면 이탈 2회",
    coding_submitted: "코딩테스트 제출", coding_timeout: "코딩테스트 시간 종료",
};
// 모르는 코드는 영문 그대로 보이지 않게 한다 (E13)
const reasonText = (code: string | null | undefined) => (code && REASON[code]) || "기타";

const ENDED_TITLE: Record<string, string> = { completed: "응시를 마쳤습니다.", cancelled: "응시가 취소되었습니다." };

/** S-A15 면접 이어가기: 서버 판정 조회 → 재점검 → 이어서 시작 */
function Resume() {
    const { applicationId } = useParams<{ applicationId: string }>();
    const router = useRouter();
    const { toast } = useApp();
    const [state, setState] = useState<State | null>(null);
    const [passed, setPassed] = useState(false);
    const [busy, setBusy] = useState(false);
    const [closed, setClosed] = useState(false);

    useEffect(() => {
        api<State>(`/applications/${applicationId}/interview/state`).then(setState).catch(() => router.replace("/mypage"));
    }, [applicationId, router]);

    if (!state) return <div className="narrow center"><Spinner /> 연결 기록을 확인하고 있습니다…</div>;

    const pastClose = closed || new Date(state.resume_until).getTime() <= new Date(state.server_time).getTime();
    if (state.attempt_status === "ended_closed" || (state.attempt_status === "interrupted" && pastClose)) {
        return (
            <div className="narrow card center stack">
                <h2>마감이 되어 면접을 진행할 수 없습니다.</h2>
                <p>저장된 답변까지 평가하며, 제시되지 않은 문항은 0점입니다.</p>
                <Link className="btn btn-primary" href="/mypage">마이페이지로</Link>
            </div>
        );
    }
    if (state.attempt_status !== "interrupted") {
        return (
            <div className="narrow card center stack">
                <h2>{ENDED_TITLE[state.attempt_status] ?? "응시가 종료되었습니다."}</h2>
                {state.end_detail && <p>사유: {reasonText(state.end_detail)}</p>}
                <p className="muted">{state.attempt_status === "completed" ? "이어갈 면접이 없습니다. 결과는 마이페이지에서 확인할 수 있습니다."
                    : state.attempt_status === "cancelled" ? "응시 규칙에 따라 1차 불합격으로 처리되며, 다시 응시할 수 없습니다."
                        : "답변한 문항까지 평가하며, 다시 응시할 수 없습니다."}</p>
                <Link className="btn btn-primary" href="/mypage">마이페이지로</Link>
            </div>
        );
    }

    async function start() {
        setBusy(true);
        try {
            await document.documentElement.requestFullscreen({ navigationUI: "hide" });
        } catch {
            toast("warn", "전체 화면으로 전환해야 시작할 수 있습니다");
            setBusy(false);
            return;
        }
        try {
            const res = await api<ExamSession>(`/applications/${applicationId}/interview/resume`, { method: "POST" });
            sessionStorage.setItem(examSessionKey(applicationId), JSON.stringify(res));
            router.replace(`/exam/${applicationId}`);
        } catch (err) {
            await document.exitFullscreen().catch(() => undefined);
            const e = err as ApiError;
            if (e.code === "POSTING_CLOSED") setClosed(true);
            else toast("error", e.message);
            setBusy(false);
        }
    }

    return (
        <div className="stack">
            <div className="notice notice-ok">
                <strong>✓ 시스템 장애로 확인되었습니다.</strong> 사유: {reasonText(state.interruption?.reason ?? "unknown")}
                <br />장비를 다시 점검한 뒤 이어서 시작합니다. 접수 마감 {longDateTime(state.resume_until)}까지 이어갈 수 있습니다.
                {/* resumes_left 는 이번 중단을 이미 뺀 값이다. 0 이어도 이번에는 이어갈 수 있다 (E13) */}
                <br />{state.resumes_left > 0
                    ? `이번에 이어간 뒤에도 연결 끊김·장치 오류가 ${state.resumes_left}번 더 생기면 다시 이어갈 수 있습니다.`
                    : "이번이 마지막 이어가기입니다. 다시 연결이 끊기거나 장치 오류가 생기면 응시가 종료됩니다."}
            </div>
            <Precheck applicationId={applicationId} onPassed={setPassed} />
            <div className="card row between">
                <span>{state.phase === "coding" ? "코딩테스트를 마지막으로 저장된 코드와 남은 시간부터 이어갑니다." : `${state.current_seq}번 질문부터 처음부터 다시 시작합니다. 감점은 없습니다.`}</span>
                <div className="row">
                    <button type="button" className="btn btn-secondary" onClick={() => router.push("/jobs")}>나중에 응시하기</button>
                    <Button size="lg" busy={busy} disabled={!passed} reason="5개 항목을 모두 통과해야 시작할 수 있습니다" onClick={start}>이어서 시작 (전체 화면)</Button>
                </div>
            </div>
        </div>
    );
}

export default function ResumePage() {
    const me = useGuard("applicant");
    return (
        <>
            <Gnb />
            <main className="page"><div className="container"><DesktopOnly>{me ? <Resume /> : <Loading />}</DesktopOnly></div></main>
            <Footer />
        </>
    );
}
