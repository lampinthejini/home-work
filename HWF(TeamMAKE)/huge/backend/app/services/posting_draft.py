"""AI 공고 초안 (S-R02, JOB-02, G-06).

정해진 값(고용 형태·근무지·인원·접수 기간·코딩테스트 여부)은 AI를 거치지 않고 그대로 복사한다.
AI(llm-rt)는 제목·회사 소개·주요 업무·자격 요건·우대 사항 문장만 쓴다. 회사명은 쓰지 않는다 (단일 기업 서비스).
진행 상태는 api 프로세스 안에 둔다 (1단계, 프로세스 1개 기준). 재시작으로 상태가 사라지면 '실패'로 보여 다시 시도하게 한다.
"""

import asyncio
import logging
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
    "규칙: 주어진 정보에 없는 연봉·복지·수치·회사명은 지어내지 않는다. 회사는 '우리 회사' 또는 '저희 팀'으로 부른다. "
    "나이·성별·혼인·외모·출신 지역으로 지원을 제한하는 표현을 쓰지 않는다. "
    "제목은 '직무 (경력 수준)' 형식으로 쓴다. 예: AI/AX 엔지니어 (경력 3년 이상). "
    "주요 업무·자격 요건·우대 사항은 '- '로 시작하는 줄 3~6개로 쓴다. JSON 으로만 답한다."
)


class DraftText(BaseModel):
    title: str = Field(description="공고 제목, 40자 이내. 예: AI/AX 엔지니어 (경력 3년 이상)")
    company_intro: str = Field(description="회사·팀 소개 2~4문장")
    duties: str = Field(description="주요 업무, '- ' 로 시작하는 줄")
    requirements: str = Field(description="자격 요건, '- ' 로 시작하는 줄")
    preferred: str = Field(description="우대 사항, '- ' 로 시작하는 줄. 없으면 빈 문자열")


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
        f"주로 맡을 일: {', '.join(body.duties)}",
        f"필요한 기술: {', '.join(body.skills) or '(지정 없음)'}",
        f"우대 사항 메모: {body.preferred or '(없음)'}",
        f"회사·팀 소개 메모: {body.company_intro}",
        f"지금 회사 상황·강조할 점: {body.emphasis or '(없음)'}",
    ]
    return "아래 정보로 채용 공고 초안을 써라.\n" + "\n".join(lines)


def isUsable(draft: DraftText) -> bool:
    return (0 < len(draft.title.strip()) <= 200 and len(draft.company_intro.strip()) >= 10
            and len(draft.duties.strip()) >= 10 and len(draft.requirements.strip()) >= 10)


async def generate(postingId: str, prompt: str) -> None:
    lastError = "unknown"
    for attempt in range(DRAFT_ATTEMPTS):
        try:
            draft = await llm.structured(DraftText, SYSTEM, prompt, timeoutSec=DRAFT_TIMEOUT_SEC, maxTokens=1500, temperature=0.5)
            if not isUsable(draft):
                raise llm.LlmError("draft_invalid")
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


def start(postingId: str, prompt: str) -> None:
    drafts[postingId] = {"status": "running", "bias_warnings": [], "error": None}
    task = asyncio.get_running_loop().create_task(generate(postingId, prompt))
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
