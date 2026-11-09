"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { ApplyFlow, BottomBar, useApplication } from "@/components/ApplyFlow";
import { useApp } from "@/components/Providers";
import { Button } from "@/components/Ui";
import { api, ApiError } from "@/lib/api";

// PRD APP-03 (v1.3) 다섯 항목
const ITEMS = [
    { key: "data_collection", title: "① 응시 데이터 수집·이용", summary: "이력서, 답변 음성·텍스트, 카메라 녹화(영상과 마이크 소리), 코드, 장애·이탈 기록",
        detail: "AI 면접 진행과 평가를 위해 위 데이터를 수집합니다. 카메라 영상과 마이크 소리 녹화는 부정행위 확인용이며 평가 점수에는 쓰지 않습니다." },
    { key: "ai_decision", title: "② AI 자동 채점과 1차 합격·불합격 결정", summary: "",
        detail: "AI가 평가 항목별로 채점합니다. 시스템이 공고의 가중치로 합산한 종합 총점이 합격 기준 이상이면 1차 합격으로 정하고, AI는 그 이유를 씁니다. 이렇게 정해진 결과는 관리자도 바꿀 수 없습니다. 시스템 문제 등으로 자동 채점을 끝내지 못하면 다시 시도하며, 3일 안에 담당자가 합격·불합격을 정할 수 있습니다. 정하지 않고 다시 시도도 실패하면 평가 미완료로 1차 불합격 처리되며, 장애가 길어져도 7일 안에는 결과가 정해집니다." },
    { key: "share_with_admin", title: "③ 공고를 운영하는 관리자에게 결과 제공", summary: "",
        detail: "평가 결과, 답변 기록, 이력서, 장애·이탈 기록을 공고 관리자가 볼 수 있습니다." },
    { key: "retention", title: "④ 보관 기간: 응시 데이터 결과 공개일부터 7일 · 녹화 3일 후 자동 삭제", summary: "",
        detail: "기간이 지나면 자동으로 삭제됩니다. 동의를 철회하면 진행 중 응시가 취소되고 데이터가 즉시 삭제됩니다." },
    { key: "exam_rules", title: "⑤ 응시 규칙", summary: "1회만 응시 · 중단 버튼 없음 · 화면 이탈 1회 경고, 2회 응시 취소(1차 불합격) · 연결이 끊기면 이어가기 3회까지",
        detail: "다른 탭·창으로 이동하거나 전체 화면을 해제하면 화면 이탈입니다. 새로고침·창 닫기는 응시 종료로 처리됩니다. 인터넷·장치 문제로 연결이 끊기면 3번까지 이어서 볼 수 있고(서버 오류는 세지 않음), 그다음 끊기면 응시가 끝나 답변한 문항까지 평가합니다." },
] as const;

type Key = (typeof ITEMS)[number]["key"];

function Consent() {
    const { app } = useApplication();
    const router = useRouter();
    const { toast } = useApp();
    const [checked, setChecked] = useState<Record<Key, boolean>>({ data_collection: false, ai_decision: false, share_with_admin: false, retention: false, exam_rules: false });
    const [open, setOpen] = useState<Key | null>(null);
    const [busy, setBusy] = useState(false);
    const all = Object.values(checked).every(Boolean);

    async function submit() {
        setBusy(true);
        try {
            await api(`/applications/${app.application_id}/consent`, { body: { consent_version: app.consent_version, items: checked } });
            router.push(`/apply/${app.application_id}/resume`);
        } catch (err) {
            toast("error", (err as ApiError).message, submit);
        } finally {
            setBusy(false);
        }
    }

    return (
        <div className="card stack" style={{ maxWidth: 820 }}>
            <h2>지원을 위해 아래 내용에 모두 동의해 주세요.</h2>
            <label className="check" style={{ fontWeight: 700 }}>
                <input type="checkbox" checked={all} onChange={(e) => setChecked(Object.fromEntries(ITEMS.map((i) => [i.key, e.target.checked])) as Record<Key, boolean>)} />
                전체 동의
            </label>
            <hr style={{ border: 0, borderTop: "1px solid var(--color-line)", width: "100%" }} />
            {ITEMS.map((item) => (
                <div key={item.key}>
                    <div className="row between" style={{ flexWrap: "nowrap" }}>
                        <label className="check">
                            <input type="checkbox" checked={checked[item.key]} onChange={(e) => setChecked({ ...checked, [item.key]: e.target.checked })} />
                            <span>(필수) {item.title}{item.summary && <span className="small muted" style={{ display: "block" }}>{item.summary}</span>}</span>
                        </label>
                        <button type="button" className="btn btn-text btn-sm" aria-expanded={open === item.key} onClick={() => setOpen(open === item.key ? null : item.key)}>
                            자세히 {open === item.key ? "▴" : "▾"}
                        </button>
                    </div>
                    {open === item.key && <p className="small muted" style={{ margin: "6px 0 0 30px" }}>{item.detail}</p>}
                </div>
            ))}
            <p className="tiny muted">동의 문구 버전 {app.consent_version} · 동의를 철회하면 진행 중 응시가 취소되고 데이터가 즉시 삭제됩니다.</p>
            <BottomBar>
                <button type="button" className="btn btn-secondary" onClick={() => router.push(`/jobs/${app.posting.posting_id}`)}>취소</button>
                <span style={{ flex: 1 }} />
                <Button onClick={submit} busy={busy} disabled={!all} reason="5개 항목에 모두 동의해야 진행할 수 있습니다">동의하고 다음 ▶</Button>
            </BottomBar>
        </div>
    );
}

export default function ConsentPage() {
    return <ApplyFlow step="consent"><Consent /></ApplyFlow>;
}
