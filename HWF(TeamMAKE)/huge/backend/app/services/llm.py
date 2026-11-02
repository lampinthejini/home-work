"""LLM 호출 (TRD 3장 구현 준수 사항, 기술 아키텍처 9-2).

LangChain ChatOpenAI 에 내부 주소(llama.cpp OpenAI 호환 API)를 넣고, JSON 스키마를 강제한 뒤
Pydantic 으로 다시 검사한다. 모든 호출에 시간 제한을 건다. 외부로 나가지 않는다.
"""

import asyncio
import logging

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
