// 카메라 녹화: MediaRecorder 10초 조각을 순서대로 올린다 (API 명세서 6장 POST /interview/{sid}/recording).
// 녹화는 부정행위 확인용이며 평가에 쓰지 않는다. 조각은 1·2·4초 간격으로 3번(upload_retry_limit) 다시 올리고,
// 그래도 안 되면 onFail 을 한 번 부른다 (서버가 장애 중단으로 판단)

import { api, ApiError } from "@/lib/api";

const SLICE_MS = 10_000;
const RETRY_DELAYS_MS = [1000, 2000, 4000];
const VIDEO_BITS = 300_000;

function mimeType(): string | undefined {
    return ["video/webm;codecs=vp8,opus", "video/webm"].find((t) => MediaRecorder.isTypeSupported(t));
}

function createRecorder(stream: MediaStream): MediaRecorder {
    return new MediaRecorder(stream, { mimeType: mimeType(), videoBitsPerSecond: VIDEO_BITS });
}

/** 환경 점검용: 이 브라우저에서 실제로 녹화를 시작할 수 있는지 잠깐 켜 본다 */
export function canRecord(stream: MediaStream): boolean {
    if (typeof MediaRecorder === "undefined") return false;
    try {
        const probe = createRecorder(stream);
        probe.start();
        probe.stop();
        return true;
    } catch {
        return false;
    }
}

export class CameraRecorder {
    private recorder: MediaRecorder | null = null;
    private chunkNo = 0;
    private queue: Promise<void> = Promise.resolve();
    private failed = false;
    private closed = false;

    constructor(
        private sessionId: string,
        private segment: number,
        private phase: () => "interview" | "coding",
        private onFail: () => void,
    ) {}

    /** 녹화를 지원하지 않는 브라우저면 false. 응시 화면이 장치 오류로 처리한다 */
    start(stream: MediaStream): boolean {
        if (typeof MediaRecorder === "undefined" || this.recorder) return false;
        this.recorder = createRecorder(stream);
        this.recorder.ondataavailable = (event) => {
            if (event.data.size === 0 || this.failed) return;
            const no = this.chunkNo++;
            const phase = this.phase();
            this.queue = this.queue.then(() => this.upload(no, event.data, phase));
        };
        this.recorder.start(SLICE_MS);
        return true;
    }

    /** 남은 조각까지 올리게 멈춘다. 트랙을 끄기 전에 부른다 */
    stop() {
        this.closed = true;
        if (this.recorder && this.recorder.state !== "inactive") this.recorder.stop();
    }

    private async upload(chunkNo: number, data: Blob, phase: string) {
        if (this.failed) return;
        const form = new FormData();
        form.append("segment_no", String(this.segment));
        form.append("chunk_no", String(chunkNo));
        form.append("phase", phase);
        form.append("file", data, `${chunkNo}.webm`);
        for (let attempt = 0; ; attempt++) {
            try {
                await api(`/interview/${this.sessionId}/recording`, { body: form });
                return;
            } catch (err) {
                const status = (err as ApiError).status;
                // 4xx 는 다시 보내도 같다. 응시가 끝난 뒤(409)면 조용히 멈춘다
                if (status >= 400 && status < 500) {
                    if (status !== 409) console.warn("recording chunk rejected", (err as ApiError).code);
                    return;
                }
                if (attempt >= RETRY_DELAYS_MS.length) break;
                await new Promise((r) => setTimeout(r, RETRY_DELAYS_MS[attempt]));
            }
        }
        this.failed = true;
        if (this.recorder && this.recorder.state !== "inactive") this.recorder.stop();
        if (!this.closed) this.onFail();
    }
}
