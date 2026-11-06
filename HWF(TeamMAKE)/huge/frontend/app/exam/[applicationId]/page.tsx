"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { HugeLogo, Mascot } from "@/components/Brand";
import { CodingIntro, CodingTest, type CodingInfo } from "@/components/exam/Coding";
import { ExamOverlay, type Overlay } from "@/components/exam/Overlays";
import { useApp } from "@/components/Providers";
import { DesktopOnly, useGuard } from "@/components/Shell";
import { Loading, Spinner } from "@/components/Ui";
import { api } from "@/lib/api";
import { loadExamSession, sendUnloadBeacon, type ExamSession } from "@/lib/exam";
import { longDateTime, mmss } from "@/lib/format";
import { loadDeviceChoice, openStream, stopStream } from "@/lib/media";
import { PcmRecorder } from "@/lib/pcm";
import { CameraRecorder } from "@/lib/recording";

type Phase = "connecting" | "preparing" | "interview" | "coding-intro" | "coding" | "done";
type Step = "reading" | "countdown" | "answering" | "processing";
type Question = { seq: number; kind: "base" | "follow_up"; text: string; audio_url: string | null; answer_sec: number; progress: string };
type StateResponse = {
    attempt_status: string; phase: "interview" | "coding"; end_detail: string | null; resume_until: string; release_at: string;
    questions: { composed: number; total: number };
};
type Posting = { title: string; close_at: string; release_at: string; has_coding_test: boolean };

const HEARTBEAT_MS = 5000;
const BLUR_THRESHOLD_MS = 2000;
const AWAY_GRACE_MS = 1500; // 탭 전환 한 번에 visibility·fullscreen·blur 가 함께 오므로 첫 신호만 보낸다
const COUNTDOWN = 3;
const FLUSH_MS = 250; // 녹음기의 마지막 조각(최대 1초)이 서버에 닿은 뒤 답변 완료를 보낸다
const NO_AUDIO_READ_MS = 5000; // TTS 가 없으면 자막만 5초 보여 준 뒤 카운트다운 (G-04)

function Exam() {
    const { applicationId } = useParams<{ applicationId: string }>();
    const router = useRouter();
    const { toast } = useApp();
    const [session] = useState<ExamSession | null>(() => (typeof window === "undefined" ? null : loadExamSession(applicationId)));
    const [posting, setPosting] = useState<Posting | null>(null);
    const [phase, setPhase] = useState<Phase>("connecting");
    const [prep, setPrep] = useState({ composed: 0, total: 10, elapsed: 0 });
    const [question, setQuestion] = useState<Question | null>(null);
    const [step, setStep] = useState<Step>("processing");
    const [count, setCount] = useState(COUNTDOWN);
    const [remaining, setRemaining] = useState(0);
    const [answerTotal, setAnswerTotal] = useState(90);
    const [caption, setCaption] = useState("");
    const [noAudio, setNoAudio] = useState(false);
    const [level, setLevel] = useState(0);
    const [overlay, setOverlay] = useState<Overlay | null>(null);
    const [conn, setConn] = useState<"ok" | "slow" | "down">("ok");
    const [coding, setCoding] = useState<CodingInfo | null>(null);
    const [codingRemaining, setCodingRemaining] = useState(0);
    const [awayCount, setAwayCount] = useState(0);
    const [codingAuto, setCodingAuto] = useState(false);
    const [recordingOn, setRecordingOn] = useState(false);

    const ws = useRef<WebSocket | null>(null);
    const stream = useRef<MediaStream | null>(null);
    const recorder = useRef<PcmRecorder | null>(null);
    const camera = useRef<CameraRecorder | null>(null);
    const phaseRef = useRef<"interview" | "coding">("interview");
    const audio = useRef<HTMLAudioElement | null>(null);
    const video = useRef<HTMLVideoElement>(null);
    const timers = useRef<number[]>([]);
    const captionChunk = useRef(-1);
    const current = useRef<Question | null>(null);
    const stepRef = useRef<Step>("processing");
    const watching = useRef(true); // 이탈 감시 (응시가 끝나면 끈다)
    const ended = useRef(false);
    const warned = useRef(false);
    const lastAway = useRef(0);
    const blurTimer = useRef<number | null>(null);
    const blurAt = useRef(0);
    const lastMessageAt = useRef(0);
    const remainingRef = useRef(0);
    const failedDevice = useRef<"mic" | "camera" | null>(null);

    const later = useCallback((fn: () => void, ms: number) => { timers.current.push(window.setTimeout(fn, ms)); }, []);
    const clearTimers = useCallback(() => { timers.current.forEach((t) => window.clearTimeout(t)); timers.current = []; }, []);
    const setStepBoth = useCallback((s: Step) => { stepRef.current = s; setStep(s); }, []);
    const setRemainingBoth = useCallback((sec: number) => { remainingRef.current = sec; setRemaining(sec); }, []);

    const send = useCallback((message: Record<string, unknown>) => {
        if (ws.current?.readyState === WebSocket.OPEN) ws.current.send(JSON.stringify(message));
    }, []);

    const stopEverything = useCallback(() => {
        watching.current = false;
        ended.current = true;
        clearTimers();
        audio.current?.pause();
        recorder.current?.close();
        camera.current?.stop(); // 트랙을 끄기 전에 멈춰야 마지막 조각이 나온다
        setRecordingOn(false);
        stopStream(stream.current);
    }, [clearTimers]);

    /** 상태가 바뀐 뒤에 전체 화면을 푼다 (해제가 이탈로 잡히지 않게, §7.5) */
    const finish = useCallback((next: Overlay | null, toPhase?: Phase) => {
        stopEverything();
        if (next) setOverlay(next);
        if (toPhase) setPhase(toPhase);
        if (document.fullscreenElement) void document.exitFullscreen().catch(() => undefined);
    }, [stopEverything]);

    // ---------- 답변 단계 ----------
    const endAnswer = useCallback(() => {
        const q = current.current;
        recorder.current?.stop();
        setStepBoth("processing");
        window.setTimeout(() => send({ type: "answer_done", seq: q?.seq, answer_no: q?.kind === "follow_up" ? 2 : 1 }), FLUSH_MS);
    }, [send, setStepBoth]);

    const beginAnswer = useCallback((seconds: number) => {
        setStepBoth("answering");
        setRemainingBoth(seconds);
        stream.current?.getAudioTracks().forEach((t) => { t.enabled = true; });
        recorder.current?.start();
        const tick = () => {
            if (warned.current || stepRef.current !== "answering") return;
            const left = remainingRef.current - 1;
            setRemainingBoth(Math.max(0, left));
            if (left <= 0) endAnswer();
            else later(tick, 1000);
        };
        later(tick, 1000);
    }, [endAnswer, later, setRemainingBoth, setStepBoth]);

    const countdownThen = useCallback((seconds: number) => {
        setStepBoth("countdown");
        setCount(COUNTDOWN);
        for (let i = 1; i < COUNTDOWN; i++) later(() => { if (!warned.current) setCount(COUNTDOWN - i); }, i * 1000);
        later(() => { if (!warned.current) beginAnswer(seconds); }, COUNTDOWN * 1000);
    }, [beginAnswer, later, setStepBoth]);

    const presentQuestion = useCallback((q: Question) => {
        clearTimers();
        audio.current?.pause();
        recorder.current?.pause();
        current.current = q;
        captionChunk.current = -1;
        setQuestion(q);
        setCaption("");
        setAnswerTotal(q.answer_sec);
        setRemainingBoth(q.answer_sec);
        setStepBoth("reading");
        setPhase("interview");
        const afterReading = () => { if (!warned.current) countdownThen(q.answer_sec); };
        if (q.audio_url) {
            setNoAudio(false);
            const player = new Audio(q.audio_url);
            audio.current = player;
            player.onended = afterReading;
            player.onerror = () => { setNoAudio(true); later(afterReading, NO_AUDIO_READ_MS); };
            player.play().catch(() => { setNoAudio(true); later(afterReading, NO_AUDIO_READ_MS); });
        } else {
            setNoAudio(true);
            later(afterReading, NO_AUDIO_READ_MS);
        }
    }, [clearTimers, countdownThen, later, setRemainingBoth, setStepBoth]);

    const answerDone = useCallback(() => {
        if (stepRef.current !== "answering") return;
        clearTimers();
        endAnswer();
    }, [clearTimers, endAnswer]);

    // ---------- 서버가 판단한 결과 다시 읽기 (연결이 끊겼을 때) ----------
    const settleFromServer = useCallback(async (waitMs: number) => {
        if (ended.current) return;
        stopEverything();
        setOverlay({ kind: "checking" });
        await new Promise((r) => setTimeout(r, waitMs));
        try {
            const s = await api<StateResponse>(`/applications/${applicationId}/interview/state`);
            const map: Record<string, Overlay | null> = {
                interrupted: { kind: "paused", reason: "ws_abnormal_close", resumeUntil: s.resume_until },
                ended: { kind: "ended", detail: s.end_detail },
                cancelled: { kind: "cancelled" },
                ended_closed: { kind: "closed" },
            };
            if (s.attempt_status === "completed") finish(null, "done");
            else finish(map[s.attempt_status] ?? { kind: "paused", reason: "unknown", resumeUntil: s.resume_until });
        } catch {
            finish({ kind: "paused", reason: "offline", resumeUntil: null });
        }
    }, [applicationId, finish, stopEverything]);

    // ---------- 서버 메시지 ----------
    const onMessage = useCallback((raw: string) => {
        lastMessageAt.current = Date.now();
        const m = JSON.parse(raw);
        switch (m.type) {
            case "preparing":
                setPhase("preparing");
                setPrep({ composed: m.composed, total: m.total, elapsed: m.elapsed_sec });
                break;
            case "question":
                warned.current = false;
                setOverlay(null);
                presentQuestion(m as Question);
                break;
            case "caption": {
                const q = current.current;
                const answerNo = q?.kind === "follow_up" ? 2 : 1;
                if (!q || m.seq !== q.seq || m.answer_no !== answerNo || m.chunk_no < captionChunk.current) break;
                captionChunk.current = m.chunk_no;
                setCaption(m.text);
                break;
            }
            case "warn":
                warned.current = true;
                clearTimers();
                audio.current?.pause();
                recorder.current?.pause();
                stream.current?.getAudioTracks().forEach((t) => { t.enabled = false; });
                setAwayCount(1);
                if (typeof m.remaining_sec === "number" && stepRef.current === "answering") setRemainingBoth(m.remaining_sec);
                setOverlay({ kind: "warn", label: m.label ?? "화면 이탈", phase: m.phase });
                break;
            case "resume":
                warned.current = false;
                setOverlay(null);
                if (m.phase === "coding") {
                    setCodingRemaining(m.remaining_sec);
                } else if (current.current && typeof m.remaining_sec === "number") {
                    countdownThen(m.remaining_sec);
                }
                break;
            case "paused":
                finish({ kind: "paused", reason: m.reason, resumeUntil: m.resume_until });
                break;
            case "phase":
                warned.current = false;
                setOverlay(null);
                clearTimers();
                recorder.current?.close();
                recorder.current = null;
                phaseRef.current = "coding";
                setCoding(m.coding as CodingInfo);
                setAwayCount(m.coding.away_count);
                setCodingRemaining(m.coding.remaining_sec ?? 3600);
                setPhase(m.coding.started ? "coding" : "coding-intro");
                break;
            case "terminate":
                if (m.reason === "completed") finish(null, "done");
                else if (m.reason === "cancelled") finish({ kind: "cancelled" });
                else if (m.reason === "closed") finish({ kind: "closed" });
                else if (m.reason === "withdrawn") finish({ kind: "withdrawn" });
                else finish({ kind: "ended", detail: m.detail ?? null });
                break;
            case "error":
                console.warn("server error message", m.code);
                break;
        }
    }, [clearTimers, countdownThen, finish, presentQuestion, setRemainingBoth]);

    // ---------- 연결 · 장치 ----------
    useEffect(() => {
        if (!session) return;
        let disposed = false;
        watching.current = true;
        ended.current = false;
        api<{ posting: Posting }>(`/applications/${applicationId}`).then((r) => setPosting(r.posting)).catch(() => undefined);

        (async () => {
            try {
                const opened = await openStream(loadDeviceChoice());
                if (disposed) { stopStream(opened); return; }
                stream.current = opened;
            } catch {
                // 아직 연결 전이라 보낼 수 없다. 연결되면 바로 알린다 (서버가 장애 중단으로 처리)
                failedDevice.current = "mic";
            }
            if (disposed) return;
            if (video.current && stream.current) video.current.srcObject = stream.current;
            stream.current?.getTracks().forEach((track) => {
                track.onended = () => { if (watching.current) send({ type: "device_error", device: track.kind === "audio" ? "mic" : "camera", kind: "ended" }); };
            });
            if (stream.current) {
                const rec = new PcmRecorder((pcm) => { if (ws.current?.readyState === WebSocket.OPEN) ws.current.send(pcm); });
                try {
                    await rec.open(stream.current);
                    if (disposed) { rec.close(); return; }
                    recorder.current = rec;
                } catch {
                    rec.close();
                    failedDevice.current = "mic";
                }
                if (disposed) return;
            }
            if (stream.current) {
                phaseRef.current = session.phase ?? "interview";
                const cam = new CameraRecorder(session.session_id, session.recording_segment, () => phaseRef.current,
                    () => { if (watching.current) send({ type: "upload_failed" }); });
                try {
                    if (cam.start(stream.current)) {
                        camera.current = cam;
                        setRecordingOn(true);
                    } else {
                        failedDevice.current ??= "camera";
                    }
                } catch {
                    failedDevice.current ??= "camera";
                }
            }
            const socket = new WebSocket(session.ws_url);
            socket.binaryType = "arraybuffer";
            ws.current = socket;
            socket.onopen = () => {
                lastMessageAt.current = Date.now();
                setConn("ok");
                if (failedDevice.current) socket.send(JSON.stringify({ type: "device_error", device: failedDevice.current, kind: "open_failed" }));
            };
            socket.onmessage = (event) => { if (typeof event.data === "string") onMessage(event.data); };
            socket.onclose = (event) => {
                setConn("down");
                if (ended.current || disposed) return;
                // 서버가 15초 뒤 판단하므로 그 뒤에 결과를 읽는다 (TRD 7-2). 이미 쓴 세션(4409)·인증 실패(4401)는 바로 읽는다
                void settleFromServer(event.code === 4409 || event.code === 4401 ? 500 : 17_000);
            };
        })().catch(() => {
            // 연결조차 만들지 못했다. 멈춘 화면에 두지 않고 서버 상태로 안내한다
            if (!disposed) void settleFromServer(500);
        });

        const heartbeat = window.setInterval(() => {
            send({ type: "heartbeat", sent_at: new Date().toISOString() });
            if (ws.current?.readyState === WebSocket.OPEN) setConn(Date.now() - lastMessageAt.current > 20_000 && ws.current.bufferedAmount > 64_000 ? "slow" : "ok");
        }, HEARTBEAT_MS);
        const meter = window.setInterval(() => setLevel(recorder.current?.level() ?? 0), 120);

        return () => {
            disposed = true;
            window.clearInterval(heartbeat);
            window.clearInterval(meter);
            ws.current?.close(1000);
            stopEverything();
        };
        // 세션이 정해지면 한 번만 연결한다
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [session]);

    // ---------- 이탈 감시 (CHT-01, §8.2) ----------
    useEffect(() => {
        if (!session) return;
        const away = (type: "visibility" | "blur" | "fullscreen", extra: Record<string, unknown>) => {
            if (!watching.current) return;
            const t = Date.now();
            if (t - lastAway.current < AWAY_GRACE_MS) return;
            if (type === "fullscreen" && warned.current) return; // 경고 중에는 이미 전체 화면이 풀려 있다
            lastAway.current = t;
            send({ type, at: new Date().toISOString(), ...extra });
        };
        const onVisibility = () => {
            if (document.visibilityState !== "hidden") return;
            if (blurTimer.current) { window.clearTimeout(blurTimer.current); blurTimer.current = null; }
            away("visibility", { state: "hidden" });
        };
        const onBlur = () => {
            blurAt.current = Date.now();
            blurTimer.current = window.setTimeout(() => {
                blurTimer.current = null;
                away("blur", { duration_ms: Date.now() - blurAt.current });
            }, BLUR_THRESHOLD_MS);
        };
        const onFocus = () => { if (blurTimer.current) { window.clearTimeout(blurTimer.current); blurTimer.current = null; } };
        const onFullscreen = () => { if (!document.fullscreenElement) away("fullscreen", { state: "exit" }); };
        const onBeforeUnload = (event: BeforeUnloadEvent) => { if (watching.current) event.preventDefault(); };
        const onPageHide = () => {
            if (!watching.current) return;
            send({ type: "unload", at: new Date().toISOString(), detail: "pagehide" });
            sendUnloadBeacon(session.session_id, "pagehide");
        };
        // 뒤로가기 트랩: 화면은 그대로 두고 안내만 한다. 이탈로 세지 않는다 (§8.7)
        window.history.pushState({ exam: true }, "", window.location.href);
        const onPopState = () => {
            if (!watching.current) return;
            window.history.pushState({ exam: true }, "", window.location.href);
            toast("warn", "응시 중에는 이전 화면으로 갈 수 없습니다");
        };
        const onContextMenu = (event: MouseEvent) => event.preventDefault();

        let permissionStatus: PermissionStatus[] = [];
        Promise.all((["microphone", "camera"] as PermissionName[]).map((name) => navigator.permissions.query({ name }).catch(() => null)))
            .then((list) => {
                permissionStatus = list.filter(Boolean) as PermissionStatus[];
                permissionStatus.forEach((status, i) => {
                    status.onchange = () => {
                        if (status.state !== "granted" && watching.current) {
                            const device = i === 0 ? "mic" : "camera";
                            send({ type: "permission", device });
                            navigator.sendBeacon(`/api/interview/${session.session_id}/events`,
                                new Blob([JSON.stringify({ type: "permission", device, at: new Date().toISOString() })], { type: "application/json" }));
                        }
                    };
                });
            });

        document.addEventListener("visibilitychange", onVisibility);
        window.addEventListener("blur", onBlur);
        window.addEventListener("focus", onFocus);
        document.addEventListener("fullscreenchange", onFullscreen);
        window.addEventListener("beforeunload", onBeforeUnload);
        window.addEventListener("pagehide", onPageHide);
        window.addEventListener("popstate", onPopState);
        document.addEventListener("contextmenu", onContextMenu);
        return () => {
            document.removeEventListener("visibilitychange", onVisibility);
            window.removeEventListener("blur", onBlur);
            window.removeEventListener("focus", onFocus);
            document.removeEventListener("fullscreenchange", onFullscreen);
            window.removeEventListener("beforeunload", onBeforeUnload);
            window.removeEventListener("pagehide", onPageHide);
            window.removeEventListener("popstate", onPopState);
            document.removeEventListener("contextmenu", onContextMenu);
            permissionStatus.forEach((s) => { s.onchange = null; });
        };
    }, [session, send, toast]);

    async function warnAck() {
        // 이 클릭이 전체 화면 요청의 사용자 동작이 된다
        await document.documentElement.requestFullscreen({ navigationUI: "hide" }).catch(() => undefined);
        lastAway.current = Date.now();
        send({ type: "warn_ack", seq: current.current?.seq ?? null });
    }

    const startCoding = useCallback(async () => {
        for (let attempt = 0; attempt < 4; attempt++) {
            try {
                const res = await api<{ remaining_sec: number }>(`/coding/${session!.session_id}/start`, { method: "POST" });
                setCodingRemaining(res.remaining_sec);
                setPhase("coding");
                return;
            } catch {
                await new Promise((r) => setTimeout(r, 1000 * 2 ** attempt));
            }
        }
        // 서버가 시작을 기록하지 못하면 시간이 흐르지 않는다. 서버 판단으로 넘긴다
        toast("error", "코딩테스트를 시작하지 못했습니다. 연결 상태를 확인하고 있습니다");
        void settleFromServer(0);
    }, [session, settleFromServer, toast]);

    const codingFinished = useCallback((auto: boolean) => {
        setCodingAuto(auto);
        finish(null, "done");
    }, [finish]);

    // 세션 없이 들어오면(다른 창·새로고침 뒤) 서버 상태로 화면을 정한다 (§2.3)
    useEffect(() => {
        if (session) return;
        api<StateResponse>(`/applications/${applicationId}/interview/state`).then((s) => {
            const target: Record<string, string> = { interrupted: `/exam/${applicationId}/resume`, ready: `/apply/${applicationId}/precheck`, drafting: `/apply/${applicationId}/consent` };
            if (s.attempt_status === "interviewing" || s.attempt_status === "coding") toast("warn", "다른 창에서 응시 중입니다");
            router.replace(target[s.attempt_status] ?? "/mypage");
        }).catch(() => router.replace("/mypage"));
    }, [session, applicationId, router, toast]);

    if (!session) return <Loading />;

    const total = 10;
    const seq = question?.seq ?? 0;
    const urgent = step === "answering" && remaining <= 10;

    return (
        <div className="exam">
            <header className="exam-head">
                <HugeLogo href={null} height={28} />
                <span className="title">{posting?.title ?? "AI 면접"}</span>
                <span className="spacer" />
                {phase === "interview" && <span className="small" style={{ fontWeight: 600 }}>진행 {question?.progress ?? `${seq} / ${total}`}{question?.kind === "follow_up" && <span className="badge badge-blue" style={{ marginLeft: 8 }}>꼬리질문</span>}</span>}
                {(phase === "coding" || phase === "coding-intro") && <span className="small" style={{ fontWeight: 600 }}>코딩테스트</span>}
                <span className="spacer" />
                {phase !== "done" && <span className="small muted">{recordingOn ? <><span style={{ color: "var(--color-danger)" }}>●</span> 녹화 중</> : "● 카메라 켜짐"}</span>}
                <span className={`conn conn-${conn}`}>{conn === "ok" ? "연결 양호" : conn === "slow" ? "연결 지연" : "연결 끊김"}</span>
            </header>

            {phase === "connecting" && <div className="exam-body"><Spinner /> 면접실에 연결하고 있습니다…</div>}

            {phase === "preparing" && (
                <div className="exam-body">
                    <Mascot name="02-analysis" size={170} />
                    <h1>면접 질문을 준비하고 있습니다</h1>
                    <ol className="stepper">
                        <li className={prep.composed >= prep.total ? "done" : "current"}><span className="dot">{prep.composed >= prep.total ? "✓" : 1}</span>질문 구성</li>
                        <li className={prep.composed >= prep.total ? "current" : ""}><span className="dot">2</span>질문 음성 준비</li>
                        <li><span className="dot">3</span>시작</li>
                    </ol>
                    <div className="timebar" style={{ width: 420 }}><div style={{ width: `${Math.min(100, (prep.elapsed / 60) * 100)}%` }} /></div>
                    <p className="center">{prep.elapsed > 30 ? "조금 더 걸리고 있습니다. 창을 닫지 마세요." : "준비가 끝나면 첫 질문이 자동으로 시작됩니다. 창을 닫지 마세요."}<br />
                        <span className="small muted">ⓘ 질문이 끝나면 3-2-1 후 답변이 녹음됩니다. 답변은 90초입니다.</span></p>
                </div>
            )}

            {phase === "interview" && question && (
                <div className="exam-body">
                    <div className="progress-dots" aria-label={`질문 ${seq} / ${total}`}>
                        {Array.from({ length: total }, (_, i) => <span key={i} className={i + 1 < seq ? "done" : i + 1 === seq ? "now" : ""} />)}
                    </div>
                    <p className="question-text" aria-live="polite">{question.text}</p>
                    {step === "reading" && <p className="muted">{noAudio ? "음성 없이 자막으로 진행합니다" : "🔊 질문을 읽고 있습니다…"}</p>}
                    {step === "countdown" && <div className="countdown" aria-live="assertive">{count}</div>}
                    {(step === "answering" || step === "processing") && (
                        <div className="answer-box">
                            {step === "answering" ? (
                                <>
                                    <div className="row between">
                                        <strong style={{ color: "var(--color-danger)" }}>● 답변 중</strong>
                                        <span className={`remaining${urgent ? " urgent" : ""}`}>남은 시간 {mmss(remaining)}</span>
                                    </div>
                                    <div className={`timebar${urgent ? " urgent" : ""}`}><div style={{ width: `${(remaining / answerTotal) * 100}%` }} /></div>
                                    <div className="row" style={{ flexWrap: "nowrap" }}>
                                        <span aria-hidden>🎙</span>
                                        <div className="level" style={{ flex: 1 }}><div style={{ width: `${Math.round(level * 100)}%` }} /></div>
                                    </div>
                                    <p className="caption-live" title="실시간 자막 · 평가는 답변 전체로 합니다">📝 {caption || "말씀하시면 자막이 나타납니다"} <span className="tiny">(실시간 자막 · 평가는 답변 전체로 합니다)</span></p>
                                    <div className="center"><button type="button" className="btn btn-primary btn-lg" onClick={answerDone}>답변 완료</button></div>
                                </>
                            ) : (
                                <div className="center stack" role="status">
                                    <div><Spinner /> 답변을 확인하고 다음 질문을 준비하고 있습니다…</div>
                                    {caption && <p className="caption-live">📝 {caption}</p>}
                                </div>
                            )}
                        </div>
                    )}
                </div>
            )}

            {phase === "coding-intro" && coding && <CodingIntro info={coding} awayCount={awayCount} onStart={startCoding} />}
            {phase === "coding" && coding && (
                <CodingTest sessionId={session.session_id} problems={coding.problems} remainingSec={codingRemaining}
                    paused={overlay?.kind === "warn"} onFinished={codingFinished} />
            )}

            {phase === "done" && (
                <div className="exam-body">
                    <Mascot name="06-better-hiring" size={180} />
                    <h1>✓ 응시가 완료되었습니다.</h1>
                    {codingAuto && <p className="muted">시간이 끝나 마지막으로 저장된 코드를 제출했습니다.</p>}
                    <p style={{ fontSize: 20 }}>결과는 {posting ? longDateTime(posting.release_at) : "마감 다음 날 10:00"}에 공개됩니다.</p>
                    <p>AI 면접 ✓ 완료{posting?.has_coding_test && <>　　코딩테스트 ✓ 제출 완료</>}</p>
                    <ul className="muted">
                        <li>결과가 공개되면 마이페이지에서 확인할 수 있습니다.</li>
                        <li>결과는 공개일부터 7일 동안 마이페이지에서 볼 수 있습니다.</li>
                    </ul>
                    <div className="row">
                        <Link className="btn btn-secondary" href="/jobs">공고 목록으로</Link>
                        <Link className="btn btn-primary" href="/mypage">마이페이지로</Link>
                    </div>
                </div>
            )}

            {phase !== "done" && phase !== "coding" && phase !== "coding-intro" && (
                <div className="selfcam">
                    <video ref={video} autoPlay muted playsInline aria-label="내 카메라 화면" />
                </div>
            )}

            {overlay && <ExamOverlay overlay={overlay} closeAt={posting?.close_at ?? null} releaseAt={posting?.release_at ?? null} onWarnAck={warnAck} />}
        </div>
    );
}

export default function ExamPage() {
    const me = useGuard("applicant");
    return <DesktopOnly>{me ? <Exam /> : <Loading />}</DesktopOnly>;
}
