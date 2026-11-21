"""면접 질문 자리마다 넣는 자료 하나 (2026-11-20 사용자 결정, CONFLICTS C-31 — C-30 을 바꿈).

실측(같은 날, 7명 × 3세트): 회사 정보를 통째로 넣으니 회사 질문이 '사용자 중심 … 어떻게 일하고 싶으신가요'의 변형만 나왔고,
직무 주제를 공고 줄에서만 뽑으니 지원자가 달라도 같은 주제(LangChain·벡터 DB, RAG …)만 되풀이됐다.

- 자료를 '칸'으로 나눈다.
  회사 자리: 회사 소개 · 경영 이념 · 인재상 · 회사 프로젝트 · 기술 블로그 최신 글
  직무 자리: 공고 · 직무 소개 · 사내 기술 스택 · AI/AX 가 하는 일 · 최근 소식(질문 만들기 전에 찾은 임시 자료)
- 자리마다 칸을 무작위로 뽑고, 그 칸 안에서는 이력서와 가까운 위 3개 항목 가운데 무작위로 하나를 쓴다 (이미 쓴 항목은 뺀다).
  가장 가까운 하나만 쓰면 비슷한 이력서끼리 늘 같은 항목이 됐다 (실측: 같은 블로그 글 10번, 사용자 결정 같은 날).
  기술 스택은 줄이 아니라 기술 이름 하나가 항목이다.
- 최근 소식은 제목에 기술 이름(사내 기술 스택 · AI 기술 낱말)이 있는 것만 쓰고, 그 이름이 질문에 들어가야 한다
  (실측: '변호사에게 중요한 건…' 같은 소식이 직무 주제로 뽑힘. 공고와의 유사도는 0.36~0.48 로 좋고 나쁨이 갈리지 않았다).
- 자료 한 줄에 함께 나온 두 말을 'A와 B의 차이'로 묻는 질문은 틀린 전제라 다시 만든다 (마지막 시도에도 받지 않는다).
- 한 면접의 같은 종류 자리는 서로 다른 칸을 먼저 쓴다. 다시 만들 때는 다른 칸으로 옮긴다.
- 질문이 그 자료를 썼는지 확인한다: 기술 이름이 있으면 그 이름이 질문에 있어야 하고, 없으면 질문과 자료의 뜻이 가까워야 한다.
자리 하나에 들어가는 자료는 공고 · 이력서 · 이 항목 하나, 3개 (C-30 규칙 유지).
"""

import logging
import random
import re
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from . import company, job_news, rag, tech_blog

log = logging.getLogger("huge.compose")

COMPANY_FIELDS = (("intro", "회사 소개"), ("mission", "경영 이념"), ("talent", "인재상과 일하는 방식"))
JOB_PROFILE_FIELDS = (("jobs_intro", "직무 소개"), ("ai_ax_role", "AI/AX 가 하는 일"))
PROJECT_FIELD, POST_FIELD = ("project", "회사가 진행한 프로젝트"), ("post", "회사 기술 블로그 최신 글")
POSTING_FIELD, STACK_FIELD, NEWS_FIELD = ("posting", "공고"), ("tech_stack", "사내 기술 스택"), ("news", "직무 관련 최근 소식")
LATEST_POST_COUNT = 10  # 기술 블로그 '최신 글' 후보
PIECE_MIN_CHARS = 12  # 이보다 짧은 줄은 제목('인재상')으로 보고 뺀다
PIECE_MAX_CHARS = 200  # 이보다 긴 줄은 문장으로 나눈다
# 질문과 자료의 뜻이 이만큼 가까워야 자료를 쓴 것으로 본다 (기술 이름이 없는 항목만). 실측으로 정한다
MATERIAL_MIN_SIMILARITY = 0.5
# 앞에서 받은 같은 종류 질문과 이만큼 가까운 항목은 건너뛴다 (질문끼리 0.7 이상이면 다시 만들기라 그 전에 피한다)
AVOID_SIMILARITY = 0.6
PICK_TOP = 3  # 칸 안에서 이력서와 가까운 위 몇 개 가운데 무작위로 고른다
# 소식 제목에 이 낱말(또는 사내 기술 스택 이름)이 있어야 직무 자료로 쓴다
NEWS_TECH_WORDS = ("LLM", "sLLM", "에이전트", "NPU", "GPU", "추론", "파인튜닝", "미세 조정", "임베딩", "멀티모달", "언어 모델", "RAG", "벡터")
# 'A와 B(의|간의|사이의) 차이' — 같은 자료 줄에 A·B 가 함께 있으면 서로 다른 것처럼 비교한 틀린 전제
DIFFERENCE = re.compile(r"(\S+?)\s*(?:와|과)\s+(.+?)\s*(?:간의|사이의|의)?\s*(?:개념적\s*)?차이")
DIFFERENCE_REVERSED = re.compile(r"(\S+?)(?:\s*기술)?(?:이|가|은|는)\s+(.+?)(?:와|과)\s*(?:의\s*)?차이")
DIFFERENCE_TAIL = re.compile(r"\s*(기술|방식|방법|개념|모델)$")
DIFFERENCE_PARTICLE = re.compile(r"(을|를|이|가|은|는|의|에서|으로|로)$")
EMBED_TIMEOUT_SEC = 30
EMBED_BATCH = 32  # embed 서버는 한 번에 64개까지 받는다 (rag.INDEX_BATCH 와 같은 크기로 나눠 보낸다)

_vectorCache: dict[str, list[float]] = {}  # 회사 자료는 지원자마다 같아 한 번만 임베딩한다 (앱이 켜 있는 동안)


@dataclass
class Piece:
    kind: str          # company | job
    field: str         # 칸
    label: str         # 칸 이름 (프롬프트에 씀)
    text: str
    term: str | None = None  # 기술 스택 항목: 질문에 꼭 들어가야 하는 기술 이름
    vector: list[float] | None = field(default=None, repr=False)

    @property
    def key(self) -> str:
        return f"{self.field}:{self.text}"


def splitPieces(text: str) -> list[str]:
    """칸 글을 항목으로: 줄마다(앞의 '-' 를 떼고), 긴 줄은 문장으로 나눈다. 짧은 제목 줄은 뺀다."""
    pieces = []
    for line in (text or "").splitlines():
        line = line.strip(" -•·\t")
        if len(line) < PIECE_MIN_CHARS:
            continue
        if len(line) <= PIECE_MAX_CHARS:
            pieces.append(line)
            continue
        current = ""
        for sentence in re.split(r"(?<=[다.])\s+", line):
            if current and len(current) + len(sentence) > PIECE_MAX_CHARS:
                pieces.append(current)
                current = sentence
            else:
                current = f"{current} {sentence}".strip()
        if len(current) >= PIECE_MIN_CHARS:
            pieces.append(current)
    return pieces


def stackTerms(text: str) -> list[tuple[str, str]]:
    """'분류: 기술, 기술' 줄 → [(기술 이름, 분류)]. 괄호 안 쉼표는 나누지 않는다."""
    terms = []
    for line in (text or "").splitlines():
        if ":" not in line:
            continue
        group, names = line.split(":", 1)
        for name in re.split(r",(?![^()]*\))", names):
            name = name.strip()
            if name:
                terms.append((name, group.strip()))
    return terms


def companyPieces(db: Session) -> list[Piece]:
    profile = company.getProfile(db)
    pieces = [Piece("company", key, label, t) for key, label in COMPANY_FIELDS for t in splitPieces(getattr(profile, key) or "")]
    pieces += [Piece("company", *PROJECT_FIELD, company.projectLine(p)[2:]) for p in company.listProjects(db)]
    pieces += [Piece("company", *POST_FIELD, tech_blog.promptLine(p, profile)[2:]) for p in tech_blog.listPosts(db)[:LATEST_POST_COUNT]]
    return pieces


def jobLines(jobsIntro: str, postingTitle: str) -> list[str]:
    """직무 소개 가운데 이 공고 직무의 줄만 ('AI/AX 엔지니어: …'). 맞는 줄이 없으면 모두 (실측 2026-11-20: 다른 직무 줄이 뽑힘)."""
    lines = splitPieces(jobsIntro)
    mine = [line for line in lines if ":" in line and line.split(":", 1)[0].strip() in (postingTitle or "")]
    if not mine:
        return lines
    # 한 줄뿐이면 지원자마다 같은 주제 (실측 2026-11-20 c31b: 30번) → 문장·'~며,' 마디로 나누고 앞에 직무 이름을 붙인다
    split = []
    for line in mine:
        name, body = (part.strip() for part in line.split(":", 1))
        parts = [part.strip() for part in re.split(r"(?<=다\.)\s+|(?<=며),\s*", body) if len(part.strip()) >= PIECE_MIN_CHARS]
        split += [f"{name}: {part}" for part in parts] if len(parts) > 1 else [line]
    return split


def jobPieces(db: Session, postingTopics: list[str], news: list[job_news.JobNews], postingTitle: str = "") -> list[Piece]:
    profile = company.getProfile(db)
    pieces = [Piece("job", *POSTING_FIELD, t) for t in postingTopics]
    pieces += [Piece("job", "jobs_intro", "직무 소개", t) for t in jobLines(profile.jobs_intro or "", postingTitle)]
    pieces += [Piece("job", key, label, t) for key, label in JOB_PROFILE_FIELDS if key != "jobs_intro"
               for t in splitPieces(getattr(profile, key) or "")]
    pieces += [Piece("job", *STACK_FIELD, f"{name} ({group})", term=name) for name, group in stackTerms(profile.tech_stack or "")]
    words = [n for name, _ in stackTerms(profile.tech_stack or "") for n in [name, *termNames(name)]] + list(NEWS_TECH_WORDS)
    for n in news:
        term = newsTerm(n.title, words)
        if term:
            pieces.append(Piece("job", *NEWS_FIELD, n.title, term=term, vector=n.vector))
    return pieces


def newsTerm(title: str, words: list[str]) -> str | None:
    """소식 제목에 나온 첫 기술 이름 (영문 이름은 낱말 단위: 'vLLM' 안의 'LLM' 은 따로 세지 않는다). 없으면 None."""
    for word in words:
        pattern = re.escape(word) if re.search(r"[가-힣]", word) else rf"(?<![A-Za-z]){re.escape(word)}(?![A-Za-z])"
        match = re.search(pattern, title, re.IGNORECASE)
        if match:
            return match.group(0)
    return None


async def embedPieces(pieces: list[Piece], timeoutSec: float = EMBED_TIMEOUT_SEC) -> None:
    """항목 벡터를 채운다. 회사 자료는 앱이 켜 있는 동안 다시 임베딩하지 않는다. 실패하면 벡터 없이 둔다 (앞의 항목을 쓴다)."""
    for p in pieces:
        if p.vector is None and p.text in _vectorCache:
            p.vector = _vectorCache[p.text]
    missing = list(dict.fromkeys(p.text for p in pieces if p.vector is None))
    if not missing:
        return
    try:
        for start in range(0, len(missing), EMBED_BATCH):
            batch = missing[start:start + EMBED_BATCH]
            _vectorCache.update(zip(batch, await rag.embed(batch, timeoutSec=timeoutSec), strict=True))
    except rag.EmbedUnavailable as exc:  # 받은 묶음까지는 쓴다
        log.info("slot material embed stopped: %s", exc)
    for p in pieces:
        if p.vector is None:
            p.vector = _vectorCache.get(p.text)


class MaterialPicker:
    """한 면접의 자리 자료 고르기. rng 는 시험에서 정할 수 있게 받는다."""

    def __init__(self, pieces: list[Piece], resumeVectors: list[list[float]], rng: random.Random | None = None):
        self.pieces = pieces
        self.resumeVectors = resumeVectors
        self.rng = rng or random.Random()
        self.usedKeys: set[str] = set()
        self.usedFields: dict[str, list[str]] = {"company": [], "job": []}

    def fieldOrder(self, kind: str) -> list[str]:
        """이 자리가 칸을 써 볼 차례: 무작위로 섞되, 이 면접에서 아직 안 쓴 칸을 앞에 둔다."""
        fields = list(dict.fromkeys(p.field for p in self.pieces if p.kind == kind))
        self.rng.shuffle(fields)
        used = self.usedFields[kind]
        return [f for f in fields if f not in used] + [f for f in fields if f in used]

    def distance(self, piece: Piece) -> float | None:
        if piece.vector is None or not self.resumeVectors:
            return None
        return rag.chunkDistance(self.resumeVectors, piece.vector)

    def pick(self, kind: str, order: list[str], attempt: int, avoid: list[list[float]] = ()) -> Piece | None:
        """attempt 번째 시도에 쓸 항목. 그 칸이 비었으면 다음 칸. 칸 안에서는 안 쓴 것 가운데 이력서와 가까운 위 PICK_TOP 개 중 무작위.
        avoid(앞에서 받은 같은 종류 질문 벡터)와 가까운 항목은 건너뛴다 — 다 가까우면 그대로 고른다."""
        for step in range(len(order)):
            fieldName = order[(attempt + step) % len(order)]
            inField = [p for p in self.pieces if p.kind == kind and p.field == fieldName]
            fresh = [p for p in inField if p.key not in self.usedKeys] or inField
            if not fresh:
                continue
            fresh = [p for p in fresh if not self.closeTo(p, avoid)] or fresh
            known = sorted((p for p in fresh if self.distance(p) is not None), key=self.distance)
            return self.rng.choice(known[:PICK_TOP]) if known else fresh[0]
        return None

    @staticmethod
    def closeTo(piece: Piece, avoid: list[list[float]]) -> bool:
        return piece.vector is not None and rag.maxSimilarity(piece.vector, list(avoid)) >= AVOID_SIMILARITY

    def markUsed(self, piece: Piece) -> None:
        self.usedKeys.add(piece.key)
        self.usedFields[piece.kind].append(piece.field)


def termNames(term: str) -> list[str]:
    """질문에 나오면 되는 이름들: '검색 증강 생성(RAG)' → 검색 증강 생성·rag, 'LangChain·LangGraph 기반 에이전트' → langchain·langgraph 기반 에이전트."""
    names = [term] + re.findall(r"\(([^)]*)\)", term) + [re.sub(r"\(.*?\)", "", term)]
    names += [part for n in list(names) for part in n.split("·")]
    return [n.strip().lower() for n in dict.fromkeys(names) if len(n.strip()) >= 2]


def grounded(piece: Piece, question: str, questionVector: list[float] | None) -> tuple[bool, float | None]:
    """질문이 자료를 썼나 (맞나, 뜻 가까움). 기술 이름 항목은 이름이 질문에 있어야 한다. 벡터가 없으면 확인하지 않는다."""
    similarity = rag.cosine(questionVector, piece.vector) if questionVector and piece.vector else None
    if piece.term:
        return any(name in question.lower() for name in termNames(piece.term)), similarity
    if similarity is None:
        return True, None
    return similarity >= MATERIAL_MIN_SIMILARITY, similarity


def pairedDifference(pieces: list[Piece], question: str) -> bool:
    """질문이 자료 한 줄에 함께 나온 두 말을 'A와 B의 차이'로 묻나 (실측 2026-11-20: 'RAG와 사내 문서 검색 기술의 차이' 4번, 불량 B1).
    받은 자료 줄만이 아니라 모든 자료 줄과 비교한다 (c31b: 소식 '추론' 을 받은 자리가 AI/AX 줄의 두 말을 비교해 빠져나감).
    'A이 B과 차이' 꼴도 본다 (c31c: 'RAG 기술이 사내 문서 검색과 차이를 가지는 이유')."""
    found = [m.group(1, 2) for pattern in (DIFFERENCE, DIFFERENCE_REVERSED) for m in [pattern.search(question)] if m]
    return any(pairedInPieces(pieces, first, second) for first, second in found)


def pairedInPieces(pieces: list[Piece], first: str, second: str) -> bool:
    first = first.lower()
    # 'B' 뒤에 말이 더 붙으면('사내 문서 검색을 사용할 때 … 방식') 끝에서 한 낱말씩 줄여 가며 자료에 있는지 본다
    words = DIFFERENCE_TAIL.sub("", second.strip()).lower().split()
    seconds = [DIFFERENCE_PARTICLE.sub("", " ".join(words[:n])) for n in range(len(words), 0, -1)]
    seconds = [s for s in seconds if len(s) >= 2]
    if not first or not seconds:
        return False
    # 자료에서 두 말이 'A와 B(으)로' 처럼 함께 쓰는 한 수단으로 나올 때만 ('RAG와 사내 문서 검색으로 … 줄인다').
    # 쉼표·가운뎃점으로 늘어놓은 것, '정답률과 근거 일치율' 처럼 나란히 둔 서로 다른 것의 차이는 막지 않는다
    # (c31b: 'AIIT-X 모델팀, …, AX 추진팀', c31c: '정답률·근거 일치율' 과 회사 프로젝트 줄의 '정답률과 근거 일치율')
    joined = [re.compile(rf"{re.escape(a)}\s*(?:와|과)\s+{re.escape(b)}\s*(?:으로|로)") for s in seconds for a, b in ((first, s), (s, first))]
    return any(j.search(p.text.lower()) for p in pieces for j in joined)
