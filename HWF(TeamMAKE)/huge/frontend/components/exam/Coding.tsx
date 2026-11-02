"use client";

import Editor, { loader, type OnMount } from "@monaco-editor/react";
import { useCallback, useEffect, useRef, useState } from "react";

import { useApp } from "@/components/Providers";
import { Button, Modal } from "@/components/Ui";
import { api, ApiError } from "@/lib/api";
import { mmss, shortDateTime } from "@/lib/format";

// 편집기 파일은 우리 서버(public/monaco)에서 받는다. 외부 CDN 을 쓰지 않는다
loader.config({ paths: { vs: "/monaco/vs" } });

export type Problem = {
    problem_no: number; level: string; title: string; statement: string; signature: string; starter: string;
    examples: { input: string; output: string }[]; limits: { time_sec: number; memory_mb: number }; saved_code?: string; saved_at?: string | null;
};
export type CodingInfo = { problems: Problem[]; remaining_sec: number | null; started: boolean; away_count: number; auto_start_sec: number };
type RunResult = { status: string; error?: string | null; results: { example_no: number; passed: boolean; expected: string; actual: string | null; stdout: string; stderr: string; time_ms: number }[] };

const AUTOSAVE_MS = 30_000;
const RUN_STATUS: Record<string, string> = {
    ok: "실행 완료", timeout: "시간 초과 (10초)", memory_exceeded: "메모리 초과 (256MB)", runtime_error: "실행 오류", syntax_error: "문법 오류",
};

/** S-A10 안내: [시작] 또는 60초 뒤 자동 시작 (G-03) */
export function CodingIntro({ info, onStart, awayCount }: { info: CodingInfo; onStart: () => void; awayCount: number }) {
    const [left, setLeft] = useState(info.auto_start_sec);
    const started = useRef(false);
    const start = useCallback(() => {
        if (started.current) return;
        started.current = true;
        onStart();
    }, [onStart]);

    useEffect(() => {
        if (left <= 0) { start(); return; }
        const timer = window.setTimeout(() => setLeft((v) => v - 1), 1000);
        return () => window.clearTimeout(timer);
    }, [left, start]);

    return (
        <div className="exam-body">
            <div className="card stack" style={{ maxWidth: 680 }}>
                <h2 className="center">✓ AI 면접이 끝났습니다. 수고하셨습니다.</h2>
                <p className="center">이어서 코딩테스트를 진행합니다.</p>
                <ul>
                    <li>2문항 (기초 1 · 응용 1) · Python 3 · 두 문항 합계 60분</li>
                    <li>[실행]으로 공개 예제를 몇 번이든 돌려 볼 수 있습니다</li>
                    <li>코드는 30초마다 자동 저장됩니다</li>
                    <li>외부에서 복사한 내용은 붙여넣을 수 없습니다</li>
                    <li>[최종 제출]을 해야 응시가 끝납니다. 시간이 다 되면 자동 제출됩니다</li>
                    <li>화면 이탈 횟수는 면접과 이어서 셉니다 (현재 {awayCount} / 2)</li>
                </ul>
                <div className="center stack">
                    <div><button type="button" className="btn btn-primary btn-lg" onClick={start}>코딩테스트 시작</button></div>
                    <span className="small muted">{left}초 후 자동으로 시작됩니다 ({mmss(left)})</span>
                </div>
            </div>
        </div>
    );
}

/** S-A11 코딩테스트. 시간은 서버가 재고, 화면은 받은 남은 시간으로 센다 */
export function CodingTest({ sessionId, problems, remainingSec, paused, onFinished }: {
    sessionId: string; problems: Problem[]; remainingSec: number; paused: boolean; onFinished: (auto: boolean) => void;
}) {
    const { toast } = useApp();
    const [active, setActive] = useState(1);
    const [codes, setCodes] = useState<Record<number, string>>(() => Object.fromEntries(problems.map((p) => [p.problem_no, p.saved_code ?? p.starter])));
    const [savedAt, setSavedAt] = useState<Record<number, string | null>>(() => Object.fromEntries(problems.map((p) => [p.problem_no, p.saved_at ?? null])));
    const [dirty, setDirty] = useState<Record<number, boolean>>({});
    const [left, setLeft] = useState(remainingSec);
    const [running, setRunning] = useState(false);
    const [result, setResult] = useState<RunResult | null>(null);
    const [confirm, setConfirm] = useState(false);
    const [submitting, setSubmitting] = useState(false);
    const pasteBlocked = useRef<Record<number, number>>({});
    const internalClipboard = useRef<string>("");
    const codesRef = useRef(codes);
    const finished = useRef(false);

    useEffect(() => { codesRef.current = codes; }, [codes]);
    const [syncedSec, setSyncedSec] = useState(remainingSec);
    if (syncedSec !== remainingSec) {
        // 서버가 남은 시간을 다시 보내면(경고 뒤 재개 등) 그 값으로 맞춘다
        setSyncedSec(remainingSec);
        setLeft(remainingSec);
    }

    useEffect(() => {
        if (paused || finished.current) return;
        const timer = window.setInterval(() => setLeft((v) => Math.max(0, v - 1)), 1000);
        return () => window.clearInterval(timer);
    }, [paused]);

    const save = useCallback(async (problemNo: number) => {
        const blocked = pasteBlocked.current[problemNo] ?? 0;
        for (let attempt = 0; attempt < 3; attempt++) {
            try {
                await api(`/coding/${sessionId}/autosave`, { body: { problem_no: problemNo, code: codesRef.current[problemNo], paste_blocked: blocked } });
                pasteBlocked.current[problemNo] = 0;
                setSavedAt((s) => ({ ...s, [problemNo]: new Date().toISOString() }));
                setDirty((d) => ({ ...d, [problemNo]: false }));
                return;
            } catch (err) {
                if ((err as ApiError).code === "TIME_OVER") { finished.current = true; onFinished(true); return; }
                await new Promise((r) => setTimeout(r, 1000 * 2 ** attempt));
            }
        }
        toast("error", "코드를 자동 저장하지 못했습니다");
    }, [sessionId, toast, onFinished]);

    useEffect(() => {
        if (paused) return;
        const timer = window.setInterval(() => { for (const p of problems) void save(p.problem_no); }, AUTOSAVE_MS);
        return () => window.clearInterval(timer);
    }, [paused, problems, save]);

    // 끝나기 5초 전에 두 문항을 마지막으로 저장한다 (끝난 뒤의 저장은 서버가 받지 않는다)
    useEffect(() => {
        if (left !== 5 || finished.current) return;
        // save 는 네트워크 응답 뒤에만 상태를 바꾼다 (동기 setState 아님)
        // eslint-disable-next-line react-hooks/set-state-in-effect
        for (const p of problems) void save(p.problem_no);
    }, [left, problems, save]);

    // 시간 끝: 서버가 마지막 저장 코드로 자동 제출한다
    useEffect(() => {
        if (left > 0 || finished.current) return;
        finished.current = true;
        toast("info", "시간이 끝나 마지막으로 저장된 코드를 제출했습니다");
        window.setTimeout(() => onFinished(true), 2000);
    }, [left, onFinished, toast]);

    const onMount: OnMount = (editor) => {
        const node = editor.getContainerDomNode();
        // 편집기 안에서 복사한 내용만 붙여넣을 수 있다 (COD-07)
        node.addEventListener("copy", () => { internalClipboard.current = editor.getModel()?.getValueInRange(editor.getSelection()!) ?? ""; }, true);
        node.addEventListener("cut", () => { internalClipboard.current = editor.getModel()?.getValueInRange(editor.getSelection()!) ?? ""; }, true);
        node.addEventListener("paste", (event) => {
            const text = event.clipboardData?.getData("text/plain") ?? "";
            if (text && text !== internalClipboard.current) {
                event.preventDefault();
                event.stopPropagation();
                const no = Number(editor.getModel()?.uri.path.replace(/\D/g, "") || active);
                pasteBlocked.current[no] = (pasteBlocked.current[no] ?? 0) + 1;
                toast("warn", "외부에서 복사한 내용은 붙여넣을 수 없습니다");
            }
        }, true);
        editor.onKeyDown((e) => {
            // 드래그로 외부 글 넣기도 막는다
            if (e.browserEvent.key === "Insert" && e.shiftKey) e.preventDefault();
        });
        node.addEventListener("drop", (event) => { event.preventDefault(); event.stopPropagation(); }, true);
    };

    async function run() {
        setRunning(true);
        setResult(null);
        try {
            setResult(await api<RunResult>(`/coding/${sessionId}/run`, { body: { problem_no: active, code: codes[active] } }));
        } catch (err) {
            const e = err as ApiError;
            if (e.code === "TIME_OVER") { finished.current = true; onFinished(true); return; }
            toast("error", e.message);
        } finally {
            setRunning(false);
        }
    }

    async function submit() {
        setSubmitting(true);
        try {
            await api(`/coding/${sessionId}/submit`, { body: { codes: problems.map((p) => ({ problem_no: p.problem_no, code: codes[p.problem_no] })) } });
            finished.current = true;
            onFinished(false);
        } catch (err) {
            const e = err as ApiError;
            if (e.code === "TIME_OVER") { finished.current = true; onFinished(true); return; }
            toast("error", e.message, submit);
        } finally {
            setSubmitting(false);
        }
    }

    function switchTab(no: number) {
        void save(active);
        setActive(no);
        setResult(null);
    }

    const problem = problems.find((p) => p.problem_no === active)!;
    const urgent = left <= 300;
    const lastSaved = Object.values(savedAt).filter(Boolean).sort().pop();

    return (
        <>
            <div className="row" style={{ height: 48, padding: "0 24px", borderBottom: "1px solid var(--color-line)", gap: 24 }}>
                <strong>코딩테스트</strong>
                <span className={`remaining${urgent ? " urgent" : ""}`} style={{ fontSize: 22 }} aria-live="off">남은 시간 {mmss(left)}{paused && " (멈춤)"}</span>
                <span className="small muted">{lastSaved ? `자동 저장됨 ${shortDateTime(lastSaved).slice(6)}` : "아직 저장 전"}</span>
                <span style={{ flex: 1 }} />
                <button type="button" className="btn btn-primary btn-sm" onClick={() => { void save(active); setConfirm(true); }} disabled={paused}>최종 제출</button>
            </div>
            <div className="coding">
                <div className="problem">
                    <div className="problem-tabs" role="tablist" style={{ padding: 0, height: "auto", marginBottom: 16 }}>
                        {problems.map((p) => (
                            <button key={p.problem_no} type="button" role="tab" aria-selected={active === p.problem_no} onClick={() => switchTab(p.problem_no)}>
                                문제 {p.problem_no} · {p.level} {dirty[p.problem_no] ? "●" : savedAt[p.problem_no] ? "✓저장" : ""}
                            </button>
                        ))}
                    </div>
                    <h2>문제 {problem.problem_no}. {problem.title}</h2>
                    <p className="pre">{problem.statement}</p>
                    <h3>함수 형식</h3>
                    <pre>{problem.signature}</pre>
                    {problem.examples.map((ex, i) => (
                        <div key={i} className="small">
                            <strong>예시 {i + 1}</strong>
                            <pre>입력: {ex.input}{"\n"}출력: {ex.output}</pre>
                        </div>
                    ))}
                    <p className="tiny muted">제한: 실행 {problem.limits.time_sec}초 · 메모리 {problem.limits.memory_mb}MB · 인터넷 사용 불가</p>
                </div>
                <div className="editor">
                    <Editor key={active} path={`problem-${active}.py`} language="python" theme="vs" value={codes[active]}
                        onChange={(value) => { setCodes((c) => ({ ...c, [active]: value ?? "" })); setDirty((d) => ({ ...d, [active]: true })); }}
                        onMount={onMount} options={{ minimap: { enabled: false }, fontSize: 15, tabSize: 4, insertSpaces: true, readOnly: paused, scrollBeyondLastLine: false, automaticLayout: true }} />
                    <div className="result" aria-live="polite">
                        <div className="row between">
                            <strong>실행 결과</strong>
                            <Button size="sm" kind="secondary" busy={running} disabled={paused} onClick={run}>{running ? "실행 중…" : "▶ 실행"}</Button>
                        </div>
                        {!result && !running && <p className="small muted">[실행]을 누르면 공개 예시로 코드를 돌려 봅니다. 실행만으로는 제출되지 않습니다.</p>}
                        {result && (
                            <div className="stack" style={{ gap: 6, marginTop: 8 }}>
                                <span className={`badge ${result.status === "ok" ? "badge-green" : "badge-red"}`}>{RUN_STATUS[result.status] ?? result.status}</span>
                                {result.error && <pre>{result.error}</pre>}
                                {result.results.map((r) => (
                                    <div key={r.example_no}>
                                        예시 {r.example_no}{" "}
                                        {r.passed ? <span style={{ color: "var(--color-success-text)" }}>✓ 통과</span> : <span style={{ color: "var(--color-danger)" }}>✕ 실패</span>}
                                        {" "}<span className="muted">({(r.time_ms / 1000).toFixed(2)}초)</span>
                                        {!r.passed && <span> 기대값 {r.expected} / 실제값 {r.actual ?? "-"}</span>}
                                        {r.stdout && <pre>{r.stdout}</pre>}
                                        {r.stderr && <pre>{r.stderr}</pre>}
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                </div>
            </div>
            {confirm && (
                <Modal title="최종 제출" escClose={false} actions={(
                    <>
                        <button type="button" className="btn btn-secondary" onClick={() => setConfirm(false)}>계속 작성</button>
                        <Button busy={submitting} onClick={submit}>제출하기</Button>
                    </>
                )}>
                    <p>두 문항을 모두 제출합니다. 제출 후에는 고칠 수 없습니다.</p>
                    {problems.map((p) => {
                        const empty = (codes[p.problem_no] ?? "").trim() === p.starter.trim() || !(codes[p.problem_no] ?? "").trim();
                        return (
                            <p key={p.problem_no} className="small">
                                문제 {p.problem_no} · {p.level} {empty ? <span style={{ color: "var(--color-warning-text)" }}>⚠ 작성한 코드가 없습니다</span>
                                    : <>✓ 작성함 {savedAt[p.problem_no] && <span className="muted">마지막 저장 {shortDateTime(savedAt[p.problem_no]).slice(6)}</span>}</>}
                            </p>
                        );
                    })}
                </Modal>
            )}
        </>
    );
}
