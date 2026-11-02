"""Huge TTS 서비스 — Supertonic (한국어, CPU, ONNX).

POST /synthesize {"text"} → audio/wav. 응답 헤더 x-audio-seconds 에 길이(초).
모델 파일은 처음 기동할 때 한 번 받아 HF 캐시 볼륨에 둔다.
"""

import io
import os
import threading
import time

import numpy as np
import soundfile as sf
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field
from supertonic import TTS

MODEL_NAME = os.environ.get("TTS_MODEL", "supertonic-3")
VOICE = os.environ.get("TTS_VOICE", "F1")
SPEED = float(os.environ.get("TTS_SPEED", "1.0"))
STEPS = int(os.environ.get("TTS_STEPS", "8"))

app = FastAPI(title="huge-tts")
engine = TTS(model=MODEL_NAME, auto_download=True)
voiceStyle = engine.get_voice_style(VOICE)
sampleRate = int(getattr(engine, "sample_rate", 0) or getattr(getattr(engine, "model", None), "sample_rate", 0) or 44100)
lock = threading.Lock()


class SynthesizeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=600)


@app.get("/health")
def health():
    return {"status": "ok", "model": MODEL_NAME, "voice": VOICE, "sample_rate": sampleRate}


@app.post("/synthesize")
def synthesize(body: SynthesizeRequest):
    started = time.monotonic()
    try:
        with lock:
            wav, duration = engine.synthesize(body.text, voice_style=voiceStyle, total_steps=STEPS, speed=SPEED, lang="ko")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"synthesis failed: {type(exc).__name__}") from exc
    samples = np.asarray(wav).reshape(-1)
    buffer = io.BytesIO()
    sf.write(buffer, samples, sampleRate, format="WAV", subtype="PCM_16")
    seconds = float(np.asarray(duration).reshape(-1)[0]) if np.size(duration) else len(samples) / sampleRate
    return Response(
        content=buffer.getvalue(),
        media_type="audio/wav",
        headers={"x-audio-seconds": f"{seconds:.2f}", "x-elapsed-seconds": f"{time.monotonic() - started:.2f}"},
    )
