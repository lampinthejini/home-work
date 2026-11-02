"""STT · TTS 내부 서비스 호출. 시간 제한 필수 (기술 아키텍처 4-3)."""

import httpx

from ..config import ENV


class SpeechError(Exception):
    pass


async def transcribe(pcm: bytes, timeoutSec: float) -> dict:
    """16kHz mono PCM16 → {text, words, elapsed_sec}."""
    try:
        async with httpx.AsyncClient(timeout=timeoutSec) as http:
            res = await http.post(f"{ENV.sttUrl}/transcribe", content=pcm, headers={"content-type": "application/octet-stream"})
    except httpx.HTTPError as exc:
        raise SpeechError(type(exc).__name__) from exc
    if res.status_code != 200:
        raise SpeechError(f"stt {res.status_code}")
    return res.json()


async def synthesize(text: str, timeoutSec: float) -> tuple[bytes, float]:
    """한국어 문장 → (WAV 바이트, 길이 초)."""
    try:
        async with httpx.AsyncClient(timeout=timeoutSec) as http:
            res = await http.post(f"{ENV.ttsUrl}/synthesize", json={"text": text})
    except httpx.HTTPError as exc:
        raise SpeechError(type(exc).__name__) from exc
    if res.status_code != 200:
        raise SpeechError(f"tts {res.status_code}")
    return res.content, float(res.headers.get("x-audio-seconds", "0"))


async def serviceHealthy(url: str, timeoutSec: float = 3) -> bool:
    try:
        async with httpx.AsyncClient(timeout=timeoutSec) as http:
            return (await http.get(f"{url}/health")).status_code == 200
    except httpx.HTTPError:
        return False
