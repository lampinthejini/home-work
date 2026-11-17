"""Huge STT 서비스 — faster-whisper (Large V3 Turbo, int8_float16, GPU).

- POST /transcribe : 답변 전체 음성(16kHz mono PCM16)을 최종 글자로 바꾼다 (단어 시각 포함).
- 임시 자막 루프   : Redis 스트림 audio:{sid} 를 CAPTION_INTERVAL_SEC 마다 읽어
                    PUBLISH caption:{sid} 로 돌려준다. GPU 가 바쁘면 그 차례는 건너뛴다 (TRD 5-2).
"""

import asyncio
import json
import os
import threading
import time
from contextlib import asynccontextmanager

import numpy as np
import redis
from fastapi import FastAPI, HTTPException, Query, Request
from faster_whisper import WhisperModel

SAMPLE_RATE = 16000
CAPTION_WINDOW_SEC = 20
MODEL_NAME = os.environ.get("WHISPER_MODEL", "large-v3-turbo")
COMPUTE_TYPE = os.environ.get("WHISPER_COMPUTE", "int8_float16")
CAPTION_INTERVAL_SEC = float(os.environ.get("CAPTION_INTERVAL_SEC", "3"))
REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")
# 면접에서 자주 나오는데 잘못 받아 적기 쉬운 말. 받아 적은 글이 꼬리질문과 채점에 그대로 쓰인다 (논의사항 E16).
# initial_prompt 는 condition_on_previous_text=False 이면 첫 구간에만 쓰이므로 구간마다 들어가는 hotwords 를 쓴다.
# 모델 이름(Qwen 등)은 이력서에 잘 없어 질문마다 주는 말로는 못 고친다 (실측 2026-11-17: Qwen → 'QN').
HOTWORDS = (
    "니즈 군집화 결측치 임베딩 옵티마이저 손실함수 과적합 파인튜닝 트랜스포머 프롬프트 파이프라인 온프레미스 벡터DB "
    "머신러닝 벡터 검색 RAG LLM API GPU LangGraph FastAPI PyTorch Qwen Llama Claude GPT Whisper"
)
# 답변마다 api 가 더 주는 말(그 질문 문장·이력서 기술). 지원자 말을 바꾸지 않고 받아 적을 때 참고만 한다 (2026-11-17 사용자 결정).
# faster-whisper 는 hotwords 를 앞에서부터 HOTWORDS_TOKEN_LIMIT 토큰까지만 쓴다 (max_length 448 의 절반 - 1).
# 더 주는 말을 앞에 두고, 고정 낱말이 잘리지 않을 만큼만 남긴다.
# 실측(2026-11-17, 사용자 녹음 4개): 3회→사내 업무, 온선 안문기기→문서를 나누는 크기, 일자수→글자수로 고쳐졌다.
# 다만 고정 낱말만 줄 때 맞던 'Qwen' 은 더 주는 말이 붙으면 다시 'QN' 이 됐다(앞·뒤 어느 쪽에 두어도). 뒤에 두면 '글자수'도 못 고쳤다.
HOTWORDS_TOKEN_LIMIT = 223
EXTRA_HOTWORDS_CHARS = 150  # 실측: 고정 낱말 98토큰, 질문 한 문장 + 기술 5개 약 35토큰


def tokenCount(text: str) -> int | None:
    tokenizer = getattr(model, "hf_tokenizer", None)
    if tokenizer is None:
        return None
    return len(tokenizer.encode(" " + text, add_special_tokens=False).ids)


def hotwordsWith(extra: str) -> str:
    words = " ".join((extra or "").split())[:EXTRA_HOTWORDS_CHARS].split()
    while words:
        joined = f"{' '.join(words)} {HOTWORDS}"
        count = tokenCount(joined)
        if count is None or count < HOTWORDS_TOKEN_LIMIT:
            return joined
        words.pop()
    return HOTWORDS


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # 켤 때 미리 받아쓰기는 여기서 한다. uvicorn 은 이게 끝나야 요청을 받으므로 /health 는 준비된 뒤에야 답한다.
    # 모듈을 불러올 때 돌리지 않는 것은 테스트(가짜 numpy·모델로 불러옴)가 이 단계를 건너뛰게 하려는 것이다.
    await asyncio.to_thread(warmUp)
    yield


app = FastAPI(title="huge-stt", lifespan=lifespan)
model = WhisperModel(MODEL_NAME, device="cuda", compute_type=COMPUTE_TYPE)
gpuLock = threading.Lock()
redisClient = redis.Redis.from_url(REDIS_URL)


def pcmToFloat(pcm: bytes) -> np.ndarray:
    return np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0


def runTranscribe(audio: np.ndarray, withWords: bool, hotwords: str = HOTWORDS) -> dict:
    segments, _ = model.transcribe(
        audio,
        language="ko",
        vad_filter=True,
        beam_size=5 if withWords else 1,
        word_timestamps=withWords,
        condition_on_previous_text=False,
        hotwords=hotwords,
    )
    texts = []
    words = []
    for seg in segments:
        texts.append(seg.text.strip())
        if withWords and seg.words:
            for w in seg.words:
                words.append({"start": round(w.start, 2), "end": round(w.end, 2), "word": w.word})
    return {"text": " ".join(t for t in texts if t), "words": words}


def warmUp() -> None:
    """켤 때 한 번 받아 적어 둔다 (2026-11-16 실측: 부팅 뒤 첫 받아쓰기가 약 80초 걸려 면접 1번 답변이 20초 제한에 걸림).
    lifespan 이 서버가 요청을 받기 전에 부르므로 끝날 때까지 /health 가 답하지 않는다 — 준비된 뒤에야 healthy 가 된다."""
    started = time.monotonic()
    noise = (np.random.default_rng(0).standard_normal(SAMPLE_RATE * 2) * 0.01).astype(np.float32)
    try:
        # 잡음은 VAD 가 지워 디코더가 돌지 않으므로, 디코더는 VAD 없이 한 번, VAD(Silero) 는 따로 한 번 불러 둔다
        segments, _ = model.transcribe(noise, language="ko", vad_filter=False, beam_size=5, word_timestamps=True,
                                       condition_on_previous_text=False, hotwords=HOTWORDS)
        list(segments)
        runTranscribe(noise, withWords=True)
    except Exception as exc:  # noqa: BLE001 — 미리 돌리기 실패는 서버를 막지 않는다 (첫 요청이 느릴 뿐)
        print(f"stt warm-up failed: {type(exc).__name__}", flush=True)
        return
    print(f"stt warm-up done in {time.monotonic() - started:.1f}s", flush=True)


def transcribeWithGpu(audio: np.ndarray, hotwords: str = HOTWORDS) -> dict:
    with gpuLock:
        return runTranscribe(audio, withWords=True, hotwords=hotwords)


@app.get("/health")
def health():
    return {"status": "ok", "model": MODEL_NAME, "compute": COMPUTE_TYPE}


@app.post("/transcribe")
async def transcribe(request: Request, hotwords: str = Query("", max_length=2000)):
    pcm = await request.body()
    if len(pcm) % 2:
        raise HTTPException(400, "PCM16 length must be even")
    audio = pcmToFloat(pcm)
    started = time.monotonic()
    # 변환은 수 초 걸린다. 사건 루프에서 돌리면 그동안 /health 도 답하지 못한다
    result = await asyncio.to_thread(transcribeWithGpu, audio, hotwordsWith(hotwords))
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
