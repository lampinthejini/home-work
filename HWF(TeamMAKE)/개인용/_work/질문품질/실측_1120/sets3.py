"""서류 합격자 7명의 면접 질문을 3세트씩 다시 만들며 단계별 시간과 LLM 호출 수를 잰다 (2026-11-20).

api 컨테이너 안에서 돈다: docker exec -w /srv huge-app-api-1 python /tmp/qq/실측_1120/sets3.py
결과: /tmp/sets3.jsonl (질문), /tmp/sets3_time.jsonl (한 명·한 세트 시간)
"""

import asyncio
import json
import logging
import os
import sys
import time
from collections import defaultdict

sys.path.insert(0, "/srv")
from app.db import SessionLocal  # noqa: E402
from app.models import Application, InterviewQuestion  # noqa: E402
from app.services import job_news, llm, question_compose, rag, speech  # noqa: E402

TAG = os.environ.get("TAG", "sets3")
logging.basicConfig(filename=f"/tmp/{TAG}_compose.log", level=logging.INFO, format="%(asctime)s %(message)s")
STATE = json.load(open("/tmp/qq/실측_1120/sim_state.json", encoding="utf-8"))
ROUNDS = int(os.environ.get("ROUNDS", "3"))
ONLY = int(os.environ.get("ONLY", "0"))  # 앞 사람 몇 명만
attempts = open(f"/tmp/{TAG}_attempts.jsonl", "w", encoding="utf-8")
stat = defaultdict(float)


def timed(name, fn):
    async def wrap(*a, **k):
        t = time.monotonic()
        try:
            return await fn(*a, **k)
        finally:
            stat[name] += time.monotonic() - t
            stat[name + "_n"] += 1
    return wrap


realStructured = llm.structured


async def structured(schema, system, user, *a, **k):
    t = time.monotonic()
    try:
        out = await realStructured(schema, system, user, *a, **k)
        if schema.__name__ == "RagQuestion":  # 시도마다 받은 자료와 만든 질문 (시험 기록, 앱 로그에는 남기지 않음)
            kind = user.split("[만들 질문] ")[1].split(" ")[0]
            topic = user.split("이번 질문의 기술 주제: ")[1].split(" — 이 주제만")[0] if "이번 질문의 기술 주제: " in user else ""
            NL = chr(10)
            info = user.split("<회사>" + NL)[1].split(NL) if "<회사>" + NL in user else ["", "", ""]
            field, item = info[1], info[2][:150]
            problem = user.split("이전 답의 문제: ")[1].split(NL)[0][:80] if "이전 답의 문제: " in user else ""
            attempts.write(json.dumps({"kind": kind, "topic": topic[:150], "field": field, "item": item, "problem": problem,
                                       "q": out.question}, ensure_ascii=False) + NL)
            attempts.flush()
        return out
    finally:
        stat["llm_" + schema.__name__] += time.monotonic() - t
        stat["llm_" + schema.__name__ + "_n"] += 1


llm.structured = structured
rag.embed = timed("embed", rag.embed)
job_news.collect = timed("news", job_news.collect)
question_compose.loadResumeVectors = timed("resume_vectors", question_compose.loadResumeVectors)
question_compose.addKeyPoints = timed("key_points", question_compose.addKeyPoints)
question_compose.synthesizeAll = timed("tts_all", question_compose.synthesizeAll)
speech.synthesize = timed("tts_one", speech.synthesize)
question_compose.composeAll = timed("slots", question_compose.composeAll)


def passed() -> list[dict]:
    db = SessionLocal()
    try:
        return [a for a in STATE["apps"] if db.get(Application, a["application_id"]).attempt_status == "ready"]
    finally:
        db.close()


async def main() -> None:
    apps = passed()[:ONLY] if ONLY else passed()
    qf = open(f"/tmp/{TAG}.jsonl", "w", encoding="utf-8")
    tf = open(f"/tmp/{TAG}_time.jsonl", "w", encoding="utf-8")
    for rnd in range(1, ROUNDS + 1):
        for a in apps:
            db = SessionLocal()
            app = db.get(Application, a["application_id"])
            app.questions_status = "none"
            for q in db.query(InterviewQuestion).filter_by(application_id=app.id):
                q.audio_key = None
            db.commit()
            db.close()
            stat.clear()
            t = time.monotonic()
            await question_compose.compose(a["application_id"])
            total = time.monotonic() - t
            db = SessionLocal()
            for q in db.query(InterviewQuestion).filter_by(application_id=a["application_id"], kind="base").order_by(InterviewQuestion.seq):
                qf.write(json.dumps({"id": f"{TAG}-r{rnd}-p{a['no']}-{q.seq}", "round": rnd, "person": a["no"], "kind": q.qtype,
                                     "source": "reserve" if q.substituted else "ai", "reason": q.substitute_reason,
                                     "text": q.text}, ensure_ascii=False) + "\n")
            db.close()
            row = {"round": rnd, "person": a["no"], "total": round(total, 1), **{k: round(v, 1) for k, v in stat.items()}}
            tf.write(json.dumps(row, ensure_ascii=False) + "\n")
            qf.flush()
            tf.flush()
            print(json.dumps(row, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
