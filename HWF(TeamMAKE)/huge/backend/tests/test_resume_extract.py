import asyncio

import fitz
import pytest

from app.models import ResumeUpload, User
from app.services import resume_extract as rx


def makePdf(lines: list[str]) -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    for i, line in enumerate(lines):
        page.insert_text((72, 72 + i * 24), line, fontname="korea", fontsize=12)
    return doc.tobytes()


def test_isReadable():
    assert rx.isReadable("성명 홍길동 한국대학교 컴퓨터공학과 가나다전자 연구원 Python PyTorch LangChain 2019-03 2024-06")
    assert not rx.isReadable("이력서")  # 글자가 너무 적음
    assert not rx.isReadable("(cid:12)(cid:34) " * 20 + "가나다라마바사아자차카타파하" * 4)  # 글꼴 깨짐
    assert not rx.isReadable("ÇÑ±¹ÀÎ ¸íºÎ " * 10)  # 라틴-1 깨짐


def test_readPagesUsesReaderThenMarksBlankPage():
    doc = fitz.open(stream=makePdf(["성명: 홍길동", "학력: 한국대학교 컴퓨터공학과 학사 2015-03 ~ 2019-02", "기술: Python PyTorch LangChain"]))
    doc.new_page()  # 글자 없는 쪽 (스캔 쪽처럼)
    pages = asyncio.run(rx.readPages(doc.tobytes()))
    assert [p.source for p in pages] == ["pymupdf", "none"]
    assert "홍길동" in pages[0].text
    assert asyncio.run(rx.countPages(doc.tobytes(), "application/pdf"))[:2] == (1, 1)


def test_imageNeedsOcr():
    assert asyncio.run(rx.countPages(b"\x89PNG", "image/png")) == (0, 1, "")


def test_missingFields():
    assert rx.missingFields({"name": "", "education": [], "career": []}) == ["name", "education_or_career"]
    assert rx.missingFields({"name": "홍길동", "education": [], "career": [{"company": "가나다"}]}) == []


def test_fillBlanksKeepsReadValues():
    base = {"name": "", "education": [], "skills": ["Python"]}
    extra = {"name": "홍길동", "education": [{"school": "한국대학교"}], "skills": ["Java"]}
    assert rx.fillBlanks(base, extra) == {"name": "홍길동", "education": [{"school": "한국대학교"}], "skills": ["Python"]}


def test_lowConfidenceFields():
    resume = {"name": "홍길동", "career": [{"company": "가나다전자", "role": "연구원"}]}
    lines = [{"text": "성명: 홍길동", "conf": 0.95}, {"text": "가나다전자 연구원", "conf": 0.6}]
    assert rx.lowConfidenceFields(resume, lines) == ["career[0].company", "career[0].role"]


def test_splitResult():
    resume, meta = rx.splitResult({"name": "홍길동", "_ocr": {"confidence": 0.9, "low_conf_fields": []}})
    assert resume == {"name": "홍길동"} and meta["confidence"] == 0.9
    assert rx.splitResult(None) == (None, {})


def runFlow(sessionFactory, monkeypatch, data: bytes, contentType: str, llmAnswers: list[dict], ocrOk: bool = True, ocrConf: float = 0.7):
    """저장소·OCR·LLM 을 가짜로 바꿔 runExtraction 한 번을 돌리고 (업로드 행, OCR 한 쪽 번호, LLM 에 넘긴 글) 을 돌려준다."""
    import asyncio

    from app.models import ResumeUpload, User
    from app.services import llm, storage

    ocred, prompts = [], []
    monkeypatch.setattr(storage, "getObject", lambda key: (data, contentType))

    async def fakeOcr(image: bytes) -> dict:
        if not ocrOk:
            raise rx.OcrError("down")
        ocred.append(len(ocred) + 1)
        return {"text": "성명: 홍길동", "lines": [{"text": "성명: 홍길동", "conf": ocrConf}], "confidence": ocrConf}

    async def fakeStructured(schema, system, user, timeoutSec, maxTokens=400, temperature=0.4):
        prompts.append(user)
        return schema(**llmAnswers[min(len(prompts), len(llmAnswers)) - 1])

    monkeypatch.setattr(rx, "ocrImage", fakeOcr)
    monkeypatch.setattr(llm, "structured", fakeStructured)
    with sessionFactory() as db:
        user = User(email="kim@example.com", password_hash="x", name="김", role="applicant")
        db.add(user)
        db.flush()
        upload = ResumeUpload(user_id=user.id, file_key="k", file_name="r", content_type=contentType, estimated_seconds=30)
        db.add(upload)
        db.commit()
        uploadId = upload.id
    asyncio.run(rx.runExtraction(uploadId))
    with sessionFactory() as db:
        return db.get(ResumeUpload, uploadId), ocred, prompts


PNG_HEAD = bytes([0x89]) + b"PNG"
TEXT_LINES = ["학력: 한국대학교 컴퓨터공학과 학사 2015-03 ~ 2019-02", "경력: 가나다전자 AI연구소 연구원 2019-03 ~ 2024-06", "기술: Python PyTorch LangChain"]


def test_textPdfSkipsOcr(sessionFactory, monkeypatch):
    answer = {"name": "홍길동", "education": [{"school": "한국대학교"}]}
    upload, ocred, _ = runFlow(sessionFactory, monkeypatch, makePdf(["성명: 홍길동", *TEXT_LINES]), "application/pdf", [answer])
    assert upload.stage == "done" and upload.method == "text" and ocred == []
    assert upload.result["_ocr"] == {"confidence": None, "low_conf_fields": []}


def test_blankNameIsFilledByOcrWithoutOverwriting(sessionFactory, monkeypatch):
    first = {"name": "", "education": [{"school": "한국대학교"}]}
    second = {"name": "홍길동", "education": [{"school": "잘못 읽은 학교"}]}
    upload, ocred, prompts = runFlow(sessionFactory, monkeypatch, makePdf(TEXT_LINES), "application/pdf", [first, second])
    assert upload.stage == "done" and upload.method == "mixed" and ocred == [1]
    assert upload.result["name"] == "홍길동"
    assert upload.result["education"] == [{"school": "한국대학교", "major": "", "degree": "", "start": "", "end": ""}]
    assert upload.result["_ocr"]["low_conf_fields"] == ["name"]
    assert len(prompts) == 2


def test_photoUsesOcr(sessionFactory, monkeypatch):
    upload, ocred, _ = runFlow(sessionFactory, monkeypatch, b"\x89PNG", "image/png", [{"name": "홍길동", "career": [{"company": "가나다"}]}])
    assert upload.stage == "done" and upload.method == "ocr" and ocred == [1]
    assert upload.result["_ocr"]["confidence"] == 0.7


def test_photoWithOcrDownSaysOcrFailed(sessionFactory, monkeypatch):
    upload, _, _ = runFlow(sessionFactory, monkeypatch, b"\x89PNG", "image/png", [{}], ocrOk=False)
    assert upload.stage == "failed" and upload.fail_reason == "OCR_FAILED"



def test_lowConfidenceOcrFails(sessionFactory, monkeypatch):
    upload, _, _ = runFlow(sessionFactory, monkeypatch, PNG_HEAD, "image/png", [{}], ocrConf=0.3)
    assert upload.stage == "failed" and upload.fail_reason == "LOW_CONFIDENCE"


def test_tidyTextJoinsSplitDateRanges():
    text = "2012년 3월 ~      학력사항 서울과학기술대학교  문예창작학과\n\n   2025년 8월\n2009년 3월 ~ 2012년\n잠실고등학교 졸업\n2월"
    assert rx.tidyText(text).splitlines() == [
        "2012년 3월 ~ 2025년 8월 학력사항 서울과학기술대학교 문예창작학과",
        "2009년 3월 ~ 2012년 2월",
        "잠실고등학교 졸업",
    ]


def test_tidyTextKeepsCompleteRanges():
    assert rx.tidyText("2019년 7월 ~ 2025년 9월 가나다전자\n2026년 4월 운전면허") == "2019년 7월 ~ 2025년 9월 가나다전자\n2026년 4월 운전면허"


def test_splitCoverLetterKeepsOriginalText():
    body, cover = rx.splitCoverLetter("성명 홍길동\n자기소개서\n지원동기 저는 꾸준히\n배워 왔습니다.\n입사 후 포부")
    assert body == "성명 홍길동\n"
    assert cover == "지원동기 저는 꾸준히 배워 왔습니다.\n입사 후 포부"
    assert rx.splitCoverLetter("성명 홍길동") == ("성명 홍길동", "")


def test_cleanResult():
    resume = {"name": "홍 길 동", "projects": [{"name": "<프로젝트명>", "period": ""}, {"name": "AI 면접", "period": "2026.10"},
                                               {"name": "주제", "period": "2026년 00월 00일 ~"}],
              "education": [{"school": "잠실고등학교", "major": "졸업"}]}
    cleaned = rx.cleanResult(resume)
    assert cleaned["name"] == "홍길동"
    assert [p["name"] for p in cleaned["projects"]] == ["AI 면접"]
    assert cleaned["education"][0]["major"] == ""
    assert rx.cleanResult({"name": "John Smith", "projects": [], "education": []})["name"] == "John Smith"


@pytest.mark.parametrize("stage", ["uploaded", "checking", "ocr", "structuring"])
def test_restartFailsUnfinishedUpload(sessionFactory, monkeypatch, stage):
    """추출은 api 프로세스 안의 작업이라 재시작하면 사라진다. 화면이 '처리 중'에 남지 않게 실패로 바꾼다 (논의사항 E3)."""
    from app import main

    monkeypatch.setattr(main, "SessionLocal", sessionFactory)
    uploadId = saveUpload(sessionFactory, stage)
    main.recoverAfterRestart()
    with sessionFactory() as db:
        upload = db.get(ResumeUpload, uploadId)
        assert (upload.stage, upload.fail_reason) == ("failed", "INTERNAL")
        assert upload.finished_at is not None


@pytest.mark.parametrize("stage", ["done", "failed", "cancelled"])
def test_restartKeepsFinishedUpload(sessionFactory, monkeypatch, stage):
    from app import main

    monkeypatch.setattr(main, "SessionLocal", sessionFactory)
    uploadId = saveUpload(sessionFactory, stage)
    main.recoverAfterRestart()
    with sessionFactory() as db:
        upload = db.get(ResumeUpload, uploadId)
        assert (upload.stage, upload.fail_reason, upload.finished_at) == (stage, None, None)


def saveUpload(sessionFactory, stage: str) -> str:
    with sessionFactory() as db:
        user = User(email=f"{stage}@example.com", password_hash="x", name="김", role="applicant")
        db.add(user)
        db.flush()
        upload = ResumeUpload(user_id=user.id, file_key="k", file_name="r", content_type="application/pdf", stage=stage)
        db.add(upload)
        db.commit()
        return upload.id
