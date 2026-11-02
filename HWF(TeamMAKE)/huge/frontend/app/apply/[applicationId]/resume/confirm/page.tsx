"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { ApplyFlow, BottomBar, useApplication, type ResumeData } from "@/components/ApplyFlow";
import { useApp } from "@/components/Providers";
import { ResumeForm, resumeRequirement } from "@/components/ResumeForm";
import { Button, Loading, Modal } from "@/components/Ui";
import { api, ApiError } from "@/lib/api";
import { draftKey, type Draft } from "@/lib/resumeDraft";

function Confirm() {
    const { app } = useApplication();
    const router = useRouter();
    const { toast } = useApp();
    const [draft, setDraft] = useState<Draft | null>(null);
    const [edited, setEdited] = useState<Set<string>>(new Set());
    const [lowConf, setLowConf] = useState<Set<string>>(new Set());
    const [confirming, setConfirming] = useState(false);
    const [busy, setBusy] = useState(false);
    const [invalid, setInvalid] = useState<{ name?: boolean; history?: boolean }>({});

    useEffect(() => {
        const raw = sessionStorage.getItem(draftKey(app.application_id));
        // 이전 화면이 넘긴 임시값을 읽는다. 없으면(새 창·주소 직접 입력) 빈 폼 대신 제출 방식 화면에서 되살린다
        if (!raw) {
            router.replace(`/apply/${app.application_id}/resume`);
            return;
        }
        const parsed = JSON.parse(raw) as Draft;
        /* eslint-disable react-hooks/set-state-in-effect */
        setDraft(parsed);
        setLowConf(new Set(parsed.low_conf_fields ?? []));
        /* eslint-enable react-hooks/set-state-in-effect */
    }, [app.application_id, router]);

    if (!draft) return <Loading />;
    const requirement = resumeRequirement(draft.resume);

    // 지원자가 고치거나 [확인]을 누른 칸은 확인 필요 표시를 지운다 (화면정의서 S-A05)
    function clearLowConf(field: string) {
        const rest = new Set(lowConf);
        rest.delete(field);
        setLowConf(rest);
        const next = { ...draft!, low_conf_fields: [...rest] };
        setDraft(next);
        sessionStorage.setItem(draftKey(app.application_id), JSON.stringify(next));
    }

    function change(resume: ResumeData) {
        const next = { ...draft!, resume, low_conf_fields: [...lowConf] };
        setDraft(next);
        sessionStorage.setItem(draftKey(app.application_id), JSON.stringify(next));
    }

    async function submit() {
        setBusy(true);
        try {
            const { name, ...rest } = draft!.resume;
            await api(`/applications/${app.application_id}/resume`, {
                body: { method: draft!.method, upload_id: draft!.upload_id, resume: { name, ...rest, cover_letter: rest.cover_letter || null }, edited_fields: [...edited] },
            });
            sessionStorage.removeItem(draftKey(app.application_id));
            toast("info", "이력서를 제출했습니다. 환경 점검을 마치면 면접을 시작할 수 있습니다");
            router.replace(`/apply/${app.application_id}/precheck`);
        } catch (err) {
            const e = err as ApiError;
            setConfirming(false);
            if (e.code === "RESUME_REQUIRED_MISSING") {
                setInvalid({ name: !requirement.name, history: !requirement.history });
                document.getElementById(requirement.name ? "field-education" : "field-name")?.scrollIntoView({ behavior: "smooth", block: "center" });
            } else {
                toast("error", e.code === "NETWORK" ? "저장하지 못했습니다" : e.message, submit);
            }
        } finally {
            setBusy(false);
        }
    }

    return (
        <div className="stack">
            <div className="row between">
                <h2 style={{ margin: 0 }}>내용을 확인하고 틀린 부분을 고쳐 주세요.</h2>
                <span className="small" aria-live="polite">
                    필수: 성명 {requirement.name ? "✓" : "✕"} · 학력 또는 경력 1건 이상 {requirement.history ? "✓" : "✕"}
                </span>
            </div>
            {draft.method === "upload" && <div className="notice notice-info small">AI가 파일에서 읽은 내용입니다. 원본과 다른 부분이 없는지 꼭 확인해 주세요.</div>}
            {lowConf.size > 0 && (
                <div className="notice notice-warn small">🔍 글자 인식이 불확실한 칸 {lowConf.size}개가 주황색으로 표시되어 있습니다. 원본과 비교해 고치거나 [확인]을 눌러 주세요.</div>
            )}
            <div style={{ display: "grid", gridTemplateColumns: draft.method === "upload" ? "minmax(0, 1fr) minmax(0, 1fr)" : "1fr", gap: 24, alignItems: "start" }}>
                <div className="card">
                    <ResumeForm value={draft.resume} onChange={change} invalid={invalid} lowConf={lowConf} onConfirm={clearLowConf}
                        onEdit={(f) => { setEdited((s) => new Set(s).add(f)); if (lowConf.has(f)) clearLowConf(f); }} />
                </div>
                {draft.method === "upload" && (
                    <div className="card tight" style={{ position: "sticky", top: 88, height: "calc(100vh - 220px)" }}>
                        <iframe title="원본 이력서" src={`/api/applications/${app.application_id}/resume/file`} style={{ width: "100%", height: "100%", border: 0 }} />
                    </div>
                )}
            </div>
            <BottomBar>
                <button type="button" className="btn btn-secondary" onClick={() => router.push(`/apply/${app.application_id}/resume`)}>이전</button>
                <span style={{ flex: 1 }} />
                <Button onClick={() => setConfirming(true)} disabled={!requirement.ok} reason="성명과 학력 또는 경력 1건 이상이 필요합니다">이력서 제출 ▶</Button>
            </BottomBar>
            {confirming && (
                <Modal title="지원서를 제출합니다" onClose={() => setConfirming(false)} actions={(
                    <>
                        <button type="button" className="btn btn-secondary" onClick={() => setConfirming(false)}>계속 수정</button>
                        <Button busy={busy} onClick={submit}>제출하기</Button>
                    </>
                )}>
                    <p>제출한 이력서는 이 공고에서 수정할 수 없습니다.</p>
                </Modal>
            )}
        </div>
    );
}

export default function ConfirmPage() {
    return <ApplyFlow step="resume"><Confirm /></ApplyFlow>;
}
