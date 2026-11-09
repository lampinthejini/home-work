// 장치·브라우저 도우미. 점검(S-A06)에서 고른 장치를 면접에서도 쓴다

export type DeviceChoice = { mic?: string; camera?: string; speaker?: string };
const DEVICE_KEY = "huge:devices";

export function loadDeviceChoice(): DeviceChoice {
    try {
        return JSON.parse(sessionStorage.getItem(DEVICE_KEY) ?? "{}") as DeviceChoice;
    } catch {
        return {};
    }
}

export function saveDeviceChoice(choice: DeviceChoice) {
    sessionStorage.setItem(DEVICE_KEY, JSON.stringify(choice));
}

export function detectBrowser(): { name: string; version: string } {
    const ua = navigator.userAgent;
    const edge = ua.match(/Edg\/(\d+)/);
    if (edge) return { name: "edge", version: edge[1] };
    const chrome = ua.match(/Chrome\/(\d+)/);
    if (chrome && !/OPR\//.test(ua)) return { name: "chrome", version: chrome[1] };
    const firefox = ua.match(/Firefox\/(\d+)/);
    if (firefox) return { name: "firefox", version: firefox[1] };
    const safari = ua.match(/Version\/(\d+).*Safari/);
    return safari ? { name: "safari", version: safari[1] } : { name: "unknown", version: "0" };
}

export function isSupportedBrowser(b: { name: string; version: string }) {
    return (b.name === "chrome" || b.name === "edge") && Number(b.version) >= 120;
}

/** 고른 장치를 먼저 쓰고, 그 장치를 뺐으면 다른 장치로 연다 (exact 로 요구하면 장치를 뺀 뒤 열기에 실패한다) */
export async function openStream(choice: DeviceChoice, video = true): Promise<MediaStream> {
    return navigator.mediaDevices.getUserMedia({
        audio: { deviceId: choice.mic ? { ideal: choice.mic } : undefined, echoCancellation: true, noiseSuppression: true, channelCount: 1 },
        video: video ? { deviceId: choice.camera ? { ideal: choice.camera } : undefined, width: { ideal: 640 }, height: { ideal: 480 } } : false,
    });
}

/** 환경 점검에서 고른 스피커로 소리를 낸다. 고를 수 없는 브라우저나 장치를 뺀 경우는 기본 출력 그대로 */
export async function routeToSpeaker(player: HTMLAudioElement, speakerId?: string): Promise<void> {
    if (!speakerId || !("setSinkId" in player)) return;
    await (player as HTMLAudioElement & { setSinkId: (id: string) => Promise<void> }).setSinkId(speakerId).catch(() => undefined);
}

export function stopStream(stream: MediaStream | null) {
    stream?.getTracks().forEach((t) => t.stop());
}

/** 마이크 입력 크기(0~1)를 콜백으로 알려 주는 측정기 */
export function levelMeter(stream: MediaStream, onLevel: (level: number) => void): () => void {
    const ctx = new AudioContext();
    const source = ctx.createMediaStreamSource(stream);
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 512;
    source.connect(analyser);
    const buffer = new Uint8Array(analyser.fftSize);
    let frame = 0;
    const loop = () => {
        analyser.getByteTimeDomainData(buffer);
        let peak = 0;
        for (const v of buffer) peak = Math.max(peak, Math.abs(v - 128) / 128);
        onLevel(Math.min(1, peak * 2.5));
        frame = requestAnimationFrame(loop);
    };
    loop();
    return () => { cancelAnimationFrame(frame); source.disconnect(); void ctx.close(); };
}

export async function playTestTone(speakerId?: string) {
    const ctx = new AudioContext();
    const dest = ctx.createMediaStreamDestination();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.frequency.value = 660;
    gain.gain.setValueAtTime(0.0001, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.25, ctx.currentTime + 0.05);
    gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 1.2);
    osc.connect(gain);
    const audio = new Audio();
    if (speakerId && "setSinkId" in audio) {
        gain.connect(dest);
        audio.srcObject = dest.stream;
        await (audio as HTMLAudioElement & { setSinkId: (id: string) => Promise<void> }).setSinkId(speakerId).catch(() => undefined);
        await audio.play();
    } else {
        gain.connect(ctx.destination);
    }
    osc.start();
    osc.stop(ctx.currentTime + 1.3);
    window.setTimeout(() => { audio.pause(); void ctx.close(); }, 1500);
}

/** 대략의 내려받기 속도(Mbps). 같은 서버의 정적 파일로 잰다 */
export async function measureMbps(): Promise<number | null> {
    try {
        const started = performance.now();
        const res = await fetch(`/brand/og-image.jpg?t=${Date.now()}`, { cache: "no-store" });
        const bytes = (await res.arrayBuffer()).byteLength;
        const seconds = Math.max(0.001, (performance.now() - started) / 1000);
        return Math.round(((bytes * 8) / seconds / 1_000_000) * 10) / 10;
    } catch {
        return null;
    }
}
