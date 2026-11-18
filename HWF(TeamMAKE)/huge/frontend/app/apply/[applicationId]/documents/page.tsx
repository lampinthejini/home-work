"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { ApplyFlow, BottomBar, useApplication } from "@/components/ApplyFlow";
import { useApp } from "@/components/Providers";
import { SCREENING_TIME_NOTE } from "@/components/ScreeningItems";
import { Button, Loading, Modal } from "@/components/Ui";
import { api, ApiError } from "@/lib/api";

type DocFile = { id: string; kind: string; name: string; chars: number };
type Documents = { cover_text: string; cover_max: number; max_files: number; file_max_mb: number; files: DocFile[] };
const AUTOSAVE_MS = 1500;

/** 이력서에 칸이 없는 항목을 어디에 쓰는지 보여 주는 안내 (내용에 넣지 않고 빈 칸에만 보임, 2026-11-18 사용자 결정) */
const COVER_PLACEHOLDER = `형식 · 문항 자유입니다. 경험마다 상황 · 본인이 한 일 · 결과(또는 배운 점)를 적어 주세요.

이력서에 칸이 없는 내용도 여기에 적어 주세요. 예)
[교육 · 부트캠프] 과정 이름, 기간, 배운 것과 만든 것
[대회 · 해커톤 · 수상] 이름, 결과, 본인이 맡은 일
[대외활동 · 어학 · 기타] 활동과 그 안에서 한 일`;

/** 자기소개서 PDF (선택, 3개까지). 포트폴리오·프로젝트 기술서 등도 자기소개서로 본다. 글자만 읽어 서류 평가에 쓴다 */
function FilesBox({ applicationId, docs, onChange }: { applicationId: string; docs: Documents; onChange: (d: Documents) => void }) {
    const { toast } = useApp();
    const [busy, setBusy] = useState(false);

    async function upload(file: File) {
        if (file.size > docs.file_max_mb * 1024 * 1024) {
            toast("error", `PDF는 ${docs.file_max_mb}MB까지 올릴 수 있습니다`);
            return;
        }
        const form = new FormData();
        form.append("file", file);
        setBusy(true);
        try {
            onChange(await api<Documents>(`/applications/${applicationId}/documents/files`, { body: form }));
            toast("ok", "PDF를 올렸습니다");
        } catch (err) {
            toast("error", (err as ApiError).message);
        } finally {
            setBusy(false);
        }
    }

    async function remove(id: string) {
        setBusy(true);
        try {
            onChange(await api<Documents>(`/applications/${applicationId}/documents/files/${id}`, { method: "DELETE" }));
        } catch (err) {
            toast("error", (err as ApiError).message);
        } finally {
            setBusy(false);
        }
    }

    return (
        <div className="card stack" style={{ gap: 8 }}>
            <h3 style={{ margin: 0 }}>자기소개서 PDF <span className="small muted">(선택, {docs.max_files}개까지)</span></h3>
            <p className="small muted" style={{ margin: 0 }}>
                포트폴리오 · 프로젝트 기술서 등 다른 서류를 올려도 모두 자기소개서로 평가합니다. 파일 하나에 {docs.file_max_mb}MB까지.
            </p>
            {docs.files.map((f) => (
                <div key={f.id} className="row between">
                    <span className="small">📄 {f.name} <span className="muted">(글자 {f.chars.toLocaleString()}자 읽음)</span></span>
                    <Button kind="text" size="sm" busy={busy} onClick={() => remove(f.id)}>지우기</Button>
                </div>
            ))}
            {docs.files.length < docs.max_files && (
                <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
                    <input id="doc-file" type="file" accept="application/pdf,.pdf" disabled={busy}
                        onChange={(e) => { const f = e.target.files?.[0]; if (f) void upload(f); e.target.value = ""; }} />
                    {busy && <span className="small muted">글자를 읽는 중…</span>}
                </div>
            )}
        </div>
    );
}

/** 추가 서류 (CONFLICTS C-25): 자기소개서(글·PDF), 모두 선택. [제출]하면 서류 평가가 시작된다 */
function DocumentsStep() {
    const { app } = useApplication();
    const router = useRouter();
    const { toast } = useApp();
    const [docs, setDocs] = useState<Documents | null>(null);
    const [cover, setCover] = useState("");
    const [confirming, setConfirming] = useState(false);
    const [busy, setBusy] = useState(false);
    const [saved, setSaved] = useState(true);
    const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

    useEffect(() => {
        api<Documents>(`/applications/${app.application_id}/documents`).then((d) => {
            setDocs(d);
            setCover(d.cover_text);
        }).catch((err) => toast("error", (err as ApiError).message));
    }, [app.application_id, toast]);

    // 쓰는 동안 잠시 멈추면 임시 저장 (창을 닫아도 이어 쓸 수 있게)
    useEffect(() => () => { if (timer.current) clearTimeout(timer.current); }, []);
    function change(text: string) {
        setCover(text);
        setSaved(false);
        if (timer.current) clearTimeout(timer.current);
        timer.current = setTimeout(() => {
            api(`/applications/${app.application_id}/documents`, { method: "PUT", body: { cover_text: text } })
                .then(() => setSaved(true)).catch(() => undefined);
        }, AUTOSAVE_MS);
    }

    if (!docs) return <Loading />;
    const empty = !cover.trim() && docs.files.length === 0;

    async function submit() {
        setBusy(true);
        if (timer.current) clearTimeout(timer.current);
        try {
            await api(`/applications/${app.application_id}/submit`, { body: { cover_text: cover } });
            toast("info", "지원서를 제출했습니다. AI가 서류를 평가하고 있으며, 끝나면 알림으로 알려 드립니다");
            router.replace("/mypage");
        } catch (err) {
            setConfirming(false);
            toast("error", (err as ApiError).message);
        } finally {
            setBusy(false);
        }
    }

    return (
        <div className="stack">
            <div className="row between">
                <h2 style={{ margin: 0 }}>추가 서류를 내 주세요. <span className="small muted">(모두 선택)</span></h2>
                <span className="small muted" aria-live="polite">{saved ? "임시 저장됨" : "저장 중…"}</span>
            </div>
            <div className="notice notice-info small stack" style={{ gap: 4 }}>
                <span>
                    이력서와 자기소개서를 함께 보고 AI가 모든 지원자에게 같은 기준표로 평가합니다. 평가 항목은 직무 적합 · 회사 적합(인재상) ·
                    적응·성장입니다. 분량이 아니라 <strong>구체적인 경험(상황 · 본인이 한 일 · 결과 또는 배운 점)</strong>이 근거가 되며,
                    서류에 적힌 문장만 근거로 씁니다. 프로젝트 · 팀 활동 · 단체 생활 등 어떤 경험이든 괜찮습니다.
                </span>
                <span>
                    ⓘ <strong>글자만 평가합니다.</strong> 그림 · 사진 · 캡처 안의 글자도 읽어(OCR) 평가에 쓰지만, 그림 · 사진 · 디자인 · 서식
                    그 자체는 평가 대상이 아닙니다. 그림 속 글자는 잘못 읽힐 수 있으니, 중요한 내용은 글로도 써 주세요.
                </span>
                <span>
                    ⓘ <strong>이력서에 칸이 없는 내용</strong>(교육 과정 · 부트캠프, 대회 · 해커톤, 수상, 대외활동, 어학 등)은 자기소개서에 적어 주세요.
                    서류 평가와 면접 질문에 그대로 쓰입니다.
                </span>
                <span>ⓘ 자기소개서는 내지 않아도 되지만, 내지 않으면 회사 적합 · 적응·성장을 이력서 내용만으로 평가해 점수가 낮아질 수 있습니다.</span>
                <span>ⓘ {SCREENING_TIME_NOTE}</span>
            </div>
            <div className="card stack" style={{ gap: 8 }}>
                <label htmlFor="cover-text"><strong>자기소개서</strong> <span className="small muted">(형식 · 문항 자유)</span></label>
                <textarea id="cover-text" className="input" rows={12} maxLength={docs.cover_max} value={cover} placeholder={COVER_PLACEHOLDER}
                    onChange={(e) => change(e.target.value)} />
                <div className="field-hint">{cover.trim().length.toLocaleString()} / {docs.cover_max.toLocaleString()}자</div>
            </div>
            <FilesBox applicationId={app.application_id} docs={docs} onChange={setDocs} />
            <BottomBar>
                <button type="button" className="btn btn-secondary" onClick={() => router.push(`/apply/${app.application_id}/resume`)}>이력서로</button>
                <span style={{ flex: 1 }} />
                <Button onClick={() => setConfirming(true)}>지원서 제출 ▶</Button>
            </BottomBar>
            {confirming && (
                <Modal title="지원서를 제출합니다" onClose={() => setConfirming(false)} actions={(
                    <>
                        <button type="button" className="btn btn-secondary" onClick={() => setConfirming(false)}>계속 수정</button>
                        <Button busy={busy} onClick={submit}>제출하기</Button>
                    </>
                )}>
                    <p>제출한 이력서와 추가 서류는 이 공고에서 수정할 수 없습니다.</p>
                    {empty && (
                        <p className="small" style={{ color: "var(--color-danger)" }}>
                            자기소개서가 없습니다. 이력서만으로 평가하며, 회사 적합 · 적응·성장 점수가 낮아질 수 있습니다.
                        </p>
                    )}
                    <p className="small muted">제출하면 AI가 서류를 평가하고, 서류 합격이면 AI 면접을 볼 수 있습니다. 결과는 알림과 메일로 알려 드립니다. {SCREENING_TIME_NOTE}</p>
                </Modal>
            )}
        </div>
    );
}

export default function DocumentsPage() {
    return <ApplyFlow step="documents"><DocumentsStep /></ApplyFlow>;
}
