"""개발자 확인 명령. DB 의 암호화 칸(답변·이력서·판정 근거 등)을 서버 안에서만 풀어 본다.

  python -m app.devtools field <표> <칸> <id>      DB 에서 바로 읽어 푼다. 예: field answers transcript <answers.id>
  python -m app.devtools decrypt <암호문>          DBeaver 등에서 복사한 칸 값 하나를 푼다
  python -m app.devtools answers <application_id>  지원 건의 질문과 답변 글을 순서대로 보여 준다
  python -m app.devtools plain                     DBeaver 용 평문 사본을 dev_plain 스키마에 만든다 (개발 환경 전용)
  python -m app.devtools unplain                   평문 사본을 지운다 (다 보면 꼭 지운다)

열쇠(APP_ENCRYPTION_KEY)는 컨테이너 안에만 있으므로 docker exec 로만 쓸 수 있다.
지원자 개인정보가 화면에 그대로 나오니 개발 확인에만 쓰고, 출력을 파일·메신저로 옮기지 않는다.
"""

import binascii
import json
import sys

from cryptography.exceptions import InvalidTag
from sqlalchemy import text

from .config import ENV
from .crypto import EncryptedJson, EncryptedText, decryptText
from .db import Base, SessionLocal, engine
from .models import Answer, InterviewQuestion


def pretty(value) -> str:
    if value is None:
        return "(비어 있음)"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, indent=2)
    return str(value)


def fieldText(db, table: str, column: str, rowId: str) -> str:
    """표 이름과 ID 로 한 줄을 읽는다. 암호화 칸은 앱의 칸 타입이 읽을 때 자동으로 푼다."""
    model = next((m.class_ for m in Base.registry.mappers if m.class_.__tablename__ == table), None)
    if model is None:
        return f"표 이름을 확인해 주세요: {table}"
    if column not in model.__table__.columns:
        return f"칸 이름을 확인해 주세요: {table}.{column}"
    row = db.get(model, rowId)
    if row is None:
        return f"찾을 수 없습니다: {table} id={rowId}"
    return pretty(getattr(row, column))


def decryptValue(token: str) -> str:
    try:
        plain = decryptText(token.strip())
    except (binascii.Error, ValueError):
        return "풀 수 없습니다: 암호문 모양이 아닙니다. 값이 잘리거나 다른 글자가 섞여 복사된 것 같습니다 (field 명령을 쓰면 복사가 필요 없습니다)"
    except InvalidTag:
        return "풀 수 없습니다: 열쇠가 맞지 않습니다. 다른 서버·다른 열쇠로 암호화된 값입니다"
    try:
        return json.dumps(json.loads(plain), ensure_ascii=False, indent=2)
    except ValueError:
        return plain


def answersText(db, applicationId: str) -> str:
    rows = (db.query(InterviewQuestion, Answer).outerjoin(Answer, Answer.interview_question_id == InterviewQuestion.id)
            .filter(InterviewQuestion.application_id == applicationId)
            .order_by(InterviewQuestion.seq, InterviewQuestion.answer_order).all())
    if not rows:
        return "질문이 없습니다 (지원 ID 를 확인해 주세요)"
    lines = []
    for q, a in rows:
        follow = " (꼬리질문)" if q.kind == "follow_up" else ""
        lines.append(f"{q.seq}. [{q.qtype}]{follow} {q.text}")
        lines.append(f"   → {a.transcript if a and a.transcript else '(답변 없음)'}")
    return "\n".join(lines)


PLAIN_SCHEMA = "dev_plain"


def encryptedModels() -> list:
    return sorted((m.class_ for m in Base.registry.mappers
                   if any(isinstance(c.type, (EncryptedText, EncryptedJson)) for c in m.class_.__table__.columns)),
                  key=lambda model: model.__tablename__)


def asText(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, indent=2)
    return str(value)


def plainRows(db) -> dict[str, tuple[list[str], list[list]]]:
    """암호화 칸이 있는 표마다 (칸 이름들, 줄들). 앱의 칸 타입이 읽을 때 풀어 주므로 모든 값이 평문이다."""
    tables = {}
    for model in encryptedModels():
        columns = [c.name for c in model.__table__.columns]
        attrs = [model.__mapper__.get_property_by_column(c).key for c in model.__table__.columns]
        rows = [[asText(getattr(row, a)) for a in attrs] for row in db.query(model).all()]
        tables[model.__tablename__] = (columns, rows)
    return tables


def makePlain(db) -> str:
    """dev_plain 스키마에 평문 사본 표를 새로 만든다. 지금 시점의 사본이라 원본이 바뀌면 다시 돌린다."""
    if ENV.profile != "dev":
        return "개발 환경(APP_PROFILE=dev)에서만 만들 수 있습니다"
    tables = plainRows(db)
    with engine.begin() as conn:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {PLAIN_SCHEMA} CASCADE"))
        conn.execute(text(f"CREATE SCHEMA {PLAIN_SCHEMA}"))
        for name, (columns, rows) in tables.items():
            cols = ", ".join(f'"{c}" text' for c in columns)
            conn.execute(text(f'CREATE TABLE {PLAIN_SCHEMA}."{name}" ({cols})'))
            if rows:
                marks = ", ".join(f":c{i}" for i in range(len(columns)))
                conn.execute(text(f'INSERT INTO {PLAIN_SCHEMA}."{name}" VALUES ({marks})'),
                             [{f"c{i}": v for i, v in enumerate(row)} for row in rows])
    counts = ", ".join(f"{name} {len(rows)}줄" for name, (_, rows) in tables.items())
    return f"평문 사본을 만들었습니다 (스키마 {PLAIN_SCHEMA}): {counts}\n다 보면 unplain 으로 지워 주세요"


def dropPlain() -> str:
    with engine.begin() as conn:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {PLAIN_SCHEMA} CASCADE"))
    return f"평문 사본(스키마 {PLAIN_SCHEMA})을 지웠습니다"


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if (command, len(sys.argv)) not in (("decrypt", 3), ("answers", 3), ("field", 5), ("plain", 2), ("unplain", 2)):
        sys.exit(__doc__)
    if command == "plain":
        with SessionLocal() as session:
            print(makePlain(session))
    elif command == "unplain":
        print(dropPlain())
    elif command == "field":
        with SessionLocal() as session:
            print(fieldText(session, *sys.argv[2:5]))
    elif command == "decrypt":
        print(decryptValue(sys.argv[2]))
    else:
        with SessionLocal() as session:
            print(answersText(session, sys.argv[2]))
