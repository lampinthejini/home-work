"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { ApplyFlow, BottomBar, emptyResume, useApplication, type ResumeData } from "@/components/ApplyFlow";
import { Button, Modal } from "@/components/Ui";
import { api, ApiError } from "@/lib/api";
import { dateOnly } from "@/lib/format";
import { draftKey, type Draft } from "@/lib/resumeDraft";

type Method = "upload" | "manual" | "saved";
type Upload = { upload_id: string; file_name: string; estimated_seconds: number; pages: { text: number; scanned: number } };
type Status = {
    stage: string; estimated_seconds: number; elapsed_seconds: number; result: ResumeData | null; fail_reason: string | null;
    ocr_low_conf_fields: string[];
};


const STAGES = [
    { key: "uploaded", label: "업로드" }, { key: "checking", label: "파일 확인" }, { key: "ocr", label: "글자 인식(OCR)" },
    { key: "structuring", label: "AI 정보 추출" },
];
const MAX_PDF_BYTES = 50 * 1024 * 1024; // 서버 upload_max_mb
const MAX_PHOTO_BYTES = 15 * 1024 * 1024; // OCR 서비스 상한
const FAIL_TEXT: Record<string, string> = {
    NO_TEXT: "파일에서 글자를 찾지 못했습니다.",
    LOW_CONFIDENCE: "글자를 알아보기 어렵습니다. 더 선명한 파일로 올려 주세요.",
    TIMEOUT: "처리 시간이 너무 오래 걸렸습니다.",
    UNSUPPORTED_FILE: "PDF·JPG·PNG 파일만 올릴 수 있습니다.",
    FILE_TOO_LARGE: "파일이 너무 커서 받을 수 없습니다. 용량을 줄여 다시 올려 주세요.",
    PDF_ENCRYPTED: "암호가 걸린 PDF입니다. 암호를 푼 파일로 다시 올려 주세요.",
    PDF_BROKEN: "파일이 손상되어 열 수 없습니다. 원본에서 PDF로 다시 저장해 올려 주세요.",
    PDF_TOO_COMPLEX: "파일이 너무 복잡해 읽지 못했습니다. PDF로 다시 저장하거나 사진으로 올려 주세요.",
    OCR_FAILED: "글자 인식을 끝내지 못했습니다. 잠시 뒤 다시 올려 주세요.",
    INTERNAL: "서버 문제로 처리를 끝내지 못했습니다. 다시 올려 주세요.",
};

function ResumeMethod() {
    const { app } = useApplication();
    const router = useRouter();
    const [method, setMethod] = useState<Method | null>(null);
    const [saved, setSaved] = useState<{ resume: ResumeData; updated_at: string } | null>(null);
    const [upload, setUpload] = useState<Upload | null>(null);
    const [status, setStatus] = useState<Status | null>(null);
    const [failed, setFailed] = useState<string | null>(null);
    const [busy, setBusy] = useState(false);
    const [drag, setDrag] = useState(false);
    const [restored, setRestored] = useState<Draft | null>(null);
    const fileInput = useRef<HTMLInputElement>(null);

    useEffect(() => {
        api<{ resume: ResumeData; updated_at: string }>("/me/resume").then(setSaved).catch(() => setSaved(null));
    }, []);

    // 확인·수정 화면에서 [이전]으로 왔거나 나갔다 [이어서 작성]으로 오면 작성하던 내용을 되살린다 (화면정의서 S-A05 [이전]: 입력값 유지)
    useEffect(() => {
        const raw = sessionStorage.getItem(draftKey(app.application_id));
        if (raw) {
            const draft = JSON.parse(raw) as Draft;
            /* eslint-disable react-hooks/set-state-in-effect */
            setRestored(draft);
            setMethod(draft.method);
            /* eslint-enable react-hooks/set-state-in-effect */
            return;
        }
        // 이 창에 임시값이 없으면 서버에 남은 파일 추출 결과를 쓴다 (다시 올리고 기다리지 않게)
        api<Status & { upload_id: string }>(`/applications/${app.application_id}/resume/extract-status`).then((s) => {
            if (s.stage !== "done" || !s.result) return;
            setRestored({ method: "upload", upload_id: s.upload_id, resume: { ...emptyResume(), ...s.result }, low_conf_fields: s.ocr_low_conf_fields ?? [] });
            setMethod("upload");
        }).catch(() => undefined);
    }, [app.application_id]);

    const proceed = useCallback((draft: Draft) => {
        sessionStorage.setItem(draftKey(app.application_id), JSON.stringify(draft));
        router.push(`/apply/${app.application_id}/resume/confirm`);
    }, [app.application_id, router]);

    // 추출 진행 상태 폴링. 끝나면 자동으로 확인 화면 (T-08)
    useEffect(() => {
        if (!upload) return;
        let stopped = false;
        const tick = async () => {
            try {
                const s = await api<Status>(`/applications/${app.application_id}/resume/extract-status`);
                if (stopped) return;
                setStatus(s);
                if (s.stage === "done" && s.result) {
                    proceed({ method: "upload", upload_id: upload.upload_id, resume: { ...emptyResume(), ...s.result }, low_conf_fields: s.ocr_low_conf_fields ?? [] });
                    return;
                }
                if (s.stage === "failed") {
                    setFailed(FAIL_TEXT[s.fail_reason ?? ""] ?? "글자를 인식하기 어렵거나 시간이 너무 오래 걸렸습니다.");
                    return;
                }
            } catch {
                // 일시 오류는 다음 폴링에서 다시 본다
            }
            if (!stopped) window.setTimeout(tick, 1000);
        };
        void tick();
        return () => { stopped = true; };
    }, [upload, app.application_id, proceed]);

    async function sendFile(file: File) {
        // 큰 파일은 보내기 전에 거절한다. 서버가 도중에 끊으면 브라우저에 원인이 남지 않는다
        if (file.size > (file.type === "application/pdf" ? MAX_PDF_BYTES : MAX_PHOTO_BYTES)) {
            setFailed(FAIL_TEXT.FILE_TOO_LARGE);
            return;
        }
        setBusy(true);
        setFailed(null);
        setStatus(null);
        const form = new FormData();
        form.append("file", file);
        try {
            setUpload(await api<Upload>(`/applications/${app.application_id}/resume/upload`, { body: form }));
        } catch (err) {
            const e = err as ApiError;
            setFailed(FAIL_TEXT[e.code] ?? e.message);
        } finally {
            setBusy(false);
        }
    }

    async function cancelUpload() {
        await api(`/applications/${app.application_id}/resume/upload`, { method: "DELETE" }).catch(() => undefined);
        setUpload(null);
        setStatus(null);
    }

    const resuming = restored !== null && method === restored.method;

    function next() {
        if (resuming) proceed(restored);
        else if (method === "saved" && saved) proceed({ method: "saved", upload_id: null, resume: { ...emptyResume(), ...saved.resume } });
        else if (method === "manual") proceed({ method: "manual", upload_id: null, resume: { ...emptyResume(), name: "" } });
    }

    // OCR 단계는 스캔 쪽·사진이 있거나 실제로 OCR 을 거칠 때만 보인다 (화면정의서 S-A04)
    const stages = STAGES.filter((s) => s.key !== "ocr" || (upload?.pages.scanned ?? 0) > 0 || status?.stage === "ocr");
    const stageIndex = stages.findIndex((s) => s.key === status?.stage);
    const processing = upload && !failed;

    return (
        <div className="stack">
            <h2>이력서를 어떻게 제출할까요?</h2>
            <div className="grid3" role="radiogroup" aria-label="이력서 제출 방식">
                {([
                    { key: "upload", icon: "📄", title: "파일 업로드", text: "AI가 내용을 읽어 채워 줍니다", sub: "PDF·JPG·PNG (스캔본·사진 포함, PDF는 10쪽까지)" },
                    { key: "manual", icon: "✍", title: "직접 작성", text: "항목을 직접 입력합니다", sub: "" },
                    { key: "saved", icon: "📁", title: "등록본 불러오기", text: "마이페이지 이력서 사용", sub: saved ? `최종 수정 ${dateOnly(saved.updated_at)}` : "등록된 이력서가 없습니다" },
                ] as const).map((m) => {
                    const disabled = m.key === "saved" && !saved;
                    return (
                        <button key={m.key} type="button" role="radio" aria-checked={method === m.key} disabled={disabled || !!processing}
                            className="card" onClick={() => setMethod(m.key)}
                            style={{ textAlign: "left", cursor: disabled ? "not-allowed" : "pointer", opacity: disabled ? .55 : 1, font: "inherit", color: "inherit",
                                borderColor: method === m.key ? "var(--color-primary)" : undefined, boxShadow: method === m.key ? "0 0 0 3px var(--color-primary-soft)" : undefined }}>
                            <div style={{ fontSize: 28 }} aria-hidden>{m.icon}</div>
                            <h3 style={{ margin: "8px 0 4px" }}>{m.title}</h3>
                            <div className="small">{m.text}</div>
                            {m.sub && <div className="tiny muted" style={{ marginTop: 4 }}>{m.sub}</div>}
                        </button>
                    );
                })}
            </div>

            {resuming && !processing && (
                <div className="notice notice-info small">
                    작성하던 이력서가 있습니다{restored.method === "upload" ? " (파일에서 읽어 온 내용)" : ""}. [다음 ▶]을 누르면 고치던 내용 그대로 확인·수정 화면으로 갑니다.
                    {restored.method === "upload" && " 다른 파일을 쓰려면 아래에 새로 올려 주세요."}
                </div>
            )}

            {method === "upload" && !upload && (
                <div className="card center" onDragOver={(e) => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)}
                    onDrop={(e) => { e.preventDefault(); setDrag(false); const f = e.dataTransfer.files[0]; if (f) void sendFile(f); }}
                    style={{ borderStyle: "dashed", borderWidth: 2, borderColor: drag ? "var(--color-primary)" : undefined, padding: 40 }}>
                    <p style={{ fontSize: 18 }}>⬆ 이력서 파일을 여기로 끌어다 놓거나</p>
                    <Button kind="secondary" busy={busy} onClick={() => fileInput.current?.click()}>파일 선택</Button>
                    <input ref={fileInput} type="file" accept=".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png" hidden
                        onChange={(e) => { const f = e.target.files?.[0]; if (f) void sendFile(f); e.target.value = ""; }} />
                    <p className="small muted" style={{ marginTop: 12 }}>PDF·JPG·PNG · 스캔본·사진도 글자 인식(OCR)으로 읽습니다 · PDF는 앞 10쪽까지만 읽습니다</p>
                </div>
            )}

            {processing && (
                <div className="card stack" aria-live="polite">
                    <div className="row between">
                        <strong>{upload.file_name}</strong>
                        <button type="button" className="btn btn-secondary btn-sm" onClick={cancelUpload}>취소</button>
                    </div>
                    <ol className="stepper">
                        {stages.map((s, i) => (
                            <li key={s.key} className={i < stageIndex ? "done" : i === stageIndex ? "current" : ""}>
                                <span className="dot">{i < stageIndex ? "✓" : i + 1}</span>{s.label}{i === stageIndex && " 중…"}
                            </li>
                        ))}
                    </ol>
                    <div className="timebar"><div style={{ width: `${Math.min(95, ((status?.elapsed_seconds ?? 0) / Math.max(1, upload.estimated_seconds)) * 100)}%` }} /></div>
                    <span className="small muted">예상 처리 시간 약 {upload.estimated_seconds}초 ({upload.pages.text + upload.pages.scanned}쪽) · 지금까지 {status?.elapsed_seconds ?? 0}초</span>
                </div>
            )}

            {failed && (
                <Modal title="이력서를 불러오는 데 실패했습니다." escClose={false} actions={(
                    <>
                        <button type="button" className="btn btn-secondary" onClick={() => { setFailed(null); setUpload(null); setMethod("upload"); }}>다른 파일 올리기</button>
                        <button type="button" className="btn btn-primary" onClick={() => proceed({ method: "manual", upload_id: null, resume: emptyResume() })}>직접 입력하기</button>
                    </>
                )}>
                    <p>{failed}</p>
                    <p>직접 입력하시겠어요?</p>
                </Modal>
            )}

            <BottomBar>
                <button type="button" className="btn btn-secondary" onClick={() => router.push(`/apply/${app.application_id}/consent`)}>이전</button>
                <span style={{ flex: 1 }} />
                <Button onClick={next} disabled={!(resuming || method === "manual" || (method === "saved" && saved))}
                    reason={method === "upload" ? "파일 처리가 끝나면 자동으로 넘어갑니다" : "제출 방식을 골라 주세요"}>다음 ▶</Button>
            </BottomBar>
        </div>
    );
}

export default function ResumePage() {
    return <ApplyFlow step="resume"><ResumeMethod /></ApplyFlow>;
}
