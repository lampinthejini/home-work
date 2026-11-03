"""개발자 확인 명령 (python -m app.devtools): DB 의 암호화 칸을 서버 안에서만 풀어 본다 (2026-11-02 사용자 요청)."""

from test_evaluation import makeApplication

from app import devtools
from app.crypto import encryptText
from app.models import Answer, InterviewQuestion


def test_decryptTextToken():
    assert devtools.decryptValue(encryptText("안녕하세요")) == "안녕하세요"


def test_decryptJsonTokenIsPrettyPrinted():
    token = encryptText('{"school": "한국대학교", "major": "컴퓨터공학"}')
    out = devtools.decryptValue(token)
    assert '"school": "한국대학교"' in out and "\n" in out


def test_decryptBadTokenSaysWhy():
    assert devtools.decryptValue("not-a-token").startswith("풀 수 없습니다")


def test_answersListsQuestionAndTranscript(sessionFactory):
    appId = makeApplication(sessionFactory)
    with sessionFactory() as db:
        q = InterviewQuestion(application_id=appId, seq=99, qtype="job", text="RAG 를 설명해 주세요")
        db.add(q)
        db.flush()
        db.add(Answer(application_id=appId, interview_question_id=q.id, transcript="검색해서 답을 만듭니다"))
        db.commit()
        out = devtools.answersText(db, appId)
    assert "99. [job] RAG 를 설명해 주세요" in out
    assert "검색해서 답을 만듭니다" in out


def test_fieldReadsAndDecryptsByTableColumnId(sessionFactory):
    """긴 암호문을 복사하지 않아도 표·칸·ID 로 바로 푼다."""
    appId = makeApplication(sessionFactory)
    with sessionFactory() as db:
        q = InterviewQuestion(application_id=appId, seq=98, qtype="job", text="질문")
        db.add(q)
        db.flush()
        answer = Answer(application_id=appId, interview_question_id=q.id, transcript="제 답변입니다")
        db.add(answer)
        db.commit()
        assert devtools.fieldText(db, "answers", "transcript", answer.id) == "제 답변입니다"
        assert devtools.fieldText(db, "answers", "transcript", "없는-id").startswith("찾을 수 없습니다")
        assert devtools.fieldText(db, "nope", "transcript", answer.id).startswith("표 이름")


def test_badBase64SaysCopyProblem():
    assert "복사" in devtools.decryptValue("abc")


def test_plainRowsDecryptEncryptedColumns(sessionFactory):
    """DBeaver 용 평문 사본: 암호화 칸이 있는 표만, 모든 칸을 글자로 (2026-11-02 사용자 요청, 개발 환경 전용)."""
    appId = makeApplication(sessionFactory)
    with sessionFactory() as db:
        q = InterviewQuestion(application_id=appId, seq=97, qtype="job", text="질문")
        db.add(q)
        db.flush()
        db.add(Answer(application_id=appId, interview_question_id=q.id, transcript="평문 답변", words=[{"word": "평문"}]))
        db.commit()
        tables = devtools.plainRows(db)
    assert "answers" in tables and "job_postings" not in tables  # 암호화 칸이 없는 표는 원본을 보면 된다
    columns, rows = tables["answers"]
    row = next(r for r in (dict(zip(columns, values, strict=True)) for values in rows) if r["transcript"] == "평문 답변")
    assert row["transcript"] == "평문 답변" and '"word": "평문"' in row["words"]
    assert row["application_id"] == appId


def test_plainRefusesOutsideDev(monkeypatch):
    from dataclasses import replace

    monkeypatch.setattr(devtools, "ENV", replace(devtools.ENV, profile="prod"))
    assert devtools.makePlain(None).startswith("개발 환경")
