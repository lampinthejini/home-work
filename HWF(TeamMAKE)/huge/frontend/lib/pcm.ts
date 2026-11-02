// 답변 녹음기: 켜져 있는 동안만 PCM 조각을 onChunk 로 넘긴다. 마이크 레벨도 함께 잰다

export class PcmRecorder {
    private ctx: AudioContext | null = null;
    private node: AudioWorkletNode | null = null;
    private analyser: AnalyserNode | null = null;
    private source: MediaStreamAudioSourceNode | null = null;
    private sending = false;

    constructor(private onChunk: (pcm: ArrayBuffer) => void) {}

    async open(stream: MediaStream) {
        this.ctx = new AudioContext({ sampleRate: 16000 });
        await this.ctx.audioWorklet.addModule("/pcm-worklet.js");
        this.source = this.ctx.createMediaStreamSource(stream);
        this.node = new AudioWorkletNode(this.ctx, "pcm-chunker");
        this.analyser = this.ctx.createAnalyser();
        this.analyser.fftSize = 512;
        this.node.port.onmessage = (event: MessageEvent<ArrayBuffer>) => {
            if (this.sending) this.onChunk(event.data);
        };
        this.source.connect(this.analyser);
        this.source.connect(this.node);
    }

    start() {
        void this.ctx?.resume();
        this.node?.port.postMessage("reset"); // 이전 답변·경고 전의 남은 소리를 버린다
        this.sending = true;
    }

    /** 남은 조각을 보내고 멈춘다 */
    stop() {
        if (!this.sending) return;
        this.node?.port.postMessage("flush");
        window.setTimeout(() => { this.sending = false; }, 120);
    }

    pause() {
        this.sending = false;
    }

    level(): number {
        if (!this.analyser) return 0;
        const buffer = new Uint8Array(this.analyser.fftSize);
        this.analyser.getByteTimeDomainData(buffer);
        let peak = 0;
        for (const v of buffer) peak = Math.max(peak, Math.abs(v - 128) / 128);
        return Math.min(1, peak * 2.5);
    }

    close() {
        this.sending = false;
        this.source?.disconnect();
        this.node?.disconnect();
        void this.ctx?.close();
        this.ctx = null;
    }
}
