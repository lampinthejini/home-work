"""질문 자리마다 자료 칸 하나 (2026-11-20 사용자 결정, CONFLICTS C-31 — C-30 '자료 3개까지'는 그대로).

- 회사 자리: 회사 소개·경영 이념·인재상·회사 프로젝트·기술 블로그 최신 글 가운데 무작위 칸, 칸 안에서는 이력서와 가장 가까운 항목.
- 직무 자리: 공고·직무 소개·사내 기술 스택(기술 이름 하나)·AI/AX 가 하는 일·최근 소식 가운데 무작위 칸.
- 같은 면접의 같은 종류 자리는 다른 칸을 먼저, 다시 만들 때는 다른 칸. 질문이 자료를 안 썼으면 다시 만든다(마지막 시도는 받음).
- 자료를 고르는 이력서 조각은 경험 줄 + 자기소개서 전체 (앞부분만 쓰지 않는다).
"""

import asyncio
import math
import random

import pytest

from app.models import Application, CompanyProject
from app.services import question_compose, rag, slot_material
from app.services.slot_material import MaterialPicker, Piece
from tests.test_question_rag import RESUME, composed, fakeVector, makeApplication, world  # noqa: F401 — world 는 pytest fixture


def test_splitPiecesDropsHeadingsAndSplitsLongLines():
    text = "인재상\n- 측정하고 판단하는 사람: 느낌이 아니라 숫자로 말한다.\n" + "가나다라마바사 문장입니다. " * 30
    pieces = slot_material.splitPieces(text)
    assert pieces[0] == "측정하고 판단하는 사람: 느낌이 아니라 숫자로 말한다."
    assert "인재상" not in pieces and len(pieces) > 2 and all(len(p) <= slot_material.PIECE_MAX_CHARS for p in pieces)


def test_stackTermsAreSingleTechNames():
    terms = slot_material.stackTerms("AI 응용: 검색 증강 생성(RAG), LangChain·LangGraph 기반 에이전트\n배포: Docker, Kubernetes")
    assert terms == [("검색 증강 생성(RAG)", "AI 응용"), ("LangChain·LangGraph 기반 에이전트", "AI 응용"),
                     ("Docker", "배포"), ("Kubernetes", "배포")]


def test_groundedNeedsTermOrCloseMeaning():
    stack = Piece("job", "tech_stack", "사내 기술 스택", "검색 증강 생성(RAG) (AI 응용)", term="검색 증강 생성(RAG)")
    assert slot_material.grounded(stack, "RAG 에서 검색 결과가 틀리는 원인은 무엇인가요?", None)[0]
    assert not slot_material.grounded(stack, "모델 과적합을 막는 방법은 무엇인가요?", None)[0]
    talent = Piece("company", "talent", "인재상", "측정하고 판단하는 사람", vector=fakeVector("측정 판단"))
    assert slot_material.grounded(talent, "질문", fakeVector("측정 판단"))[0]
    assert not slot_material.grounded(talent, "질문", fakeVector("전혀 다른 이야기 날씨"))[0]
    assert slot_material.grounded(Piece("company", "intro", "회사 소개", "글"), "질문", None)[0]  # 벡터가 없으면 확인하지 않음



def test_jobMaterialAcceptsFromPointFour():
    """2026-11-23 사용자: 직무 자료는 0.4 까지 받는다 (0.44 에도 괜찮은 질문이 있었다). 회사 자료는 0.5 그대로."""
    near = [0.45, math.sqrt(1 - 0.45 ** 2)]  # 자료 [1, 0] 과 0.45
    far = [0.35, math.sqrt(1 - 0.35 ** 2)]
    job = Piece("job", "jobs_intro", "직무 소개", "사내 문서 검색 비서 개선", vector=[1.0, 0.0])
    company = Piece("company", "intro", "회사 소개", "회사 글", vector=[1.0, 0.0])
    assert slot_material.grounded(job, "질문", near)[0]
    assert not slot_material.grounded(job, "질문", far)[0]
    assert not slot_material.grounded(company, "질문", near)[0]


def test_knowledgeJobSlotSkipsJobIntroWithoutTechName():
    """2026-11-23 사용자: 기술 이름이 없는 직무 소개 줄은 지식형 직무 자리에 주지 않는다 (c37 '정답률이 어떻게 동작하는 원리').
    앞의 직무 이름('AI/AX 엔지니어:')과 AI·AX 같은 낱말은 기술 이름으로 치지 않는다. 상황형 자리는 그대로 받는다."""
    plain = Piece("job", "jobs_intro", "직무 소개", "AI/AX 엔지니어: 정답률·근거 일치율·응답 시간으로 말한다.", vector=[1.0, 0.0])
    aiOnly = Piece("job", "jobs_intro", "직무 소개", "서비스 개발: AI 기능 화면에서는 AI 답이 늦을 때의 동작을 정한다.", vector=[1.0, 0.0])
    named = Piece("job", "jobs_intro", "직무 소개", "AI/AX 엔지니어: 문제 정의 → RAG·에이전트 설계 → 배포 순서로 일한다.", vector=[0.0, 1.0])
    other = Piece("job", "ai_ax_role", "AI/AX 가 하는 일", "AI 결과의 품질을 점검한다.", vector=[1.0, 0.0])
    assert not slot_material.namesTech(plain) and not slot_material.namesTech(aiOnly)
    assert slot_material.namesTech(named) and slot_material.namesTech(other)  # 직무 소개 칸만 본다
    picker = MaterialPicker([plain, aiOnly, named], [[1.0, 0.0]], random.Random(0))
    assert all(picker.pick("job", ["jobs_intro"], 0, needsTech=True) is named for _ in range(10))
    assert picker.pick("job", ["jobs_intro"], 0) in (plain, aiOnly, named)
    onlyPlain = MaterialPicker([plain, other], [[1.0, 0.0]], random.Random(0))
    assert onlyPlain.pick("job", ["jobs_intro", "ai_ax_role"], 0, needsTech=True) is other  # 칸이 비면 다음 칸
    assert question_compose.needsTechName("job", question_compose.KNOWLEDGE_FORMS[0])
    assert not question_compose.needsTechName("job", question_compose.SITUATION_FORMS[0])
    assert not question_compose.needsTechName("company", None)


def pieces():
    return [Piece("company", "talent", "인재상", "가까운 인재상", vector=[1.0, 0.0]),
            Piece("company", "talent", "인재상", "먼 인재상", vector=[0.0, 1.0]),
            Piece("company", "project", "회사가 진행한 프로젝트", "프로젝트", vector=[1.0, 0.0]),
            Piece("company", "post", "회사 기술 블로그 최신 글", "글", vector=[0.0, 1.0])]


def test_pickerPicksAmongClosestToResumeAndSkipsUsed():
    picker = MaterialPicker(pieces(), [[1.0, 0.1]], random.Random(0))
    first = picker.pick("company", ["talent"], 0)
    picker.markUsed(first)
    assert picker.pick("company", ["talent"], 0).text != first.text  # 쓴 것은 빼고
    assert picker.pick("company", ["talent", "project"], 1).field == "project"  # 다시 만들 때는 다음 칸
    assert picker.pick("company", ["intro", "post"], 0).field == "post"  # 빈 칸은 건너뜀


def test_fieldOrderPutsUnusedFieldsFirst():
    picker = MaterialPicker(pieces(), [], random.Random(1))
    picker.markUsed(pieces()[0])
    order = picker.fieldOrder("company")
    assert sorted(order) == ["post", "project", "talent"] and order[-1] == "talent"


def companyFields(prompts):
    return [p.split("<회사>\n")[1].split("\n")[1] for p in prompts]


def test_companyPromptGetsOnePieceNotWholeProfile(sessionFactory, world):  # noqa: F811
    fake = world()
    appId = makeApplication(sessionFactory)
    asyncio.run(question_compose.compose(appId))
    assert len(composed(sessionFactory, appId)) == 10
    for prompt in (p for p in fake.prompts if p.startswith("[만들 질문] 회사")):
        info = prompt.split("<회사>\n")[1].split("\n</회사>")[0]
        assert info.startswith("회사 이름: AIIT\n칸: ") and len(info.splitlines()) == 3  # 이름 · 칸 · 항목 하나
        assert "자료에 없는 일반적인 회사 이야기" in prompt


def test_jobPromptTopicComesFromPieces(sessionFactory, world):  # noqa: F811
    fake = world()
    appId = makeApplication(sessionFactory)
    asyncio.run(question_compose.compose(appId))
    with sessionFactory() as db:
        posting = db.get(Application, appId).posting
        texts = [p.text for p in slot_material.jobPieces(db, question_compose.jobTopics(posting, RESUME), [], posting.title)]
    jobPrompts = [p for p in fake.prompts if p.startswith("[만들 질문] 직무")]
    topics = [p.split("이번 질문의 기술 주제: ")[1].split(" — 이 주제만")[0] for p in jobPrompts]
    assert len(topics) == 4 and len(set(topics)) == 4
    assert all(any(t in topic for t in texts) for topic in topics)


def test_unusedMaterialRetriesWithAnotherFieldAndLastTryIsKept(sessionFactory, world, monkeypatch):  # noqa: F811
    fake = world()
    monkeypatch.setattr(slot_material, "grounded", lambda piece, question, vector: (False, 0.1))  # 늘 자료를 안 씀
    with sessionFactory() as db:  # 칸 3개 (인재상은 2026-11-22 부터 회사 자료가 아니라 회사 소개·경영 이념뿐이라 프로젝트를 더한다)
        db.add(CompanyProject(title="쇼핑 AI 에이전트", period="2025", summary="상품을 대신 찾아 주는 에이전트"))
        db.commit()
    appId = makeApplication(sessionFactory)
    asyncio.run(question_compose.compose(appId))
    rows = composed(sessionFactory, appId)
    companyPrompts = [p for p in fake.prompts if p.startswith("[만들 질문] 회사")]
    firstSlot = companyFields(companyPrompts[:3])
    assert len(set(firstSlot)) == 3  # 다시 만들 때마다 다른 칸
    assert "주어진 자료" in companyPrompts[1]  # 문제를 알려 준다
    assert all(r.source == "generated" for r in rows if r.qtype in ("company", "job"))  # 마지막 시도는 받는다


def test_projectsBecomeCompanyPieces(sessionFactory):
    with sessionFactory() as db:
        db.add(CompanyProject(title="쇼핑 AI 에이전트", period="2025", summary="상품을 대신 찾아 주는 에이전트"))
        db.commit()
        texts = [p.text for p in slot_material.companyPieces(db) if p.field == "project"]
    assert texts == ["쇼핑 AI 에이전트 (2025): 상품을 대신 찾아 주는 에이전트"]


@pytest.mark.parametrize("length", [300, 3000])  # 짧은 글(CoverIndex 가 나누지 않음)과 긴 글
def test_resumeChunksCoverWholeCoverLetter(sessionFactory, world, monkeypatch, length):  # noqa: F811
    """자기소개서 앞부분만 쓰지 않는다: 짧든 길든 전체를 조각으로 나눠 모두 임베딩한다 (사용자 2026-11-20)."""
    fake = world()
    embedded: list[str] = []
    original = fake.embed

    async def spyEmbed(texts, timeoutSec=10):
        embedded.extend(texts)
        return await original(texts, timeoutSec)
    monkeypatch.setattr(rag, "embed", spyEmbed)
    cover = "앞부분 지원 동기.\n" + "중간 문단입니다.\n" * (length // 9) + "끝부분에만 쓴 물류 최적화 경험"
    appId = makeApplication(sessionFactory)
    with sessionFactory() as db:
        app = db.get(Application, appId)
        app.resume_snapshot = {**RESUME, "cover_letter": cover}
        db.commit()
    asyncio.run(question_compose.compose(appId))
    assert any("끝부분에만 쓴 물류 최적화 경험" in t for t in embedded)
    assert all(len(t) <= question_compose.COVER_CHUNK_CHARS for t in embedded if "중간 문단" in t)


def test_embedPiecesSendsAtMostOneBatchAtATime(monkeypatch):
    """embed 서버는 한 번에 64개까지 받는다 (실측 2026-11-20: 자료 항목 90여 개를 한 번에 보내 422)."""
    sizes = []

    async def embed(texts, timeoutSec=10):
        sizes.append(len(texts))
        return [fakeVector(t) for t in texts]
    monkeypatch.setattr(rag, "embed", embed)
    slot_material._vectorCache.clear()
    items = [Piece("job", "tech_stack", "사내 기술 스택", f"기술 {i}", term=f"기술 {i}") for i in range(100)]
    asyncio.run(slot_material.embedPieces(items))
    assert max(sizes) <= slot_material.EMBED_BATCH and all(p.vector for p in items)


def test_pickerSkipsPiecesCloseToEarlierQuestions():
    """실측 2026-11-20: 이력서와 가장 가까운 항목만 고르니 RAG 지원자의 직무 칸마다 RAG 항목 → 앞 질문과 비슷해 다시 만들기."""
    items = [Piece("job", "tech_stack", "사내 기술 스택", "RAG", term="RAG", vector=[1.0, 0.0]),
             Piece("job", "tech_stack", "사내 기술 스택", "Kafka", term="Kafka", vector=[0.0, 1.0])]
    picker = MaterialPicker(items, [[1.0, 0.0]], random.Random(0))
    assert picker.pick("job", ["tech_stack"], 0, avoid=[[0.99, 0.05]]).text == "Kafka"  # 앞 질문이 RAG 를 물었다
    assert picker.pick("job", ["tech_stack"], 0, avoid=[[0.99, 0.05], [0.05, 0.99]]) is not None  # 다 가까우면 원래대로 고른다


def test_jobsIntroKeepsOnlyThePostingJobLine():
    """실측 2026-11-20: 직무 소개의 다른 직무 줄('데이터·검색', '서비스 개발')이 AI/AX 공고의 직무 주제로 뽑힘."""
    intro = ("- 서비스 개발: 검색·쇼핑 서비스의 백엔드를 만든다.\n- 데이터·검색: 검색 결과 순서를 정하는 모델을 만든다.\n"
             "- AI/AX 엔지니어: RAG·에이전트 설계와 평가 데이터셋으로 품질 측정.")
    assert slot_material.jobLines(intro, "[모의] AI/AX 엔지니어 (신입·경력)") == ["AI/AX 엔지니어: RAG·에이전트 설계와 평가 데이터셋으로 품질 측정."]
    assert len(slot_material.jobLines(intro, "마케터")) == 3  # 맞는 직무가 없으면 모두


def test_jobsIntroLineIsSplitIntoSentences():
    """실측 2026-11-20 c31b: 이 공고 직무 줄 하나가 직무 주제로 30번 → 문장·'~며,' 마디로 나누고 직무 이름을 붙인다."""
    intro = ("- 서비스 개발: 검색·쇼핑 서비스의 백엔드를 만든다.\n"
             "- AI/AX 엔지니어: AIIT-X를 비롯한 AI 기술로 사용자와 임직원의 문제를 푼다. 문제 정의 → 데이터 수집 → RAG·에이전트 설계 "
             "순서로 일하며, 정답률·근거 일치율·응답 시간으로 말한다.")
    assert slot_material.jobLines(intro, "AI/AX 엔지니어") == [
        "AI/AX 엔지니어: AIIT-X를 비롯한 AI 기술로 사용자와 임직원의 문제를 푼다.",
        "AI/AX 엔지니어: 문제 정의 → 데이터 수집 → RAG·에이전트 설계 순서로 일하며",
        "AI/AX 엔지니어: 정답률·근거 일치율·응답 시간으로 말한다.",
    ]


def test_pickerPicksRandomlyAmongTopThreeClosest():
    """사용자 2026-11-20: 가장 가까운 것 하나만 고르니 지원자마다 같은 글(흩어진 행동을 연결하다 10번) → 가까운 위 3개 중 무작위."""
    items = [Piece("company", "post", "글", f"글 {i}", vector=[1.0, i / 10]) for i in range(6)]
    picked = {MaterialPicker(items, [[1.0, 0.0]], random.Random(seed)).pick("company", ["post"], 0).text for seed in range(40)}
    assert picked == {"글 0", "글 1", "글 2"}


def test_newsWithoutTechNameIsDropped(sessionFactory):
    """실측 2026-11-20: '변호사에게 중요한 건 AI보다…' 같은 소식이 직무 주제로 8번. 공고와의 유사도는 0.36~0.48 로 갈리지 않음
    → 제목에 기술 이름(사내 기술 스택·AI 기술 낱말)이 있는 소식만 쓰고, 그 이름이 질문에 들어가야 한다."""
    from app.services.job_news import JobNews
    news = [JobNews("변호사에게 중요한 건 AI보다 한 걸음 더 나아가는 것"), JobNews("국산 LLM과 NPU로 AI 추론 실증"),
            JobNews("vLLM 으로 서빙 비용 절반")]
    with sessionFactory() as db:
        got = [p for p in slot_material.jobPieces(db, [], news) if p.field == "news"]
    assert [p.text for p in got] == ["국산 LLM과 NPU로 AI 추론 실증", "vLLM 으로 서빙 비용 절반"]
    assert got[0].term == "LLM" and got[1].term == "vLLM"


def test_pairedDifferenceFromOneLineIsCaught():
    """실측 2026-11-20 불량 B1 4번: 'RAG와 사내 문서 검색으로 …' 한 줄의 두 말을 'RAG와 사내 문서 검색 기술의 차이' 로 물음."""
    pieces = [Piece("job", "ai_ax_role", "AI/AX 가 하는 일", "RAG와 사내 문서 검색으로 임직원의 반복 업무를 줄인다."),
              Piece("job", "news", "최근 소식", "국산 LLM과 NPU로 AI 추론 실증", term="추론")]
    assert slot_material.pairedDifference(pieces, "RAG와 사내 문서 검색 기술의 차이는 무엇인가요?")
    assert slot_material.pairedDifference(pieces, "RAG 와 사내 문서 검색 간의 차이점을 설명해 주세요.")
    assert not slot_material.pairedDifference(pieces, "RAG와 미세 조정의 차이는 무엇인가요?")  # 자료에 없는 쪽과 비교는 괜찮음
    assert not slot_material.pairedDifference(pieces, "RAG로 사내 문서를 찾을 때 틀리는 원인은 무엇인가요?")
    assert not slot_material.pairedDifference([], "RAG와 사내 문서 검색의 차이는?")


def test_pairedDifferenceLooksAtEveryPieceNotOnlyTheGivenOne():
    """실측 2026-11-20 c31b: 소식 '추론' 을 받은 자리가 AI/AX 줄의 두 말을 비교해 빠져나감 → 모든 자료 줄과 비교."""
    pieces = [Piece("job", "news", "최근 소식", "국산 LLM과 NPU로 AI 추론 실증", term="추론"),
              Piece("job", "ai_ax_role", "AI/AX 가 하는 일", "RAG와 사내 문서 검색으로 임직원의 반복 업무를 줄인다.")]
    assert slot_material.pairedDifference(
        pieces, "추론에서 RAG와 사내 문서 검색을 사용할 때 각각의 정보 활용 방식의 차이는 무엇인가요?")


def test_pairedDifferenceAllowsListedDifferentThings():
    """쉼표·가운뎃점으로 늘어놓은 서로 다른 것의 차이는 틀린 전제가 아니다 (c31b 팀 이름, c31c '정답률·근거 일치율' 2번 잘못 막음).
    두 말이 '와·과'로 붙은 것만 막는다."""
    pieces = [Piece("job", "ai_ax_role", "AI/AX 가 하는 일", "AI/AX 본부: AIIT-X 모델팀, 생성형 서비스팀, AX 추진팀, MLOps·플랫폼팀."),
              Piece("job", "jobs_intro", "직무 소개", "AI/AX 엔지니어: 정답률·근거 일치율·응답 시간으로 말한다.")]
    assert not slot_material.pairedDifference(pieces, "AIIT-X 모델팀과 AX 추진팀의 역할 차이를 어떻게 생각하시나요?")
    assert not slot_material.pairedDifference(pieces, "MLOps와 플랫폼의 차이는 무엇인가요?")
    assert not slot_material.pairedDifference(pieces, "정답률과 근거 일치율의 차이를 어떻게 이해하시나요?")
    listed = [Piece("company", "project", "회사 프로젝트", "품질은 기능별 평가 데이터셋의 정답률과 근거 일치율, 안전성은 편향 질문 800개로 잰다.")]
    assert not slot_material.pairedDifference(listed, "정답률과 근거 일치율의 차이는 무엇인가요?")  # 나란히 둔 서로 다른 지표


def test_pairedDifferenceCatchesReversedForm():
    """c31c: 'RAG 기술이 사내 문서 검색과 차이를 가지는 이유' 처럼 'A이 B과 차이' 꼴이 검사를 빠져나감."""
    pieces = [Piece("job", "ai_ax_role", "AI/AX 가 하는 일", "RAG와 사내 문서 검색으로 임직원의 반복 업무를 줄인다.")]
    assert slot_material.pairedDifference(pieces, "RAG 기술이 사내 문서 검색과 차이를 가지는 이유는 무엇인가요?")
    assert slot_material.pairedDifference(pieces, "RAG가 사내 문서 검색과의 차이는 무엇인가요?")
    assert not slot_material.pairedDifference(pieces, "RAG가 미세 조정과 차이를 가지는 이유는 무엇인가요?")


def test_pairedDifferenceIsRetriedNotKept(sessionFactory, world, monkeypatch):  # noqa: F811
    """한 줄 두 말 '차이' 질문은 틀린 전제라 마지막 시도에도 받지 않는다 (예비 질문으로)."""
    world()
    monkeypatch.setattr(slot_material, "pairedDifference", lambda pieces, question: True)
    appId = makeApplication(sessionFactory)
    asyncio.run(question_compose.compose(appId))
    rows = [r for r in composed(sessionFactory, appId) if r.qtype in ("job", "company")]
    assert rows and all(r.source != "generated" for r in rows)
