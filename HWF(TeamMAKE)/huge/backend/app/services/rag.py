"""질문 DB 임베딩과 비슷한 질문 찾기 (TRD 7-4 ①②③, 테이블 정의서 4-16 questions.embedding).

- 임베딩: embed 컨테이너(BGE-M3, 1024차원, 길이 1로 맞춤 → 내적 = 코사인 유사도)
- 찾기: PostgreSQL pgvector (HNSW, vector_cosine_ops). SQLite(개발 테스트)에서는 쓰지 않는다
- 기준: 만든 질문이 예시와 0.9 이상 비슷하면 베낀 것, 이미 고른 질문과 0.9 이상이면 중복 (TRD 7-4 ②③)
- 예시는 예비 질문에서 찾는다 (엑셀 질문 DB 는 2026-11-16 지움, CONFLICTS C-20)
"""

import logging
import math
from dataclasses import dataclass

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..config import ENV

log = logging.getLogger("huge.rag")

EMBED_DIM = 1024
COPY_SIMILARITY = 0.9
# 예시로 보여 줄 최소 유사도 (2026-11-16 사용자 결정). 가장 가까운 것도 이보다 멀면 예시 없이 주제만으로 만든다.
# 실측(같은 날, 기본 예비 40개 + AI 질문): 주제와 상관없는 예시는 0.40~0.47, 맞는 예시는 0.5 이상
EXAMPLE_MIN_SIMILARITY = 0.5
DUPLICATE_SIMILARITY = 0.9
RESERVE_DUPLICATE_SIMILARITY = 0.8  # 예비 질문에 넣을 때 (2026-11-16 사용자 결정: 0.7 → 0.8. 면접 안 중복은 위 0.9)
EMBED_TIMEOUT_SEC = 10
INDEX_BATCH = 32
# HNSW 는 가까운 N개를 찾은 뒤 조건으로 거른다. 안 쓰는 질문(excluded·preparing)이 자리를 차지해 예시가 모자라지 않게 넓힌다 (실측 40 → 0개, 200 → 3개, 5ms)
SEARCH_WIDTH = 200
EXAMPLE_KIND = {"personality": "personality", "company": "company", "job": "job", "resume": "resume"}


class EmbedUnavailable(Exception):
    pass


@dataclass
class Example:
    id: int
    text: str
    similarity: float
    vector: list[float]


def supported(db: Session) -> bool:
    return db.get_bind().dialect.name == "postgresql"


def toLiteral(vector: list[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in vector) + "]"


def parseVector(raw) -> list[float]:
    if isinstance(raw, list):
        return [float(x) for x in raw]
    return [float(x) for x in str(raw).strip("[]").split(",") if x]


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


def maxSimilarity(vector: list[float], others: list[list[float]]) -> float:
    return max((cosine(vector, o) for o in others), default=0.0)


def parseResponse(res: httpx.Response, count: int) -> list[list[float]]:
    if res.status_code != 200:
        raise EmbedUnavailable(f"status {res.status_code}")
    vectors = res.json().get("vectors") or []
    if len(vectors) != count or any(len(v) != EMBED_DIM for v in vectors):
        raise EmbedUnavailable("bad_response")
    return vectors


async def embed(texts: list[str], timeoutSec: float = EMBED_TIMEOUT_SEC) -> list[list[float]]:
    try:
        async with httpx.AsyncClient(timeout=timeoutSec) as http:
            res = await http.post(ENV.embedUrl + "/embed", json={"texts": texts})
    except httpx.HTTPError as exc:
        raise EmbedUnavailable(type(exc).__name__) from exc
    return parseResponse(res, len(texts))


def embedSync(texts: list[str], timeoutSec: float = 120) -> list[list[float]]:
    try:
        res = httpx.post(ENV.embedUrl + "/embed", json={"texts": texts}, timeout=timeoutSec)
    except httpx.HTTPError as exc:
        raise EmbedUnavailable(type(exc).__name__) from exc
    return parseResponse(res, len(texts))


async def health(timeoutSec: float = 3) -> bool:
    try:
        async with httpx.AsyncClient(timeout=timeoutSec) as http:
            return (await http.get(ENV.embedUrl + "/health")).status_code == 200
    except httpx.HTTPError:
        return False


def indexedCount(db: Session) -> int:
    if not supported(db):
        return 0
    return db.execute(text("SELECT count(*) FROM questions WHERE embedding IS NOT NULL")).scalar_one()


def indexQuestions(db: Session) -> int:
    """임베딩이 없는 질문을 모두 숫자 목록으로 바꿔 넣는다 (manage.py embed_questions). 다시 돌려도 남은 것만 한다."""
    if not supported(db):
        raise RuntimeError("pgvector 는 PostgreSQL 에서만 쓸 수 있습니다")
    done = 0
    while True:
        rows = db.execute(text("SELECT id, text FROM questions WHERE embedding IS NULL ORDER BY id LIMIT :n"),
                          {"n": INDEX_BATCH}).all()
        if not rows:
            return done
        vectors = embedSync([r.text for r in rows])
        for row, vector in zip(rows, vectors, strict=True):
            db.execute(text("UPDATE questions SET embedding = CAST(:v AS vector) WHERE id = :id"),
                       {"v": toLiteral(vector), "id": row.id})
        db.commit()
        done += len(rows)
        if done % (INDEX_BATCH * 20) == 0:
            log.info("embedded %d questions", done)


def similar(db: Session, slotKind: str, vector: list[float], count: int, excludeIds: set[int],
            jobCode: str | None = None) -> list[Example]:
    """같은 종류 예비 질문 중 뜻이 가장 가까운 것 count 개 (RAG 예시, TRD 7-4 ③-2). 다른 직무 전용 질문은 뺀다."""
    db.execute(text(f"SET LOCAL hnsw.ef_search = {SEARCH_WIDTH}"))
    rows = db.execute(text(
        "SELECT id, text, embedding::text AS emb, 1 - (embedding <=> CAST(:v AS vector)) AS sim FROM questions "
        "WHERE kind = :kind AND status = 'active' AND source = 'reserve' AND embedding IS NOT NULL "
        "AND (job_code IS NULL OR job_code = :job) "
        "AND NOT (id = ANY(:ex)) ORDER BY embedding <=> CAST(:v AS vector) LIMIT :n"),
        {"v": toLiteral(vector), "kind": EXAMPLE_KIND[slotKind], "ex": list(excludeIds) or [-1], "n": count,
         "job": jobCode or ""}).all()
    return [Example(r.id, r.text, float(r.sim), parseVector(r.emb)) for r in rows]


def closeExamples(examples: list[Example]) -> list[Example]:
    """뜻이 너무 먼 예시는 뺀다 (먼 예시를 보여 주면 작은 모델이 그 주제로 끌려간다)."""
    return [e for e in examples if e.similarity >= EXAMPLE_MIN_SIMILARITY]


def maxStoredSimilarity(db: Session, kind: str, vector: list[float]) -> float:
    """같은 종류 질문 DB 전체(상태 무관 — 거절한 질문도 다시 들어오지 않게)에서 가장 비슷한 정도."""
    sim = db.execute(text(
        "SELECT 1 - (embedding <=> CAST(:v AS vector)) FROM questions WHERE kind = :kind AND embedding IS NOT NULL "
        "ORDER BY embedding <=> CAST(:v AS vector) LIMIT 1"), {"v": toLiteral(vector), "kind": kind}).scalar()
    return float(sim) if sim is not None else 0.0


def storeVector(db: Session, questionId: int, vector: list[float]) -> None:
    db.execute(text("UPDATE questions SET embedding = CAST(:v AS vector) WHERE id = :id"), {"v": toLiteral(vector), "id": questionId})


def vectorsFor(db: Session, ids: list[int]) -> dict[int, list[float]]:
    if not ids or not supported(db):
        return {}
    rows = db.execute(text("SELECT id, embedding::text AS emb FROM questions WHERE id = ANY(:ids) AND embedding IS NOT NULL"),
                      {"ids": ids}).all()
    return {r.id: parseVector(r.emb) for r in rows}
