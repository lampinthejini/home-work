"""4B(llm-rt) 로 질문 품질을 채점하고 Claude 채점(labels.jsonl)과 비교한다.

api 컨테이너 안에서 돌린다(llm-rt 는 컨테이너 망에서만 열림):
  docker cp 개인용/_work/질문품질 huge-app-api-1:/tmp/qq
  docker exec -w /tmp/qq huge-app-api-1 python grade4b.py [--limit N] [--parallel 1|2] [--out 파일]
결과: 질문마다 4B 점수·걸린 시간·토큰을 jsonl 로, 끝에 일치율·시간 요약을 출력한다.
"""

import argparse
import asyncio
import json
import time
from pathlib import Path

import httpx

HERE = Path(__file__).parent
URL = "http://llm-rt:8080"

# 프롬프트 안에 넣는 예시. 시험(일치율)에서는 뺀다
EXAMPLE_IDS = ["2-p1-3", "2-p2-1", "2-p1-9", "1-p2-6", "2-p1-8", "1-p10-10", "2-p10-10",
               "1-p8-6", "2-p5-9", "1-p1-8", "S3", "S4", "S7"]

POSTING = ("공고: AI/AX 엔지니어. 주요 업무: LLM 기반 서비스 설계·개발 / RAG 파이프라인 구축과 성능 평가 / 사내 AI 도입 컨설팅(AX). "
           "자격: Python 개발 경험, 머신러닝·딥러닝 기본 지식. 우대: LangChain·벡터 DB 사용 경험.")
COMPANY = ("회사 AIIT: 서비스는 검색·쇼핑·페이·웹툰·클라우드·지도, 자체 언어 모델 AIIT-X. AI 서비스(검색 요약·쇼핑 AI 에이전트·고객 상담 챗봇)는 "
           "'문서를 찾고, 근거를 고르고, 근거로만 답하고, 검증한다' 구조. AX 추진팀은 현업을 관찰해 4주 안에 시제품. 사내 문서 검색 비서. "
           "핵심 가치: 사용자 중심·기술로 연결·함께 성장. 인재상: 사용자의 문제에서 시작 / 측정하고 판단 / 모르는 것을 모른다고 말함 / 함께 더 나아짐. "
           "일하는 방식: 작은 셀이 목표를 정하고 A/B 실험, 실패는 회고로 남김.")

SYSTEM = """너는 면접 질문의 품질을 채점한다. 질문에 대한 답이 아니라 질문 자체를 본다. 아래 규칙을 위에서부터 차례로 적용한다.

[불량 b] 해당하는 코드를 모두 넣는다. 없으면 빈 목록.
B1 틀린 전제: (가) 지원자 서류에 없는 구체적인 일(실수·실패·사용자 경험·수치)을 지원자가 겪은 것처럼 말함. '실패한 경험이 있다면'처럼 누구에게나 묻는 일반 가정은 B1 아님. (나) 같은 갈래가 아닌 두 가지를 '차이·구분'으로 비교함(예: 저장소와 방식, 검수와 도구 호출). (다) 회사 정보와 틀린 사실.
B2 차별·사생활: 나이·결혼·출산·출신·종교·건강 등.
B3 특정 글이나 자료를 읽었는지 물음.
B4 문장 깨짐: 말끝이 깨짐, 같은 말 반복, 뜻이 통하지 않음, 어색한 말끝(예: '되시나요', '방법을 생각하시나요'). 영어 뒤 조사 하나 틀림('LangChain를')은 B4 아님.

[q1 맞춤도] 이 지원자·이 공고라서 나온 질문인가
5 = 지원자 서류의 특정 프로젝트·업무를 짚고, 그 안의 구체 요소(방법·수치·결정)까지 짚음
4 = 특정 프로젝트·업무를 짚었지만 구체 요소는 없음
3 = 공고 업무·우대(LLM 서비스, RAG, AX, LangChain, 벡터 DB)나 회사 고유 내용(서비스·가치·인재상·일하는 방식·AI 구조)에 맞춤
2 = 직무 분야 일반(Python·ML·LLM 일반 지식, 일반 개발 문제)
1 = 누구에게나 물을 수 있음(협업·책임감·지원 계기·포부 일반). 회사 이름만 들어간 것도 1

[q2 깊이 확인] 직접 해 본 사람만 답할 수 있나
1 = 원리·정의·차이·장단점을 묻는 지식, 또는 의견·계기·끌리는 이유·이해·하고 싶은 것
2 = 방법·원인·기준을 일반형·현재형으로 물음('어떻게 측정하나요', '조율하시나요'), 또는 예/아니오로 끝날 수 있는 경험 질문, 또는 경험에서 '어떤 점이 중요한지' 같은 의견
3 = 본인의 과거 경험(무엇을·어떻게 했나, 배운 점)을 말하게 함, 또는 회사 상황에 본인 경험을 옮기게 함
4 = 경험 속 본인 판단의 이유·기준을 물음('고른 이유', '판단 기준'), 또는 상황에서 무엇을 먼저 할지 판단하게 함
5 = 판단과 함께 다른 선택지·결과·한계 가운데 하나를 질문이 분명히 요구함

[q3 연결] 회사·공고 업무와 잇는가
먼저: q2 가 1 이고 원리·정의·차이·장단점 지식 질문이면 q3 = 1.
5 = 회사·공고 업무의 구체적인 상황 + 지원자 본인 경험을 적용하게 함
4 = 회사·공고 업무의 구체적인 상황(누구의 어떤 문제)을 주고 대응을 물음
3 = 회사 고유 내용이나 공고 주요 업무 활동(LLM 서비스 설계, RAG 구축·성능 평가, 사내 AI 도입)을 다룸
2 = 일반 업무·개발 상황(협업·마감·품질·테스트·운영·오류), 본인 과거 프로젝트, 회사 이름만 있음
1 = 업무 상황이 없음

JSON 만 답한다. why 는 40자 이내로 점수의 핵심 근거만."""


def personaBrief(p: dict) -> str:
    r = p["resume"]
    parts = [f"{c['company']} {c['role']}: {c['description']}" for c in r.get("career", [])]
    parts += [f"프로젝트 {x['name']}: {x['description']}" for x in r.get("projects", [])]
    return "지원자 서류: " + " / ".join(parts) + " / 자기소개서: " + p["cover"][:400]


def userMsg(row: dict, personas: list) -> str:
    kind = {"personality": "인성", "company": "회사", "resume": "이력서", "job": "직무"}[row["kind"]]
    return f"{personaBrief(personas[row['person'] - 1])}\n질문 종류: {kind}\n질문: {row['text']}"


def answerOf(row: dict) -> str:
    return json.dumps({"b": row["b"], "q1": row["q1"], "q2": row["q2"], "q3": row["q3"], "why": row["why"][:40]},
                      ensure_ascii=False)


SCHEMA = {"type": "object", "properties": {
    "b": {"type": "array", "items": {"type": "string", "enum": ["B1", "B2", "B3", "B4"]}},
    "q1": {"type": "integer", "minimum": 1, "maximum": 5},
    "q2": {"type": "integer", "minimum": 1, "maximum": 5},
    "q3": {"type": "integer", "minimum": 1, "maximum": 5},
    "why": {"type": "string", "maxLength": 80}},
    "required": ["b", "q1", "q2", "q3", "why"]}


def buildMessages(row: dict, examples: list, personas: list) -> list:
    msgs = [{"role": "system", "content": SYSTEM + "\n\n" + POSTING + "\n" + COMPANY}]
    for ex in examples:  # 예시는 지원자 서류 없이 짧게(길이 제한 4,096토큰)
        kind = {"personality": "인성", "company": "회사", "resume": "이력서", "job": "직무"}[ex["kind"]]
        msgs.append({"role": "user", "content": f"(예시) 질문 종류: {kind}\n질문: {ex['text']}"})
        msgs.append({"role": "assistant", "content": answerOf(ex)})
    msgs.append({"role": "user", "content": userMsg(row, personas)})
    return msgs


async def gradeOne(client: httpx.AsyncClient, row: dict, examples: list, personas: list) -> dict:
    started = time.monotonic()
    r = await client.post(f"{URL}/v1/chat/completions", json={
        "messages": buildMessages(row, examples, personas), "temperature": 0, "max_tokens": 160,
        "response_format": {"type": "json_schema", "json_schema": {"name": "grade", "schema": SCHEMA}}})
    r.raise_for_status()
    body = r.json()
    sec = time.monotonic() - started
    try:
        got = json.loads(body["choices"][0]["message"]["content"])
    except (json.JSONDecodeError, KeyError):
        got = {"b": [], "q1": 0, "q2": 0, "q3": 0, "why": "JSON 아님"}
    usage = body.get("usage", {})
    return {"id": row["id"], "got": got, "sec": round(sec, 2),
            "prompt_tokens": usage.get("prompt_tokens"), "completion_tokens": usage.get("completion_tokens")}


def summarize(rows: dict, results: list) -> dict:
    n = len(results)
    out = {"n": n}
    for k in ("q1", "q2", "q3"):
        exact = sum(rows[x["id"]][k] == x["got"][k] for x in results)
        near = sum(abs(rows[x["id"]][k] - x["got"][k]) <= 1 for x in results)
        out[k] = {"exact": round(exact / n, 3), "within1": round(near / n, 3)}
    allNear = sum(all(abs(rows[x["id"]][k] - x["got"][k]) <= 1 for k in ("q1", "q2", "q3")) for x in results)
    out["all3_within1"] = round(allNear / n, 3)
    truthBad = [x for x in results if rows[x["id"]]["b"]]
    out["bad_total"] = len(truthBad)
    out["bad_missed"] = [x["id"] for x in truthBad if not x["got"]["b"]]
    out["false_bad"] = [x["id"] for x in results if x["got"]["b"] and not rows[x["id"]]["b"]]
    secs = sorted(x["sec"] for x in results)
    out["sec_avg"] = round(sum(secs) / n, 2)
    out["sec_p90"] = secs[int(n * 0.9) - 1] if n >= 10 else secs[-1]
    out["prompt_tokens_max"] = max(x["prompt_tokens"] or 0 for x in results)
    return out


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--parallel", type=int, default=1)
    ap.add_argument("--out", default="result_4b.jsonl")
    args = ap.parse_args()
    personas = json.load(open(HERE / "원본_1119" / "personas.json", encoding="utf-8"))
    rows = {r["id"]: r for r in (json.loads(x) for x in open(HERE / "labels.jsonl", encoding="utf-8"))}
    examples = [rows[i] for i in EXAMPLE_IDS]
    tests = [r for i, r in rows.items() if i not in EXAMPLE_IDS]
    if args.limit:
        tests = tests[:args.limit]
    sem = asyncio.Semaphore(args.parallel)
    started = time.monotonic()
    async with httpx.AsyncClient(timeout=120) as client:
        async def run(row):
            async with sem:
                return await gradeOne(client, row, examples, personas)
        results = await asyncio.gather(*(run(r) for r in tests))
    wall = time.monotonic() - started
    with open(HERE / args.out, "w", encoding="utf-8") as f:
        for x in results:
            f.write(json.dumps(x, ensure_ascii=False) + "\n")
    s = summarize(rows, results)
    s["wall_sec"] = round(wall, 1)
    s["parallel"] = args.parallel
    print(json.dumps(s, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    asyncio.run(main())
