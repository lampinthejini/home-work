"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { Mascot } from "@/components/Brand";
import { Guarded, SiteShell } from "@/components/Shell";
import { ErrorBox, Loading, StatusBadge } from "@/components/Ui";
import { api, ApiError } from "@/lib/api";
import { dateOnly, longDateTime } from "@/lib/format";
import type { AttemptStatus } from "@/lib/status";

type Result = {
    result: "pass" | "fail"; attempt_status: AttemptStatus; status_reason: string | null; strengths: string[]; improvements: string[];
    contact_email: string; result_until: string;
};
type Card = { application_id: string; posting: { title: string }; release_at: string };

const STATUS_REASON: Record<string, string> = {
    cheating_cancelled: "화면 이탈 규칙에 따라 응시가 취소되어 평가하지 않았습니다.",
    closed: "접수 마감으로 면접이 끝나 답변한 문항까지 평가했습니다.",
    ended: "응시가 중간에 종료되어 답변한 문항까지 평가했습니다.",
};

/** S-A14 결과 상세. 점수·근거는 보여 주지 않는다 (RPT-03, AC-16) */
function ResultDetail() {
    const { applicationId } = useParams<{ applicationId: string }>();
    const [result, setResult] = useState<Result | null | "none">(null);
    const [card, setCard] = useState<Card | null>(null);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        // 404 만 '아직 공개 전'. 그 밖의 오류는 오류로 보여 준다
        api<Result>(`/me/results/${applicationId}`).then(setResult).catch((err) => {
            if (err instanceof ApiError && err.status === 404) setResult("none");
            else setError(err instanceof ApiError ? err.message : "결과를 불러오지 못했습니다.");
        });
        api<{ items: Card[] }>("/me/applications").then((r) => setCard(r.items.find((c) => c.application_id === applicationId) ?? null)).catch(() => undefined);
    }, [applicationId]);

    if (error) return <ErrorBox message={error} onRetry={() => window.location.reload()} />;
    if (result === null) return <Loading />;
    if (result === "none") {
        return (
            <div className="narrow center stack">
                <Mascot name="03-evaluation" size={160} />
                <h2>아직 결과가 공개되지 않았습니다.</h2>
                {card && <p className="muted">{longDateTime(card.release_at)} 공개</p>}
                <Link className="btn btn-primary" href="/mypage?tab=results">마이페이지로</Link>
            </div>
        );
    }
    const pass = result.result === "pass";
    return (
        <div className="container stack" style={{ maxWidth: 860 }}>
            <Link href="/mypage?tab=results" className="small">← 마이페이지</Link>
            <div className="row between"><strong>{card?.posting.title}</strong><span className="small muted">{dateOnly(result.result_until)}까지 열람 가능</span></div>
            <div className="card center stack">
                <h1 style={{ color: pass ? "var(--color-primary)" : "var(--color-neutral)" }}>{pass ? "1차 합격" : "1차 불합격"}</h1>
                <p>{pass ? "축하드립니다. 다음 전형은 기업에서 개별로 연락드립니다." : "이번 1차 전형에서는 함께하지 못하게 되었습니다."}</p>
                <div>응시 상태: <StatusBadge status={result.attempt_status} /></div>
                {result.status_reason && <p className="small muted">{STATUS_REASON[result.status_reason] ?? ""}</p>}
            </div>
            <div className="grid2">
                <div className="card"><h3>강점</h3><ol>{result.strengths.slice(0, 3).map((s, i) => <li key={i}>{s}</li>)}</ol></div>
                <div className="card"><h3>개선점</h3><ol>{result.improvements.slice(0, 3).map((s, i) => <li key={i}>{s}</li>)}</ol></div>
            </div>
            <p className="small muted">ⓘ AI가 생성한 결과입니다.</p>
            <hr style={{ border: 0, borderTop: "1px solid var(--color-line)", width: "100%" }} />
            <p className="tiny muted">결과에 문제가 있으면 채용 담당자 이메일(<a href={`mailto:${result.contact_email}`}>{result.contact_email}</a>)로 문의해 주세요.</p>
        </div>
    );
}

export default function ResultPage() {
    return <SiteShell><Guarded role="applicant"><ResultDetail /></Guarded></SiteShell>;
}
