"""Huge STT 서비스 — faster-whisper (Large V3 Turbo, int8_float16, GPU).

- POST /transcribe : 답변 전체 음성(16kHz mono PCM16)을 최종 글자로 바꾼다 (단어 시각 포함).
- 임시 자막 루프   : Redis 스트림 audio:{sid} 를 CAPTION_INTERVAL_SEC 마다 읽어
                    PUBLISH caption:{sid} 로 돌려준다. GPU 가 바쁘면 그 차례는 건너뛴다 (TRD 5-2).
"""

import json
import os
import threading
import time

import numpy as np
import redis
from fastapi import FastAPI, HTTPException, Request
from faster_whisper import WhisperModel

SAMPLE_RATE = 16000
CAPTION_WINDOW_SEC = 20
MODEL_NAME = os.environ.get("WHISPER_MODEL", "large-v3-turbo")
COMPUTE_TYPE = os.environ.get("WHISPER_COMPUTE", "int8_float16")
CAPTION_INTERVAL_SEC = float(os.environ.get("CAPTION_INTERVAL_SEC", "3"))
REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")

app = FastAPI(title="huge-stt")
model = WhisperModel(MODEL_NAME, device="cuda", compute_type=COMPUTE_TYPE)
gpuLock = threading.Lock()
redisClient = redis.Redis.from_url(REDIS_URL)


def pcmToFloat(pcm: bytes) -> np.ndarray:
    return np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0


def runTranscribe(audio: np.ndarray, withWords: bool) -> dict:
    segments, _ = model.transcribe(
        audio,
        language="ko",
        vad_filter=True,
        beam_size=5 if withWords else 1,
        word_timestamps=withWords,
        condition_on_previous_text=False,
    )
    texts = []
    words = []
    for seg in segments:
        texts.append(seg.text.strip())
        if withWords and seg.words:
            for w in seg.words:
                words.append({"start": round(w.start, 2), "end": round(w.end, 2), "word": w.word})
    return {"text": " ".join(t for t in texts if t), "words": words}


@app.get("/health")
def health():
    return {"status": "ok", "model": MODEL_NAME, "compute": COMPUTE_TYPE}


@app.post("/transcribe")
async def transcribe(request: Request):
    pcm = await request.body()
    if len(pcm) % 2:
        raise HTTPException(400, "PCM16 length must be even")
    audio = pcmToFloat(pcm)
    started = time.monotonic()
    with gpuLock:
        result = runTranscribe(audio, withWords=True)
    result["elapsed_sec"] = round(time.monotonic() - started, 3)
    result["audio_sec"] = round(len(audio) / SAMPLE_RATE, 2)
    return result


def captionLoop():
    """활성 세션마다 쌓인 음성으로 임시 자막을 만든다. 놓쳐도 되는 값이라 저장하지 않는다."""
    buffers: dict[str, dict] = {}
    while True:
        time.sleep(CAPTION_INTERVAL_SEC)
        try:
            active = [s.decode() for s in redisClient.smembers("caption:active")]
        except redis.RedisError:
            continue
        for sid in list(buffers):
            if sid not in active:
                buffers.pop(sid, None)
        for sid in active:
            state = buffers.setdefault(sid, {"lastId": "0-0", "key": None, "pcm": bytearray(), "chunk": 0, "dirty": False})
            try:
                entries = redisClient.xread({f"audio:{sid}": state["lastId"]}, count=500) or []
            except redis.RedisError:
                continue
            for _stream, items in entries:
                for entryId, fields in items:
                    state["lastId"] = entryId.decode()
                    key = fields[b"answer"].decode()
                    if key != state["key"]:
                        state.update(key=key, pcm=bytearray(), chunk=0)
                    state["pcm"].extend(fields[b"pcm"])
                    state["dirty"] = True
            if not state["dirty"] or state["key"] is None:
                continue
            if not gpuLock.acquire(blocking=False):
                continue  # GPU 가 바쁘면 이번 차례는 건너뛴다
            try:
                window = bytes(state["pcm"][-CAPTION_WINDOW_SEC * SAMPLE_RATE * 2:])
                text = runTranscribe(pcmToFloat(window), withWords=False)["text"]
            except Exception:  # noqa: BLE001 — 자막 실패는 면접 진행에 영향을 주지 않는다
                text = None
            finally:
                gpuLock.release()
            state["dirty"] = False
            if not text:
                continue
            state["chunk"] += 1
            seq, answerNo = state["key"].split(":")
            message = {"seq": int(seq), "answer_no": int(answerNo), "chunk_no": state["chunk"], "text": text, "is_final": False}
            try:
                redisClient.publish(f"caption:{sid}", json.dumps(message, ensure_ascii=False))
            except redis.RedisError:
                pass


threading.Thread(target=captionLoop, daemon=True).start()
