"""LLM 호출 (TRD 3장 구현 준수 사항, 기술 아키텍처 9-2).

LangChain ChatOpenAI 에 내부 주소(llama.cpp OpenAI 호환 API)를 넣고, JSON 스키마를 강제한 뒤
Pydantic 으로 다시 검사한다. 모든 호출에 시간 제한을 건다. 외부로 나가지 않는다.
"""

import asyncio
import logging
import math

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from ..config import ENV

log = logging.getLogger("huge.llm")
NO_THINK = " /no_think"


class LlmError(Exception):
    pass


# 레인 (AI 아키텍처 v1.4 3장): rt = GPU 4B (면접·질문·채점·총평), eval = CPU 8B (결과 이유 T10)
MODELS = {"rt": "qwen3-4b-instruct-2507-q4_k_m", "eval": "qwen3-8b-q4_k_m"}

# 요청 하나가 쓸 수 있는 토큰 = 입력 + 출력 (compose.ai.yml: rt 는 -c 8192 를 --parallel 2 로 나눔, eval 은 -c 6144 하나).
# 넘으면 llama.cpp 가 바로 거절한다(입력이 넘을 때) 또는 출력이 중간에 끊긴다(입력 + 출력이 넘을 때). 2026-11-18 실측
CONTEXT_TOKENS = {"rt": 4096, "eval": 6144}
TEMPLATE_TOKENS = 40  # 대화 틀(역할 표시·줄바꿈) 몫
CHARS_PER_TOKEN = 1.3  # /tokenize 를 못 쓸 때 어림. 한국어 실측 1.4~1.6자/토큰보다 짧게 잡아 넉넉히 센다


def laneUrl(lane: str) -> str:
    return ENV.llmEvalUrl if lane == "eval" else ENV.llmRtUrl


def chatModel(timeoutSec: float, maxTokens: int, temperature: float, lane: str = "rt") -> ChatOpenAI:
    return ChatOpenAI(
        base_url=laneUrl(lane),
        api_key="internal",
        model=MODELS[lane],
        timeout=timeoutSec,
        max_retries=0,
        max_tokens=maxTokens,
        temperature=temperature,
    )


async def structured(schema: type[BaseModel], system: str, user: str, timeoutSec: float,
                     maxTokens: int = 400, temperature: float = 0.4, lane: str = "rt") -> BaseModel:
    """JSON 스키마 강제 → Pydantic 재검사. 시간 초과·형식 오류는 LlmError."""
    model = chatModel(timeoutSec, maxTokens, temperature, lane).with_structured_output(schema, method="json_schema")
    try:
        result = await asyncio.wait_for(
            model.ainvoke([SystemMessage(content=system), HumanMessage(content=user + NO_THINK)]),
            timeout=timeoutSec,
        )
    except TimeoutError as exc:
        raise LlmError("timeout") from exc
    except Exception as exc:  # noqa: BLE001 — 연결 오류·형식 오류를 한 가지로 다룬다
        if "exceeds the available context" in str(exc):  # 부르는 쪽이 길이를 맞추지 못한 것. 다시 해도 같다
            log.warning("llm prompt too long (lane=%s)", lane)
            raise LlmError("too_long") from exc
        # 답변 내용이 섞일 수 있어 메시지 본문은 남기지 않는다
        log.warning("llm call failed (lane=%s): %s %s", lane, type(exc).__name__, type(exc.__cause__).__name__ if exc.__cause__ else "")
        raise LlmError(type(exc).__name__) from exc
    if not isinstance(result, schema):
        raise LlmError("schema")
    return result


async def health(timeoutSec: float = 3, lane: str = "rt") -> bool:
    import httpx

    try:
        async with httpx.AsyncClient(timeout=timeoutSec) as http:
            res = await http.get(laneUrl(lane).removesuffix("/v1") + "/health")
            return res.status_code == 200
    except httpx.HTTPError:
        return False


async def countTokens(text: str, lane: str = "rt") -> int:
    """llama.cpp /tokenize 로 센 토큰 수. 서버가 답하지 않으면 글자 수로 넉넉히 어림한다."""
    import httpx

    try:
        async with httpx.AsyncClient(timeout=5) as http:
            res = await http.post(laneUrl(lane).removesuffix("/v1") + "/tokenize", json={"content": text})
            res.raise_for_status()
            return len(res.json()["tokens"])
    except (httpx.HTTPError, KeyError, ValueError):
        return math.ceil(len(text) / CHARS_PER_TOKEN)


async def fits(system: str, user: str, maxTokens: int, lane: str = "rt") -> bool:
    """입력(시스템 + 사용자 글) + 출력 상한이 요청 하나에 들어가는가."""
    used = await countTokens(f"{system}\n{user}{NO_THINK}", lane) + TEMPLATE_TOKENS
    return used + maxTokens <= CONTEXT_TOKENS[lane]
