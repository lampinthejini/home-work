"""AI 공고 초안 (S-R02, JOB-02, G-06).

정해진 값(고용 형태·근무지·인원·접수 기간·코딩테스트 여부)은 AI를 거치지 않고 그대로 복사한다.
AI(llm-rt)는 제목·부서 소개(company_intro)·주요 업무·자격 요건·우대 사항 문장만 쓴다. 회사명은 쓰지 않는다 (단일 기업 서비스).
진행 상태는 api 프로세스 안에 둔다 (1단계, 프로세스 1개 기준). 재시작으로 상태가 사라지면 '실패'로 보여 다시 시도하게 한다.

문장 쓰기는 LangGraph 그래프로 돈다 (2026-11-10 사용자 결정). 갈림길은 코드가 정한다.
  새 초안:   retrieve(같은 직무 예전 공고) → draft → check(칸별) ─ 문제 칸 → rewrite → check ─ 통과·횟수 끝 → save(DB)
  다시 쓰기: rewrite(관리자가 고른 칸, 요청 메모) → check ─ 문제 → rewrite → check ─ 통과·횟수 끝 → deliver(화면에만)
두 흐름은 thread_id = 'posting-draft:{공고 id}' 하나를 같이 써서, 다시 쓰기 때 처음 입력·참고 공고를 체크포인트에서 읽는다.
interrupt 로 멈춰 두지 않는 것은 로컬 Python 3.10 에서 interrupt 가 동작하지 않고, 멈춘 작업을 서버에 남기지 않기 위해서다.
"""

import asyncio
import logging
import random
import re
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

from .. import db as dbModule
from ..interview import checkpoint
from ..models import JobPosting
from . import llm

log = logging.getLogger("huge.posting_draft")

DRAFT_TIMEOUT_SEC = 150
DRAFT_ATTEMPTS = 2
CAREER_LABEL = {"junior": "신입", "experienced": "경력", "any": "경력 무관"}

# 차별로 보일 수 있는 표현 (화면정의서 O-05: 규칙 기반 사전). 막지 않고 알려 준다
BIAS_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\d{2}\s*~\s*\d{2}\s*대|\d{2}세\s*(이하|미만|이상)|만\s*\d{2}세|나이\s*제한"), "나이 제한"),
    (re.compile(r"남성|여성|남자|여자|남녀"), "성별"),
    (re.compile(r"기혼|미혼|결혼"), "혼인 여부"),
    (re.compile(r"용모\s*단정|키\s*\d{3}"), "외모·신체 조건"),
    (re.compile(r"출신\s*지역|고향"), "출신 지역"),
    (re.compile(r"종교|신앙|기독교|천주교|불교|교회\s*출석"), "종교"),  # 화면(PostingEditor)과 같은 규칙 (TC-170)
]

SYSTEM = (
    "너는 한 회사의 채용 담당자를 돕는 공고 작성 도우미다. 관리자가 준 정보만으로 채용 공고 문장을 한국어로 쓴다.\n"
    "규칙: 주어진 정보에 없는 연봉·복지·수치·회사명은 지어내지 않는다. 부서는 '저희 부서' 또는 '저희 팀'으로 부른다. "
    "나이·성별·혼인·외모·출신 지역으로 지원을 제한하는 표현을 쓰지 않는다. "
    "제목은 '직무 (경력 수준)' 형식으로 쓴다. 예: AI/AX 엔지니어 (경력 3년 이상). "
    "부서 소개는 이 직무가 속한 부서를 지원자에게 소개하는 2~4문장이다. 메모를 그대로 옮기지 않는다. "
    "메모가 짧거나 없으면 주로 맡을 일·필요한 기술·강조할 점을 바탕으로 이 부서가 어떤 일을 하고 어떻게 일하는지 자연스럽게 쓴다. "
    "인원수·설립 연도·실적 수치·고객사 이름·복지처럼 주어진 정보에 없는 사실은 지어내지 않는다. "
    "주로 맡을 일이 (지정 없음)이면 직무·필요한 기술·강조할 점에 맞는 일을 정해서 주요 업무를 쓴다. "
    "관리자가 직접 입력한 맡을 일은 문장이 어색하거나 짧아도 뜻을 살려 자연스러운 공고 문장으로 다듬어 쓴다. "
    "우대 사항 메모가 있으면 반드시 그 내용을 살려 preferred 에 '- '로 시작하는 줄 1~3개로 쓴다. "
    "우대 사항 메모가 (없음)일 때만 preferred 를 빈 문자열로 둔다. "
    "주요 업무·자격 요건은 '- '로 시작하는 줄 3~6개로 쓴다. "
    # 끝맺음 통일·약어 그대로 (2026-11-03 사용자 결정: 약어를 틀리게 풀어 쓰느니 그대로 둔다)
    "끝맺음은 칸마다 하나로 통일한다: 부서 소개는 모든 문장을 '~습니다'로, 주요 업무는 모든 줄을 '~합니다'로 "
    "(예: - LLM 기반 서비스를 설계하고 개발합니다), 자격 요건·우대 사항은 모든 줄을 '~ 분'으로 끝낸다 "
    "(예: - Python으로 서비스를 개발한 경험이 있는 분). '~한다'·'~함'·'~하기'로 끝내지 않는다. "
    "RAG·LLM·MLOps·AX 같은 약어는 괄호로 풀어 쓰지 않고 그대로 쓴다. JSON 으로만 답한다."
)


class DraftText(BaseModel):
    title: str = Field(description="공고 제목, 40자 이내. 예: AI/AX 엔지니어 (경력 3년 이상)")
    company_intro: str = Field(description="부서 소개 2~4문장, 모든 문장을 '~습니다'로 끝냄")
    duties: str = Field(description="주요 업무, '- ' 로 시작하고 '~합니다'로 끝나는 줄")
    requirements: str = Field(description="자격 요건, '- ' 로 시작하고 '~ 분'으로 끝나는 줄")
    preferred: str = Field(description="우대 사항, 메모 내용을 살려 '- ' 로 시작하고 '~ 분'으로 끝나는 줄 1~3개. 우대 사항 메모가 (없음)일 때만 빈 문자열")


drafts: dict[str, dict] = {}  # posting_id → status() 의 모양 (status·stage·bias_warnings·notes·revision·error)
tasks: set[asyncio.Task] = set()


def biasWarnings(*texts: str) -> list[dict]:
    found, seen = [], set()
    for text in texts:
        for pattern, reason in BIAS_RULES:
            for match in pattern.finditer(text or ""):
                if match.group(0) not in seen:
                    seen.add(match.group(0))
                    found.append({"text": match.group(0), "reason": reason})
    return found


def buildPrompt(body, jobName: str) -> str:
    career = CAREER_LABEL[body.career_level]
    if body.career_level == "experienced" and body.career_years:
        career += f" {body.career_years}년 이상"
    lines = [
        f"직무: {jobName}",
        f"경력 수준: {career}",
        f"주로 맡을 일: {', '.join(body.duties) or '(지정 없음)'}",
        f"필요한 기술: {', '.join(body.skills) or '(지정 없음)'}",
        f"우대 사항 메모: {body.preferred or '(없음)'}",
        f"부서 소개 메모: {body.company_intro.strip() or '(없음)'}",
        f"지금 회사 상황·강조할 점: {body.emphasis or '(없음)'}",
    ]
    return "아래 정보로 채용 공고 초안을 써라.\n" + "\n".join(lines)


INTRO_MIN_LEN = 10


def isUsable(draft: DraftText) -> bool:
    """부서 소개는 보지 않는다 (짧으면 fillGaps 가 맡을 일로 만든 소개로 채운다)."""
    return 0 < len(draft.title.strip()) <= 200 and len(draft.duties.strip()) >= 10 and len(draft.requirements.strip()) >= 10


def isDashOnly(text: str) -> bool:
    return all(line.strip() in ("", "-") for line in text.splitlines())


# AI 가 부서 소개를 제대로 못 썼을 때 쓰는 기본 문구 (2026-11-02 사용자 결정). {job}·{duties}·{skills} 만 채운다.
# '{duties} 등을' 로 맺어 직접 입력한 맡을 일이 무엇으로 끝나든 조사가 어색하지 않게 한다 (2026-11-03)
INTRO_TEMPLATES = (
    "저희 부서는 {job} 직무로 {duties} 등을 맡고 있습니다.{skills_sentence}",
    "{job} 직무가 속한 저희 부서는 {duties} 등을 중심으로 일합니다.{skills_sentence}",
    "저희 부서에서는 {duties} 등을 함께 해 나갈 {job} 분을 찾고 있습니다.{skills_sentence}",
)

# 화면의 맡을 일 칩(admin/postings/ai DUTY_OPTIONS)을 문장에 넣을 때 쓰는 미리 정한 문구. 직접 입력한 것은 그대로 쓴다
DUTY_PHRASES = {
    "LLM 서비스 개발": "LLM 기반 서비스 개발",
    "RAG·검색": "RAG 기반 검색 시스템 구축",
    "모델 파인튜닝": "모델 파인튜닝과 성능 개선",
    "MLOps": "MLOps 환경 구축과 운영",
    "데이터 파이프라인": "데이터 파이프라인 설계와 운영",
    "컴퓨터 비전": "컴퓨터 비전 모델 개발",
    "업무 자동화(AX)": "AI 기반 업무 자동화(AX)",
}


# 맡을 일을 비웠을 때(2026-11-03 사용자 결정)의 기본 문구. {job}·{skills} 만 채운다
NO_DUTY_INTRO_TEMPLATES = (
    "저희 부서는 {job} 직무와 함께 서비스를 만들고 개선해 나가고 있습니다.{skills_sentence}",
    "{job} 직무가 속한 저희 부서는 새로운 기술을 실제 업무에 적용하는 일을 중심으로 일합니다.{skills_sentence}",
    "저희 부서에서는 함께 성장하며 서비스를 만들어 갈 {job} 분을 찾고 있습니다.{skills_sentence}",
)

# 직접 입력한 맡을 일이 문장처럼 끝나면 짧은 말로 줄인다: '사내 챗봇을 운영함' → '사내 챗봇 운영'
VERB_ENDINGS = ("합니다", "한다", "해요")
SHORT_ENDINGS = ("하기", "함")  # '결함'·'포함' 같은 두 글자 말은 건드리지 않게 세 글자 이상 낱말에만 쓴다


def tidyDuty(duty: str) -> str:
    text = duty.strip().rstrip(".。").strip()
    if not re.search(r"[가-힣]", text):
        return text
    words = text.split()
    last = words[-1]
    hangulTail = len(re.search(r"[가-힣]*$", last).group(0))  # '버그·결함' 은 '결함' 두 글자만 본다
    for ending in VERB_ENDINGS:
        if last.endswith(ending) and hangulTail > len(ending):
            last = last[: -len(ending)]
            break
    else:
        for ending in SHORT_ENDINGS:
            if last.endswith(ending) and hangulTail >= 3:
                last = last[: -len(ending)]
                break
    if len(words) >= 2 and words[-2][-1] in "을를" and len(words[-2]) >= 3:
        words[-2] = words[-2][:-1]  # '챗봇을 운영' → '챗봇 운영' ('마을' 같은 두 글자 말은 그대로)
    words[-1] = last
    return " ".join(words)


def fallbackIntro(body, jobName: str, template: str | None = None) -> str:
    """메모를 그대로 내보내지 않고 관리자가 고른 맡을 일·기술로만 부서 소개를 만든다. 문구는 기본 문구 중 하나를 고른다."""
    skillsSentence = f" {', '.join(body.skills)} 등의 기술을 활용합니다." if body.skills else ""
    chosen = template or random.choice(INTRO_TEMPLATES if body.duties else NO_DUTY_INTRO_TEMPLATES)
    duties = ", ".join(DUTY_PHRASES.get(duty) or tidyDuty(duty) for duty in body.duties)
    return chosen.format(job=jobName, duties=duties, skills_sentence=skillsSentence)


# 자격 요건·우대 사항은 '~ 분'으로 끝낸다 (2026-11-03 사용자 결정). 4B 모델이 놓친 줄만 고친다 (실측 30개 중 4개가 '~있습니다')
BUN_ENDINGS = (("있어야 합니다", "있는 분"), ("있습니다", "있는 분"), ("입니다", "인 분"))


def unifyBunLines(text: str) -> str:
    lines = []
    for line in text.splitlines():
        body = line.rstrip().rstrip(".").rstrip()
        for ending, replacement in BUN_ENDINGS:
            if body.endswith(ending):
                line = body[: -len(ending)] + replacement
                break
        lines.append(line)
    return "\n".join(lines)


def fillGaps(draft: DraftText, fallback: str) -> DraftText:
    """작은 모델이 부서 소개를 짧게 쓰거나 비우면 실패시키지 않고 fallbackIntro 로 채운다. 자격 요건·우대 사항 끝맺음도 맞춘다."""
    intro = draft.company_intro.strip()
    if len(intro) < INTRO_MIN_LEN and fallback.strip():
        intro = fallback.strip()
    preferred = "" if isDashOnly(draft.preferred) else unifyBunLines(draft.preferred.strip())
    return draft.model_copy(update={"company_intro": intro, "preferred": preferred,
                                    "requirements": unifyBunLines(draft.requirements.strip())})


# ---------- 그래프 (참고 공고 → 초안 → 칸별 검사 → 다시 쓰기) ----------

REFERENCE_LIMIT = 2  # 참고할 예전 공고 수 (같은 직무, 게시·마감, 최근 순)
REFERENCE_MAX_CHARS = 800  # 참고 공고 1건에서 프롬프트에 넣는 글자 수
COPY_WINDOW = 40  # 예전 공고와 이만큼 연속으로 같으면 베낀 것으로 본다 (띄어쓰기 정리 뒤)
REWRITE_LIMIT = 1  # 문제 칸을 다시 쓰는 횟수. 관리자 요청 칸은 요청 1번 + 이만큼 더
REWRITE_TIMEOUT_SEC = 90
SECTIONS = ("title", "company_intro", "duties", "requirements", "preferred")
SECTION_LABEL = {"title": "제목", "company_intro": "부서 소개", "duties": "주요 업무", "requirements": "자격 요건", "preferred": "우대 사항"}
SECTION_RULES = {
    "title": "'직무 (경력 수준)' 형식으로 40자 이내.",
    "company_intro": "부서 소개 2~4문장, 모든 문장을 '~습니다'로 끝낸다. 주어진 정보에 없는 사실은 지어내지 않는다.",
    "duties": "'- '로 시작하는 줄 3~6개, 모든 줄을 '~합니다'로 끝낸다.",
    "requirements": "'- '로 시작하는 줄 3~6개, 모든 줄을 '~ 분'으로 끝낸다.",
    "preferred": "'- '로 시작하는 줄 1~3개, 모든 줄을 '~ 분'으로 끝낸다. 우대 사항이 없으면 빈 문자열.",
}


class SectionText(BaseModel):
    text: str = Field(description="고친 칸의 새 내용만. 다른 칸은 쓰지 않는다")


class DraftState(TypedDict, total=False):
    """체크포인트에 남는 값. 공고 문장과 관리자 입력만 있고 지원자 개인정보는 없다."""
    postingId: str
    prompt: str  # buildPrompt 결과 (관리자 입력)
    fallbackIntro: str
    mode: str  # initial | revise
    references: list[str]
    draft: dict | None  # 칸 이름 → 글
    draftAttempts: int
    problems: dict  # 칸 이름 → 고칠 점 목록 (마지막 check)
    rewrites: dict  # 칸 이름 → 다시 쓴 횟수 (이번 흐름)
    request: dict | None  # 다시 쓰기 요청 {section, note}
    notes: list[str]  # 관리자에게 보여 줄 처리 기록 (이번 흐름)
    error: str | None


def threadId(postingId: str) -> str:
    return f"posting-draft:{postingId}"


def graphConfig(postingId: str) -> dict:
    return {"configurable": {"thread_id": threadId(postingId)}}


def setState(postingId: str, **values) -> None:
    current = drafts.get(postingId) or {"status": "running", "stage": None, "bias_warnings": [], "notes": [], "revision": None, "error": None}
    drafts[postingId] = {**current, **values}


def referenceText(p: JobPosting) -> str:
    return f"제목: {p.title}\n주요 업무:\n{p.duties}\n자격 요건:\n{p.requirements}"[:REFERENCE_MAX_CHARS]


def findReferences(db, posting: JobPosting) -> list[str]:
    """① 같은 직무의 게시·마감 공고. 직무 코드로 정확히 찾으므로 벡터 검색 없이 DB 조회로 충분하다."""
    rows = (db.query(JobPosting)
            .filter(JobPosting.job_code == posting.job_code, JobPosting.id != posting.id, JobPosting.status.in_(("published", "closed")))
            .order_by(JobPosting.published_at.desc()).limit(REFERENCE_LIMIT).all())
    return [referenceText(p) for p in rows]


def fenceText(text: str) -> str:
    """구분 태그를 흉내 내 프롬프트 구조를 깨지 못하게 꺾쇠를 바꾼다."""
    return (text or "").replace("<", "‹").replace(">", "›")


def withReferences(prompt: str, references: list[str]) -> str:
    if not references:
        return prompt
    blocks = "\n".join(f"<참고 {i}>\n{fenceText(r)}\n</참고 {i}>" for i, r in enumerate(references, 1))
    return (f"{prompt}\n\n같은 직무의 예전 공고다. 용어와 문체만 참고하고, 문장을 그대로 옮기지 마라. "
            f"예전 공고에만 있는 사실을 새 공고에 넣지 마라.\n{blocks}")


def normalized(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def copiesReference(text: str, references: list[str]) -> bool:
    t = normalized(text)
    refs = [normalized(r) for r in references]
    return any(t[i:i + COPY_WINDOW] in r for i in range(max(len(t) - COPY_WINDOW + 1, 0)) for r in refs)


def sectionProblems(text: str, references: list[str]) -> list[str]:
    """③ 고쳐 쓰게 할 점: 차별로 보일 수 있는 표현, 예전 공고 베끼기."""
    problems = [f"차별로 보일 수 있는 표현 '{w['text']}'({w['reason']})을 빼라" for w in biasWarnings(text)]
    if references and copiesReference(text, references):
        problems.append("예전 공고 문장을 그대로 옮겼다. 같은 뜻을 새 문장으로 써라")
    return problems


def tidySection(section: str, text: str) -> str | None:
    """다시 쓴 글을 다듬는다. 형식이 나쁘면 None (앞의 글을 그대로 둔다)."""
    text = (text or "").strip()
    if section in ("requirements", "preferred"):
        text = unifyBunLines(text)
    if section == "preferred":
        return "" if isDashOnly(text) else text
    if section == "title":
        return text if 0 < len(text) <= 200 else None
    minimum = INTRO_MIN_LEN if section == "company_intro" else 10
    return text if len(text) >= minimum else None


def rewritePrompt(state: "DraftState", section: str) -> str:
    request = state.get("request") or {}
    lines = [withReferences(state["prompt"], state.get("references", [])), "",
             f"지금 고칠 칸: {SECTION_LABEL[section]}", f"칸 규칙: {SECTION_RULES[section]}",
             f"<지금 내용>\n{fenceText(state['draft'].get(section, ''))}\n</지금 내용>"]
    problems = state.get("problems", {}).get(section)
    if problems:
        lines.append("고칠 점: " + "; ".join(problems))
    if request.get("section") == section and request.get("note"):
        lines.append(f"<관리자 요청>\n{fenceText(request['note'])}\n</관리자 요청>")
    lines.append("이 칸의 새 내용만 text 에 써라. 관리자 요청이 규칙(지어내지 않기·차별 표현 금지)과 어긋나면 규칙을 따른다.")
    return "\n".join(lines)


def rewriteLimit(state: "DraftState", section: str) -> int:
    request = state.get("request") or {}
    return REWRITE_LIMIT + (1 if state.get("mode") == "revise" and request.get("section") == section else 0)


def pendingSections(state: "DraftState") -> list[str]:
    """다시 쓸 칸: 고칠 점이 있고 횟수가 남은 칸. 다시 쓰기 요청 칸은 아직 한 번도 안 썼으면 무조건."""
    rewrites = state.get("rewrites", {})
    pending = [s for s in state.get("problems", {}) if rewrites.get(s, 0) < rewriteLimit(state, s)]
    request = state.get("request") or {}
    if state.get("mode") == "revise" and rewrites.get(request.get("section"), 0) == 0 and request.get("section") not in pending:
        pending.append(request["section"])
    return pending


def buildDraftGraph():
    async def retrieve(state: DraftState) -> dict:
        setState(state["postingId"], stage="retrieve")
        with dbModule.SessionLocal() as db:
            posting = db.get(JobPosting, state["postingId"])
            references = findReferences(db, posting) if posting is not None else []
        notes = [f"같은 직무의 예전 공고 {len(references)}건을 참고했습니다"] if references else []
        return {"references": references, "draft": None, "draftAttempts": 0, "problems": {}, "rewrites": {},
                "request": None, "notes": notes, "error": None}

    async def draft(state: DraftState) -> dict:
        setState(state["postingId"], stage="draft")
        try:
            out = await llm.structured(DraftText, SYSTEM, withReferences(state["prompt"], state.get("references", [])),
                                       timeoutSec=DRAFT_TIMEOUT_SEC, maxTokens=1500, temperature=0.5)
            if not isUsable(out):
                raise llm.LlmError("draft_invalid")
        except llm.LlmError as exc:
            log.info("draft %s attempt %d failed: %s", state["postingId"], state.get("draftAttempts", 0) + 1, exc)
            return {"draft": None, "draftAttempts": state.get("draftAttempts", 0) + 1, "error": str(exc)}
        return {"draft": fillGaps(out, state.get("fallbackIntro", "")).model_dump(), "error": None}

    async def check(state: DraftState) -> dict:
        setState(state["postingId"], stage="check")
        targets = SECTIONS if state.get("mode") != "revise" else (state["request"]["section"],)
        problems = {s: found for s in targets if (found := sectionProblems(state["draft"].get(s, ""), state.get("references", [])))}
        return {"problems": problems}

    async def rewrite(state: DraftState) -> dict:
        setState(state["postingId"], stage="rewrite")
        current, rewrites = dict(state["draft"]), dict(state.get("rewrites", {}))
        notes, error = list(state.get("notes", [])), state.get("error")
        request = state.get("request") or {}
        for section in pendingSections(state):
            rewrites[section] = rewrites.get(section, 0) + 1
            reason = "; ".join(state.get("problems", {}).get(section, [])) or "관리자 요청"
            try:
                out = await llm.structured(SectionText, SYSTEM, rewritePrompt({**state, "draft": current}, section),
                                           timeoutSec=REWRITE_TIMEOUT_SEC, maxTokens=700, temperature=0.3)
            except llm.LlmError as exc:
                log.info("draft %s rewrite %s failed: %s", state["postingId"], section, exc)
                rewrites[section] = rewriteLimit(state, section)  # 서버 문제면 더 돌리지 않는다
                if request.get("section") == section:
                    error = str(exc)
                continue
            text = tidySection(section, out.text)
            if text is None:
                notes.append(f"{SECTION_LABEL[section]}: 다시 쓴 글의 형식이 맞지 않아 앞의 글을 두었습니다")
                continue
            current[section] = text
            notes.append(f"{SECTION_LABEL[section]} 칸을 다시 썼습니다 ({reason})")
        return {"draft": current, "rewrites": rewrites, "notes": notes, "error": error}

    async def save(state: DraftState) -> dict:
        postingId, d = state["postingId"], state["draft"]
        with dbModule.SessionLocal() as db:
            posting = db.get(JobPosting, postingId)
            if posting is None or posting.status != "draft":
                setState(postingId, status="failed", stage=None, error="posting_changed")
                return {}
            posting.title = d["title"].strip()[:200]
            for field in ("company_intro", "duties", "requirements", "preferred"):
                setattr(posting, field, d[field].strip())
            db.commit()
            warnings = biasWarnings(*(getattr(posting, s) or "" for s in SECTIONS))
        setState(postingId, status="done", stage=None, bias_warnings=warnings, notes=state.get("notes", []), revision=None, error=None)
        return {}

    async def deliver(state: DraftState) -> dict:
        """다시 쓴 칸은 DB 에 쓰지 않고 화면에 준다. 관리자가 확인하고 저장한다 (저장하지 않은 수정 글을 덮지 않게)."""
        section = state["request"]["section"]
        if state.get("error"):
            setState(state["postingId"], status="failed", stage=None, revision=None, bias_warnings=[], notes=state.get("notes", []),
                     error=state["error"])
            return {}
        text = state["draft"][section]
        setState(state["postingId"], status="done", stage=None, revision={"section": section, "text": text},
                 bias_warnings=biasWarnings(text), notes=state.get("notes", []), error=None)
        return {}

    async def fail(state: DraftState) -> dict:
        setState(state["postingId"], status="failed", stage=None, bias_warnings=[], error=state.get("error") or "unknown")
        return {}

    def routeStart(state: DraftState) -> str:
        return "rewrite" if state.get("mode") == "revise" else "retrieve"

    def afterDraft(state: DraftState) -> str:
        if state.get("draft"):
            return "check"
        return "draft" if state.get("draftAttempts", 0) < DRAFT_ATTEMPTS else "fail"

    def afterCheck(state: DraftState) -> str:
        if pendingSections(state):
            return "rewrite"
        return "deliver" if state.get("mode") == "revise" else "save"

    g = StateGraph(DraftState)
    for name, node in (("retrieve", retrieve), ("draft", draft), ("check", check), ("rewrite", rewrite),
                       ("save", save), ("deliver", deliver), ("fail", fail)):
        g.add_node(name, node)
    g.add_conditional_edges(START, routeStart, ["retrieve", "rewrite"])
    g.add_edge("retrieve", "draft")
    g.add_conditional_edges("draft", afterDraft, ["check", "draft", "fail"])
    g.add_conditional_edges("check", afterCheck, ["rewrite", "save", "deliver"])
    g.add_edge("rewrite", "check")
    for name in ("save", "deliver", "fail"):
        g.add_edge(name, END)
    return g.compile(checkpointer=checkpoint.saver())


async def generate(postingId: str, prompt: str, fallbackIntro: str = "") -> None:
    """새 초안. 같은 thread 의 예전 기록은 retrieve 가 덮어쓴다."""
    try:
        await buildDraftGraph().ainvoke({"postingId": postingId, "prompt": prompt, "fallbackIntro": fallbackIntro, "mode": "initial"},
                                        graphConfig(postingId))
    except Exception:  # noqa: BLE001 — 예상 못 한 오류도 '실패'로 보여 다시 시도하게 한다
        log.exception("draft %s crashed", postingId)
        setState(postingId, status="failed", stage=None, error="internal")


async def hasDraft(postingId: str) -> bool:
    """다시 쓰기에 쓸 초안 기록(체크포인트)이 있는가."""
    snapshot = await buildDraftGraph().aget_state(graphConfig(postingId))
    return bool(snapshot.values.get("draft"))


async def revise(postingId: str, section: str, note: str, current: str) -> None:
    """④ 관리자가 고른 칸만 다시 쓴다. 처음 입력·참고 공고는 체크포인트에서 이어 쓴다."""
    graph, config = buildDraftGraph(), graphConfig(postingId)
    try:
        snapshot = await graph.aget_state(config)
        draftText = {**snapshot.values["draft"], section: current}
        await graph.ainvoke({"mode": "revise", "request": {"section": section, "note": note}, "draft": draftText,
                             "problems": {}, "rewrites": {}, "notes": [], "error": None}, config)
    except Exception:  # noqa: BLE001
        log.exception("draft %s revise crashed", postingId)
        setState(postingId, status="failed", stage=None, revision=None, error="internal")


def runInBackground(coro) -> None:
    task = asyncio.get_running_loop().create_task(coro)
    tasks.add(task)
    task.add_done_callback(tasks.discard)


def start(postingId: str, prompt: str, fallbackIntro: str = "") -> None:
    drafts[postingId] = {"status": "running", "stage": "retrieve", "bias_warnings": [], "notes": [], "revision": None, "error": None}
    runInBackground(generate(postingId, prompt, fallbackIntro))


def startRevision(postingId: str, section: str, note: str, current: str) -> None:
    setState(postingId, status="running", stage="rewrite", revision=None, bias_warnings=[], notes=[], error=None)
    runInBackground(revise(postingId, section, note, current))


def status(postingId: str, posting: JobPosting) -> dict:
    state = drafts.get(postingId)
    if state is None:
        # 재시작 등으로 진행 기록이 없다: 내용이 채워졌으면 완료, 아니면 실패로 보고 다시 시도하게 한다
        done = bool(posting.title and posting.duties)
        state = {"status": "done" if done else "failed", "error": None if done else "lost", "stage": None, "notes": [], "revision": None,
                 "bias_warnings": biasWarnings(*(getattr(posting, s) or "" for s in SECTIONS)) if done else []}
    return {"status": state["status"], "posting_id": postingId, "stage": state.get("stage"), "bias_warnings": state["bias_warnings"],
            "notes": state.get("notes", []), "revision": state.get("revision"), "error": state["error"]}


