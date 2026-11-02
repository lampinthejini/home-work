// 마이크 → 16kHz mono PCM16 약 1초 조각 (AudioContext 를 16000Hz 로 열어 브라우저가 다시 샘플링한다)
// 면접 답변 음성을 WebSocket 바이너리로 보낸다 (ADR-03 대체안, 2026-10-30 결정)
class PcmChunker extends AudioWorkletProcessor {
    constructor() {
        super();
        this.size = sampleRate; // 1초
        this.buffer = new Int16Array(this.size);
        this.offset = 0;
        this.port.onmessage = (event) => {
            if (event.data === "flush" && this.offset > 0) {
                this.port.postMessage(this.buffer.slice(0, this.offset).buffer);
            }
            this.offset = 0; // "flush" 는 남은 조각을 보내고, "reset" 은 버린다
        };
    }

    process(inputs) {
        const channel = inputs[0] && inputs[0][0];
        if (!channel) return true;
        for (let i = 0; i < channel.length; i++) {
            const s = Math.max(-1, Math.min(1, channel[i]));
            this.buffer[this.offset++] = s < 0 ? s * 0x8000 : s * 0x7fff;
            if (this.offset === this.size) {
                this.port.postMessage(this.buffer.slice().buffer);
                this.offset = 0;
            }
        }
        return true;
    }
}

registerProcessor("pcm-chunker", PcmChunker);
