"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { useApp } from "@/components/Providers";
import { scoreLine, ScreeningItems, type ScreeningView } from "@/components/ScreeningItems";
import { Guarded, SiteShell } from "@/components/Shell";
import { Button, ErrorBox, Field, Loading, StatusBadge } from "@/components/Ui";
import { api, ApiError } from "@/lib/api";
import { longDateTime } from "@/lib/format";
import type { AttemptStatus } from "@/lib/status";

type Data = { attempt_status: AttemptStatus; screening: ScreeningView };
const APPEAL_MAX = 1000;

/** 서류 평가 결과 (CONFLICTS C-24). 최종 판정에 쓴 항목별 단계·근거와, 서류 불합격이면 이의 신청 1회 */
function ScreeningDetail() {
    const { applicationId } = useParams<{ applicationId: string }>();
    const { toast } = useApp();
    const [data, setData] = useState<Data | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [appeal, setAppeal] = useState("");
    const [busy, setBusy] = useState(false);

    const load = useCallback(() => {
        api<Data>(`/applications/${applicationId}/screening`).then(setData)
            .catch((err) => setError(err instanceof ApiError ? err.message : "서류 평가 결과를 불러오지 못했습니다."));
    }, [applicationId]);
    useEffect(load, [load]);

    async function sendAppeal() {
        setBusy(true);
        try {
            await api(`/applications/${applicationId}/screening/appeal`, { body: { text: appeal.trim() } });
            toast("ok", "이의 신청을 보냈습니다. 담당자가 확인한 뒤 알려 드립니다");
            load();
        } catch (err) {
            toast("error", err instanceof ApiError ? err.message : "이의 신청을 보내지 못했습니다");
        } finally {
            setBusy(false);
        }
    }

    if (error) return <ErrorBox message={error} onRetry={() => window.location.reload()} />;
    if (!data) return <Loading />;
    const v = data.screening;
    const back = <Link href="/mypage" className="small">← 마이페이지</Link>;
    if (!v.decision) {
        return (
            <div className="narrow center stack">
                {back}
                <h2>서류를 평가하고 있습니다</h2>
                <p className="muted">AI가 항목마다 서류를 읽고 있습니다. 끝나면 알림과 메일로 알려 드립니다.</p>
            </div>
        );
    }
    const pass = v.decision === "pass";
    return (
        <div className="container stack" style={{ maxWidth: 960 }}>
            {back}
            <div className="card center stack">
                <h1 style={{ color: pass ? "var(--color-primary)" : "var(--color-neutral)" }}>{pass ? "서류 합격" : "서류 불합격"}</h1>
                <p>{pass ? "마이페이지에서 환경 점검을 마치면 AI 면접을 시작할 수 있습니다." : "이번 서류 평가에서는 함께하지 못하게 되었습니다."}</p>
                <div>지원 상태: <StatusBadge status={data.attempt_status} /></div>
                <p className="small muted">{scoreLine(v)}</p>
                {v.used_round === "second" && <p className="tiny muted">ⓘ 1차 점수가 합격선 근처여서 더 큰 AI 모델이 다시 평가했고, 그 결과로 판정했습니다.</p>}
                {v.decided_by === "admin" && <p className="tiny muted">ⓘ 이의 신청을 담당자가 확인해 판정을 정했습니다.</p>}
            </div>
            <div className="card stack">
                <h3 style={{ margin: 0 }}>항목별 평가</h3>
                <ScreeningItems items={v.items} />
                <p className="tiny muted">ⓘ AI가 항목마다 단계와 근거 문장을 고르고, 점수와 합격 여부는 시스템이 계산합니다. 근거 문장을 제출 서류에서 찾지 못하면 0단계로 처리합니다.</p>
            </div>
            {data.attempt_status === "screen_rejected" && (
                <div className="card stack">
                    <h3 style={{ margin: 0 }}>이의 신청</h3>
                    {v.appeal_at ? (
                        <p className="small">{longDateTime(v.appeal_at)}에 이의 신청을 보냈습니다. 담당자가 확인한 뒤 알림으로 알려 드립니다.</p>
                    ) : (
                        <>
                            <p className="small muted">평가가 서류 내용과 다르다고 생각되면 한 번 이의 신청을 할 수 있습니다. 담당자가 직접 확인합니다.</p>
                            <Field label="이의 신청 내용" hint={`${appeal.length} / ${APPEAL_MAX}자`}>
                                <textarea id="screening-appeal" className="input" rows={4} maxLength={APPEAL_MAX} value={appeal}
                                    placeholder="예: 경력 항목이 0단계인데, 이력서 경력 칸에 인턴 6개월이 적혀 있습니다."
                                    onChange={(e) => setAppeal(e.target.value)} />
                            </Field>
                            <div className="row" style={{ justifyContent: "flex-end" }}>
                                <Button busy={busy} disabled={!appeal.trim()} reason={!appeal.trim() ? "내용을 적어 주세요" : null} onClick={sendAppeal}>이의 신청 보내기</Button>
                            </div>
                        </>
                    )}
                </div>
            )}
        </div>
    );
}

export default function ScreeningPage() {
    return <SiteShell><Guarded role="applicant"><ScreeningDetail /></Guarded></SiteShell>;
}
