"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { useApp } from "@/components/Providers";
import { APPEAL_STATUS_LABEL, AppealResult, ScreeningItems, type ScreeningView } from "@/components/ScreeningItems";
import { Guarded, SiteShell } from "@/components/Shell";
import { Button, ErrorBox, Loading, StatusBadge } from "@/components/Ui";
import { api, ApiError } from "@/lib/api";
import { longDateTime } from "@/lib/format";
import type { AttemptStatus } from "@/lib/status";

type Data = { attempt_status: AttemptStatus; posting_title: string; can_appeal: boolean; appeal_text_max: number; screening: ScreeningView };

/** 서류 평가 결과 (CONFLICTS C-25). 항목별 단계·근거 문장 (점수는 보이지 않음). 서류 불합격이면 항목을 골라 이의 신청 1회 */
function ScreeningDetail() {
    const { applicationId } = useParams<{ applicationId: string }>();
    const { toast } = useApp();
    const [data, setData] = useState<Data | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [claims, setClaims] = useState<Record<string, string>>({});
    const [busy, setBusy] = useState(false);

    const load = useCallback(() => {
        api<Data>(`/applications/${applicationId}/screening`).then(setData)
            .catch((err) => setError(err instanceof ApiError ? err.message : "서류 평가 결과를 불러오지 못했습니다."));
    }, [applicationId]);
    useEffect(load, [load]);

    const picked = Object.entries(claims);
    const ready = picked.length > 0 && picked.every(([, text]) => text.trim());

    async function sendAppeal() {
        setBusy(true);
        try {
            await api(`/applications/${applicationId}/screening/appeal`, {
                body: { claims: picked.map(([item, text]) => ({ item, text: text.trim() })) },
            });
            toast("ok", "이의 신청을 보냈습니다. AI가 고른 항목을 다시 평가한 뒤 알림으로 알려 드립니다");
            setClaims({});
            load();
        } catch (err) {
            toast("error", err instanceof ApiError ? err.message : "이의 신청을 보내지 못했습니다");
        } finally {
            setBusy(false);
        }
    }

    function toggle(item: string, on: boolean) {
        setClaims((c) => {
            const next = { ...c };
            if (on) next[item] = next[item] ?? "";
            else delete next[item];
            return next;
        });
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
    const appealable = v.items.filter((r) => r.appealable);
    return (
        <div className="container stack" style={{ maxWidth: 960 }}>
            {back}
            <div className="card center stack">
                <p className="small muted" style={{ margin: 0 }}>{data.posting_title}</p>
                <h1 style={{ color: pass ? "var(--color-primary)" : "var(--color-neutral)" }}>{pass ? "서류 합격" : "서류 불합격"}</h1>
                <p>{pass ? "마이페이지에서 환경 점검을 마치면 AI 면접을 시작할 수 있습니다." : "이번 서류 평가에서는 함께하지 못하게 되었습니다."}</p>
                <div>지원 상태: <StatusBadge status={data.attempt_status} /></div>
                {v.used_round === "second" && <p className="tiny muted">ⓘ 처음 평가가 합격선 근처여서 더 큰 AI 모델이 다시 평가했고, 그 결과로 판정했습니다.</p>}
                {v.decided_by === "appeal" && <p className="tiny muted">ⓘ 이의 신청을 AI가 다시 평가해 판정이 바뀌었습니다.</p>}
            </div>
            <div className="card stack">
                <h3 style={{ margin: 0 }}>항목별 평가</h3>
                <ScreeningItems items={v.items} />
                <p className="tiny muted">
                    ⓘ AI가 항목마다 단계와 근거 문장을 고르고, 합격 여부는 시스템이 정해진 기준표로 계산합니다. 근거 문장을 제출 서류에서
                    찾지 못하면 0단계로 처리합니다. 글의 길이는 평가하지 않습니다. 경력 연차는 평가하지 않습니다.
                </p>
            </div>
            {v.appeal && (
                <div className="card stack">
                    <h3 style={{ margin: 0 }}>이의 신청 · {APPEAL_STATUS_LABEL[v.appeal.status]}</h3>
                    <p className="small muted" style={{ margin: 0 }}>
                        {v.appeal.at && `${longDateTime(v.appeal.at)}에 보냄`}{v.appeal.done_at && ` · ${longDateTime(v.appeal.done_at)}에 다시 평가함`}
                    </p>
                    <AppealResult appeal={v.appeal} />
                </div>
            )}
            {data.can_appeal && (
                <div className="card stack">
                    <h3 style={{ margin: 0 }}>이의 신청 (1번)</h3>
                    <p className="small muted" style={{ margin: 0 }}>
                        평가가 제출한 서류 내용과 다르다고 생각되는 항목을 고르고, 서류의 어느 부분을 놓쳤는지 적어 주세요. AI가 그 항목을
                        다시 평가합니다. <strong>제출한 서류(이력서·자기소개서·포트폴리오)에 있는 내용만 인정</strong>하며, 이의 글에만 새로 적은
                        내용은 반려됩니다. 기술스택은 공고 기술과 이름을 맞춰 본 결과라 이의 신청 대상이 아닙니다.
                    </p>
                    {appealable.map((r) => (
                        <div key={r.item} className="stack" style={{ gap: 6 }}>
                            <label className="row" style={{ gap: 8 }}>
                                <input type="checkbox" id={`appeal-${r.item}`} checked={r.item in claims} onChange={(e) => toggle(r.item, e.target.checked)} />
                                <span><strong>{r.label}</strong> <span className="small muted">({r.level} / {r.max_level} · {r.level_text})</span></span>
                            </label>
                            {r.item in claims && (
                                <>
                                    <textarea className="input" rows={3} maxLength={data.appeal_text_max} value={claims[r.item]}
                                        placeholder="예: 자기소개서 2번 답변에 실패 뒤 다시 해낸 경험과 배운 점을 적었습니다."
                                        onChange={(e) => setClaims((c) => ({ ...c, [r.item]: e.target.value }))} />
                                    <div className="field-hint">{claims[r.item].length} / {data.appeal_text_max}자</div>
                                </>
                            )}
                        </div>
                    ))}
                    <div className="row" style={{ justifyContent: "flex-end" }}>
                        <Button busy={busy} disabled={!ready} reason={!ready ? "항목을 고르고 내용을 적어 주세요" : null} onClick={sendAppeal}>이의 신청 보내기</Button>
                    </div>
                </div>
            )}
        </div>
    );
}

export default function ScreeningPage() {
    return <SiteShell><Guarded role="applicant"><ScreeningDetail /></Guarded></SiteShell>;
}
