"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { api, ApiError } from "@/lib/api";
import { canRecord } from "@/lib/recording";
import { detectBrowser, isSupportedBrowser, levelMeter, loadDeviceChoice, measureMbps, openStream, playTestTone, saveDeviceChoice, stopStream, type DeviceChoice } from "@/lib/media";

type CheckState = "checking" | "ok" | "fail" | "idle";
type Checks = { mic: CheckState; camera: CheckState; speaker: CheckState; network: CheckState; ai_server: CheckState };
type PrecheckResponse = { passed: boolean; checks: Record<string, "ok" | "fail">; valid_until: string | null };

const LABEL: Record<keyof Checks, string> = { mic: "① 마이크", camera: "② 카메라", speaker: "③ 스피커", network: "④ 네트워크", ai_server: "⑤ AI 서버" };
const FAIL_HINT: Record<keyof Checks, string> = {
    mic: "다른 마이크를 선택하거나, 주소창 왼쪽 🔒 → 마이크 '허용'으로 바꾼 뒤 [다시 점검]을 눌러 주세요.",
    camera: "다른 프로그램이 카메라를 쓰고 있는지 확인하거나, 🔒 → 카메라 '허용'으로 바꿔 주세요.",
    speaker: "음량과 출력 장치를 확인하고 테스트음을 다시 재생해 주세요.",
    network: "연결이 불안정합니다. 권장 5Mbps 이상",
    ai_server: "AI 서버를 확인하지 못했습니다. 잠시 후 [다시 점검]을 눌러 주세요.",
};

const RECORD_FAIL_HINT = "이 브라우저에서는 카메라 녹화를 할 수 없습니다. Chrome 또는 Edge 최신 버전으로 응시해 주세요.";

const MIC_LEVEL = 0.12; // 레벨 막대 기준 (0~1)
const MIC_GAP_MS = 400; // 이보다 짧은 쉼은 끊긴 것으로 보지 않음

/** S-A06 환경 점검. S-A15 이어가기 재점검에서도 그대로 쓴다 */
export function Precheck({ applicationId, onPassed }: { applicationId: string; onPassed: (passed: boolean) => void }) {
    const browser = useRef(typeof navigator === "undefined" ? { name: "unknown", version: "0" } : detectBrowser());
    const supported = isSupportedBrowser(browser.current);
    const [checks, setChecks] = useState<Checks>({ mic: "checking", camera: "checking", speaker: "idle", network: "checking", ai_server: "checking" });
    const [level, setLevel] = useState(0);
    const [devices, setDevices] = useState<MediaDeviceInfo[]>([]);
    const [choice, setChoice] = useState<DeviceChoice>(() => (typeof window === "undefined" ? {} : loadDeviceChoice()));
    const [permissionDenied, setPermissionDenied] = useState(false);
    const [recordFailed, setRecordFailed] = useState(false);
    const [speakerPlayed, setSpeakerPlayed] = useState(false);
    const [round, setRound] = useState(0);
    const video = useRef<HTMLVideoElement>(null);
    const stream = useRef<MediaStream | null>(null);
    const heardSince = useRef<number | null>(null);
    const lastLoud = useRef(0);
    const checksRef = useRef(checks);

    useEffect(() => { checksRef.current = checks; }, [checks]);

    const set = useCallback((key: keyof Checks, value: CheckState) => setChecks((c) => ({ ...c, [key]: value })), []);

    // ①② 장치 열기 + 마이크 레벨 1초 이상 감지
    useEffect(() => {
        if (!supported) return;
        let stopMeter: (() => void) | null = null;
        let cancelled = false;
        (async () => {
            try {
                const s = await openStream(choice);
                if (cancelled) { stopStream(s); return; }
                stream.current = s;
                setPermissionDenied(false);
                if (video.current) video.current.srcObject = s;
                const hasVideo = s.getVideoTracks().some((t) => t.readyState === "live");
                const recordable = canRecord(s);
                setRecordFailed(!recordable);
                set("camera", hasVideo && recordable ? "ok" : "fail");
                setDevices(await navigator.mediaDevices.enumerateDevices());
                heardSince.current = null;
                stopMeter = levelMeter(s, (value) => {
                    setLevel(value);
                    if (checksRef.current.mic === "ok") return;
                    // 말에는 음절·단어 사이 짧은 쉼이 있으므로 MIC_GAP_MS 보다 짧게 조용한 것은 이어서 말한 것으로 본다
                    const nowMs = performance.now();
                    if (value > MIC_LEVEL) {
                        heardSince.current ??= nowMs;
                        lastLoud.current = nowMs;
                        if (nowMs - heardSince.current >= 1000) set("mic", "ok");
                    } else if (heardSince.current !== null && nowMs - lastLoud.current > MIC_GAP_MS) {
                        heardSince.current = null;
                    }
                });
            } catch (error) {
                const denied = (error as DOMException).name === "NotAllowedError";
                setPermissionDenied(denied);
                set("mic", "fail");
                set("camera", "fail");
            }
        })();
        return () => {
            cancelled = true;
            stopMeter?.();
            stopStream(stream.current);
            stream.current = null;
        };
    }, [choice, round, supported, set]);

    // ④⑤ 네트워크·AI 서버는 서버 점검 API 결과로 정한다 (장치 결과와 함께 마지막에 다시 보낸다)
    const runServerCheck = useCallback(async (devicesOk: { mic: boolean; camera: boolean; speaker: boolean }) => {
        const mbps = await measureMbps();
        try {
            const res = await api<PrecheckResponse>(`/applications/${applicationId}/precheck`, {
                body: { browser: browser.current, devices: devicesOk, network_mbps: mbps === null ? null : String(mbps) },
            });
            set("network", res.checks.network === "ok" ? "ok" : "fail");
            set("ai_server", res.checks.ai_server === "ok" ? "ok" : "fail");
            return res.passed;
        } catch (err) {
            if ((err as ApiError).status === 409) throw err;
            set("network", "fail");
            set("ai_server", "fail");
            return false;
        }
    }, [applicationId, set]);

    // 점검 요청은 차례로 보낸다. 겹치면 늦게 끝난 '장치 미확인' 요청이 서버의 통과 표시를 지울 수 있다
    const checkQueue = useRef<Promise<unknown>>(Promise.resolve());
    const serverCheck = useCallback((devicesOk: { mic: boolean; camera: boolean; speaker: boolean }) => {
        const next = checkQueue.current.then(() => runServerCheck(devicesOk));
        checkQueue.current = next.catch(() => undefined);
        return next;
    }, [runServerCheck]);

    useEffect(() => {
        if (!supported) return;
        // 화면 진입·[다시 점검] 때 서버 점검을 시작한다
        void serverCheck({ mic: false, camera: false, speaker: false });
    }, [round, serverCheck, supported]);

    const deviceOk = checks.mic === "ok" && checks.camera === "ok" && checks.speaker === "ok";
    const allOk = deviceOk && checks.network === "ok" && checks.ai_server === "ok";

    // 장치 셋이 모두 통과하면 서버에 통과 표시를 받는다 (15분 유효)
    useEffect(() => {
        if (!deviceOk) { onPassed(false); return; }
        let cancelled = false;
        serverCheck({ mic: true, camera: true, speaker: true }).then((passed) => { if (!cancelled) onPassed(passed); }).catch(() => onPassed(false));
        return () => { cancelled = true; };
    }, [deviceOk, serverCheck, onPassed]);

    function choose(kind: keyof DeviceChoice, id: string) {
        const next = { ...choice, [kind]: id };
        setChoice(next);
        saveDeviceChoice(next);
        if (kind !== "speaker") setChecks((c) => ({ ...c, [kind === "mic" ? "mic" : "camera"]: "checking" }));
        else { set("speaker", "idle"); setSpeakerPlayed(false); }
    }

    function retry() {
        setChecks({ mic: "checking", camera: "checking", speaker: checks.speaker === "ok" ? "ok" : "idle", network: "checking", ai_server: "checking" });
        setRound((r) => r + 1);
    }

    if (!supported) {
        return <div className="notice notice-error" role="alert">Chrome 또는 Edge 최신 버전에서 응시할 수 있습니다. (지금 브라우저: {browser.current.name} {browser.current.version})</div>;
    }

    const select = (kind: "audioinput" | "videoinput" | "audiooutput", key: keyof DeviceChoice) => {
        const list = devices.filter((d) => d.kind === kind && d.deviceId);
        if (list.length <= 1) return null;
        return (
            <select className="input" style={{ width: 220, minHeight: 36, padding: "4px 8px" }} value={choice[key] ?? ""} aria-label={`${LABEL[key === "mic" ? "mic" : key === "camera" ? "camera" : "speaker"]} 장치 선택`}
                onChange={(e) => choose(key, e.target.value)}>
                <option value="">기본 장치</option>
                {list.map((d) => <option key={d.deviceId} value={d.deviceId}>{d.label || d.deviceId.slice(0, 8)}</option>)}
            </select>
        );
    };

    const badge = (state: CheckState) => state === "ok" ? <span className="badge badge-green">✓ 통과</span>
        : state === "fail" ? <span className="badge badge-red">✕ 실패</span>
            : state === "checking" ? <span className="badge badge-blue">● 확인 중</span> : <span className="badge badge-gray">확인 필요</span>;
    const passedCount = Object.values(checks).filter((v) => v === "ok").length;

    return (
        <div className="stack">
            <p>면접 전에 장비와 연결을 확인합니다.</p>
            {permissionDenied && <div className="notice notice-error" role="alert">마이크·카메라 권한이 막혀 있습니다. 주소창 왼쪽 🔒 → 마이크·카메라 &apos;허용&apos;으로 바꾼 뒤 [다시 점검]을 눌러 주세요.</div>}
            <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1.3fr) minmax(0, 1fr)", gap: 20, alignItems: "start" }}>
                <div className="card stack">
                    {(Object.keys(LABEL) as (keyof Checks)[]).map((key) => (
                        <div key={key} className="stack" style={{ gap: 6 }}>
                            <div className="row between">
                                <strong>{LABEL[key]}</strong>
                                <div className="row">
                                    {key === "mic" && select("audioinput", "mic")}
                                    {key === "camera" && select("videoinput", "camera")}
                                    {key === "speaker" && select("audiooutput", "speaker")}
                                    {badge(checks[key])}
                                </div>
                            </div>
                            {key === "mic" && (
                                <div className="row" style={{ flexWrap: "nowrap" }}>
                                    <div className="level" style={{ flex: 1 }} aria-hidden><div style={{ width: `${Math.round(level * 100)}%` }} /></div>
                                    <span className="small muted">&quot;아무 말이나 해 보세요&quot;</span>
                                </div>
                            )}
                            {key === "speaker" && (
                                <div className="row">
                                    <button type="button" className="btn btn-secondary btn-sm" onClick={() => { void playTestTone(choice.speaker); setSpeakerPlayed(true); set("speaker", "checking"); }}>▶ 테스트음 재생</button>
                                    <button type="button" className="btn btn-secondary btn-sm" disabled={!speakerPlayed} onClick={() => set("speaker", "ok")}>들립니다</button>
                                    <button type="button" className="btn btn-secondary btn-sm" disabled={!speakerPlayed} onClick={() => set("speaker", "fail")}>안 들려요</button>
                                </div>
                            )}
                            {checks[key] === "fail" && <span className="small" style={{ color: "var(--color-danger)" }}>{key === "camera" && recordFailed ? RECORD_FAIL_HINT : FAIL_HINT[key]}</span>}
                        </div>
                    ))}
                </div>
                <div className="card tight" style={{ aspectRatio: "4 / 3", background: "#0F172A", padding: 0, overflow: "hidden" }}>
                    <video ref={video} autoPlay muted playsInline style={{ width: "100%", height: "100%", objectFit: "cover", transform: "scaleX(-1)" }} aria-label="카메라 미리보기" />
                </div>
            </div>
            <div className="row">
                <button type="button" className="btn btn-secondary" onClick={retry}>다시 점검</button>
                <span className="small muted" aria-live="polite">{allOk ? "5개 항목을 모두 통과했습니다" : `${passedCount} / 5 통과`}</span>
            </div>
        </div>
    );
}
