"""공고 기반 예비 질문 (2026-11-10 사용자 결정 C-17, 2026-11-16 C-20 으로 바뀜).

공고를 게시하면 그 공고의 업무·자격 줄마다 직무 질문 1개, 회사 질문 COMPANY_COUNT 개를 만들어 예비 질문에 바로 넣는다 (승인 없음).
공고와 회사 정보만 보고 만든다 — 지원자 정보는 넣지 않는다.
면접 질문 만들기와 같은 프롬프트·검사(question_compose)를 쓰고, 같은 종류 예비 질문과 0.8 이상 비슷하거나
그 종류가 100개 찼으면 넣지 않는다 (question_bank.saveReserve).
실패해도 게시에는 영향이 없다 (뒤에서 돌고, 오류는 기록만 한다).
"""

import asyncio
import json
import logging

from sqlalchemy.orm import Session

from ..db import SessionLocal
from ..domain import question_text
from ..models import AuditLog, JobPosting
from . import company, llm, question_bank, rag
from . import question_compose as qc
from .evaluation import fence

log = logging.getLogger("huge.posting_questions")

CATEGORY = "공고 기반"
WEB_CATEGORY = "인터넷 참고"
JOB_TOPIC_LIMIT = 6  # 직무 질문 후보 수 상한 (공고 줄 수가 많아도)
# 회사 질문 자리마다 다른 초점 (실측 2026-11-10: 같은 프롬프트 3번이면 '문화에 매력' 질문으로 쏠림)
COMPANY_ANGLES = ("지원 동기", "우리 회사가 하는 일과 이 직무에 대한 이해", "조직 문화와 본인이 일하는 방식")
COMPANY_COUNT = len(COMPANY_ANGLES)
ATTEMPTS = 2  # 한 자리를 만들어 보는 횟수 (처음 + 고쳐 다시 1번)
TIMEOUT_SEC = 60  # 뒤에서 도는 일이라 면접 때(question_attempt_timeout_sec)보다 넉넉하게
EXAMPLE_COUNT = 3

tasks: set[asyncio.Task] = set()


def schedule(postingId: str) -> None:
    task = asyncio.get_running_loop().create_task(generateForPosting(postingId))
    tasks.add(task)
    task.add_done_callback(tasks.discard)


def saveCandidate(db: Session, posting: JobPosting | None, kind: str, text: str, vector: list[float] | None, category: str) -> bool:
    scope = qc.scopeFor(kind, posting) if posting else {"jobCode": None}
    return question_bank.saveReserve(db, kind, text, vector, category, **scope) is not None


async def examplesFor(db: Session, posting: JobPosting, kind: str, topic: str | None) -> tuple[list[rag.Example], list[float] | None]:
    """예비 질문 예시와 찾을 글의 벡터 (회사 질문은 이 벡터로 가까운 최근 소식을 고른다)."""
    try:
        vector = (await rag.embed([qc.queryText(kind, posting, {}, topic)]))[0]
        return rag.closeExamples(rag.similar(db, kind, vector, EXAMPLE_COUNT, set(), posting.job_code)), vector
    except rag.EmbedUnavailable:
        return [], None


async def makeOne(db: Session, posting: JobPosting, kind: str, topic: str | None, made: list[tuple[str, list[float] | None]]):
    """질문 1개를 만들어 검사한다. (글, 벡터) 또는 (None, None)."""
    vectorsOn = rag.supported(db)
    examples, queryVector = await examplesFor(db, posting, kind, topic) if vectorsOn else ([], None)
    postingText = fence(qc.companyText(posting, brief=kind == "job"))
    companyInfo = fence(company.questionContext(db, queryVector)) if kind == "company" else ""
    problem = None
    for _ in range(ATTEMPTS):
        prompt = qc.ragPrompt(kind, postingText, "", examples, [t for t, _ in made], problem, topic, companyInfo)
        try:
            out = await llm.structured(qc.RagQuestion, qc.SYSTEM, prompt, TIMEOUT_SEC, maxTokens=400, temperature=0.6)
        except llm.LlmError:
            return None, None
        text = question_text.cleanQuestion(out.question)
        code = qc.checkGenerated(kind, out, "")
        if code is None and question_bank.excludedReason(text):
            code = "other_company"
        if code is None and (question_bank.isKnown(db, text) or qc.isRepeat(text, [{"text": t} for t, _ in made])):
            code = "duplicate"
        vector = None
        if code is None and vectorsOn:
            try:
                vector = (await rag.embed([text]))[0]
            except rag.EmbedUnavailable:
                vector = None
            if vector and (rag.maxStoredSimilarity(db, kind, vector) >= rag.RESERVE_DUPLICATE_SIMILARITY
                           or rag.maxSimilarity(vector, [v for _, v in made if v]) >= rag.RESERVE_DUPLICATE_SIMILARITY):
                code = "duplicate"
        if code is None:
            return text, vector
        problem = qc.PROBLEM_TEXT.get(code, code) + (f' — 이전 질문: "{fence(text)}"' if text else "")
    return None, None


async def generateForPosting(postingId: str) -> dict:
    saved = skipped = 0
    try:
        with SessionLocal() as db:
            posting = db.get(JobPosting, postingId)
            if posting is None:
                return {"saved": 0, "skipped": 0}
            slots = [("job", t) for t in qc.jobTopics(posting, {})[:JOB_TOPIC_LIMIT]] + [("company", angle) for angle in COMPANY_ANGLES]
            made: list[tuple[str, list[float] | None]] = []
            for kind, topic in slots:
                if question_bank.reserveCount(db, kind) >= question_bank.RESERVE_LIMIT_PER_KIND:
                    skipped += 1  # 이 종류 예비 질문이 다 찼으면 LLM 을 쓰지 않는다
                    continue
                text, vector = await makeOne(db, posting, kind, topic, made)
                if text is None or not saveCandidate(db, posting, kind, text, vector, CATEGORY):
                    skipped += 1
                    continue
                made.append((text, vector))
                saved += 1
            db.add(AuditLog(action="question.posting_candidates", target=postingId, detail={"saved": saved, "skipped": skipped}))
            db.commit()
    except Exception:  # noqa: BLE001 — 후보 만들기는 부가 기능이라 게시를 막지 않는다
        log.exception("posting %s question candidates failed", postingId)
    return {"saved": saved, "skipped": skipped}


def loadWebCandidates(db: Session, path: str, postingId: str) -> int:
    """인터넷 참고 후보 파일(huge/data/web_questions_candidates.json)에서 예비 질문에 넣는다 (saveReserve 규칙).
    직무 질문은 그 공고의 직무만, 나머지는 공통. 이미 있는 글은 건너뛴다."""
    posting = db.get(JobPosting, postingId)
    if posting is None:
        raise ValueError(f"공고가 없습니다: {postingId}")
    rows = [q for q in json.load(open(path, encoding="utf-8"))["questions"]
            if q.get("check", {}).get("verdict") == "new" and not question_bank.isKnown(db, q["text"])]
    vectors: list[list[float] | None] = [None] * len(rows)
    if rows and rag.supported(db):
        texts = [q["text"] for q in rows]
        vectors = [v for i in range(0, len(texts), rag.INDEX_BATCH) for v in rag.embedSync(texts[i:i + rag.INDEX_BATCH])]
    saved = sum(saveCandidate(db, posting, q["kind"], q["text"], vector, WEB_CATEGORY) for q, vector in zip(rows, vectors, strict=True))
    db.add(AuditLog(action="question.web_candidates", target=postingId, detail={"saved": saved, "path": path}))
    db.commit()
    return saved
