"""STT · TTS 내부 서비스 호출. 시간 제한 필수 (기술 아키텍처 4-3)."""

import httpx

from ..config import ENV


class SpeechError(Exception):
    pass


HINT_SKILL_COUNT = 8


def sttHints(questionText: str, resume: dict) -> str:
    """받아 적을 때 참고할 말: 그 질문 문장 + 이력서 기술 이름 (2026-11-17 사용자 결정, STT 방식 '가').
    지원자 말을 고치지 않고 비슷한 소리를 이 말로 알아듣게만 돕는다. 이름·연락처는 넣지 않는다."""
    skills = list(resume.get("skills", []))
    for project in resume.get("projects", []):
        skills += project.get("skills", [])
    picked = []
    for skill in skills:
        skill = " ".join(str(skill).split())
        if skill and skill.lower() not in {p.lower() for p in picked}:
            picked.append(skill)
    return " ".join([" ".join((questionText or "").split()), *picked[:HINT_SKILL_COUNT]]).strip()


async def transcribe(pcm: bytes, timeoutSec: float, hints: str = "") -> dict:
    """16kHz mono PCM16 → {text, words, elapsed_sec}. hints 는 STT 서버가 고정 낱말 앞에 붙여 쓴다."""
    try:
        async with httpx.AsyncClient(timeout=timeoutSec) as http:
            res = await http.post(f"{ENV.sttUrl}/transcribe", content=pcm, params={"hotwords": hints} if hints else None,
                                  headers={"content-type": "application/octet-stream"})
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
