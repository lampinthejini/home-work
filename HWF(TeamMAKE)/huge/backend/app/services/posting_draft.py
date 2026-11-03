"""AI 공고 초안 (S-R02, JOB-02, G-06).

정해진 값(고용 형태·근무지·인원·접수 기간·코딩테스트 여부)은 AI를 거치지 않고 그대로 복사한다.
AI(llm-rt)는 제목·부서 소개(company_intro)·주요 업무·자격 요건·우대 사항 문장만 쓴다. 회사명은 쓰지 않는다 (단일 기업 서비스).
진행 상태는 api 프로세스 안에 둔다 (1단계, 프로세스 1개 기준). 재시작으로 상태가 사라지면 '실패'로 보여 다시 시도하게 한다.
"""

import asyncio
import logging
import random
import re

from pydantic import BaseModel, Field

from .. import db as dbModule
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


drafts: dict[str, dict] = {}  # posting_id → {"status": running|done|failed, "bias_warnings": [...], "error": str|None}
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


async def generate(postingId: str, prompt: str, fallbackIntro: str = "") -> None:
    lastError = "unknown"
    for attempt in range(DRAFT_ATTEMPTS):
        try:
            draft = await llm.structured(DraftText, SYSTEM, prompt, timeoutSec=DRAFT_TIMEOUT_SEC, maxTokens=1500, temperature=0.5)
            if not isUsable(draft):
                raise llm.LlmError("draft_invalid")
            draft = fillGaps(draft, fallbackIntro)
            break
        except llm.LlmError as exc:
            lastError = str(exc)
            log.info("draft %s attempt %d failed: %s", postingId, attempt + 1, exc)
    else:
        drafts[postingId] = {"status": "failed", "bias_warnings": [], "error": lastError}
        return
    with dbModule.SessionLocal() as db:
        posting = db.get(JobPosting, postingId)
        if posting is None or posting.status != "draft":
            drafts[postingId] = {"status": "failed", "bias_warnings": [], "error": "posting_changed"}
            return
        posting.title = draft.title.strip()[:200]
        posting.company_intro = draft.company_intro.strip()
        posting.duties = draft.duties.strip()
        posting.requirements = draft.requirements.strip()
        posting.preferred = draft.preferred.strip()
        db.commit()
        warnings = biasWarnings(posting.title, posting.company_intro, posting.duties, posting.requirements, posting.preferred)
    drafts[postingId] = {"status": "done", "bias_warnings": warnings, "error": None}


def start(postingId: str, prompt: str, fallbackIntro: str = "") -> None:
    drafts[postingId] = {"status": "running", "bias_warnings": [], "error": None}
    task = asyncio.get_running_loop().create_task(generate(postingId, prompt, fallbackIntro))
    tasks.add(task)
    task.add_done_callback(tasks.discard)


def status(postingId: str, posting: JobPosting) -> dict:
    state = drafts.get(postingId)
    if state is None:
        # 재시작 등으로 진행 기록이 없다: 내용이 채워졌으면 완료, 아니면 실패로 보고 다시 시도하게 한다
        done = bool(posting.title and posting.duties)
        state = {"status": "done" if done else "failed", "error": None if done else "lost",
                 "bias_warnings": biasWarnings(posting.title or "", posting.company_intro or "", posting.duties or "",
                                               posting.requirements or "", posting.preferred or "") if done else []}
    return {"status": state["status"], "posting_id": postingId, "bias_warnings": state["bias_warnings"], "error": state["error"]}
