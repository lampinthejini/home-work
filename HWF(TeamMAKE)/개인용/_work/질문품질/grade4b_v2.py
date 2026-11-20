"""4B(llm-rt) 로 질문 품질을 채점하고 Claude 채점(labels.jsonl)과 비교한다 (2차: 호출 둘로 나눔).

호출 A — 질문 글만 보고 q1·q2·q3 와 불량 B1(나·다)·B2·B3·B4. 지원자 서류는 주지 않는다
         (1차에서 서류를 주니 '질문이 서류를 짚었나'가 아니라 '서류에 경험이 있나'로 점수를 매김).
호출 B — 인성·이력서 질문만, 지원자 서류와 함께 '질문이 일어난 일로 말하는 일이 서류에 있나'(B1 가).

api 컨테이너 안에서 돌린다(llm-rt 는 컨테이너 망에서만 열림):
  docker cp 개인용/_work/질문품질 huge-app-api-1:/tmp/qq
  docker exec -w /tmp/qq huge-app-api-1 python grade4b.py [--limit N] [--parallel 1|2] [--out /tmp/파일]
"""

import argparse
import asyncio
import json
import time
from pathlib import Path

import httpx

HERE = Path(__file__).parent
URL = "http://llm-rt:8080"
KIND_KO = {"personality": "인성", "company": "회사", "resume": "이력서", "job": "직무"}

# 호출 A 의 예시. 시험(일치율)에서는 뺀다. why 는 질문 글 기준으로 다시 씀
EXAMPLES = {
    "2-p1-3": "프로젝트 이름(사내 규정 검색 챗봇)+구체 요소(문단 단위 분할). '판단 기준' = 과거 판단",
    "2-p2-1": "누구에게나(협업). '조율하여 진행했나요' 과거형 경험. 일반 업무 상황",
    "2-p1-9": "누구에게나(협업). '조율하시나요' 현재형 일반 방법",
    "1-p2-6": "Python 일반. 원리 = 지식이라 q3 1",
    "2-p1-8": "RAG(공고 업무). '어떻게 측정하나요' 일반형 방법. 검색 품질 측정 = 공고 업무 활동",
    "1-p10-10": "인재상 내용. '일하고 싶으신가요' = 의견",
    "2-p10-10": "누구에게나 묻는 포부. AIIT 이름만. '이루고 싶은 목표' = 의견",
    "1-p8-6": "'Python과 파이썬의' 같은 말 반복 = 문장 꼬임. 차이 = 지식",
    "1-p1-8": "검수와 도구 호출은 같은 갈래가 아니라 차이로 비교할 수 없음. 차이 = 지식",
    "1-p2-2": "회사 가치 내용. '기여하고 싶으신가요' = 의견. 경험을 묻지 않음",
    "S3": "회사 상황(상담 챗봇 오분류)+본인 프로젝트(78%→90%) 적용+그대로 쓸 것·바꿀 것",
    "S4": "회사 업무의 구체적인 상황(AX 4주 시제품). '확인하시겠어요' 앞으로의 방법",
    "S7": "특정 글을 읽었는지 물음",
}

POSTING = ("공고: AI/AX 엔지니어. 주요 업무: LLM 기반 서비스 설계·개발 / RAG 파이프라인 구축과 성능 평가 / 사내 AI 도입 컨설팅(AX). "
           "자격: Python 개발 경험, 머신러닝·딥러닝 기본 지식. 우대: LangChain·벡터 DB 사용 경험.")
COMPANY = ("회사 AIIT: 서비스는 검색·쇼핑·페이·웹툰·클라우드·지도, 자체 언어 모델 AIIT-X. AI 서비스(검색 요약·쇼핑 AI 에이전트·고객 상담 챗봇)는 "
           "'문서를 찾고, 근거를 고르고, 근거로만 답하고, 검증한다' 구조. AX 추진팀은 현업을 관찰해 4주 안에 시제품. 사내 문서 검색 비서. "
           "핵심 가치: 사용자 중심·기술로 연결·함께 성장. 인재상: 사용자의 문제에서 시작 / 측정하고 판단 / 모르는 것을 모른다고 말함 / 함께 더 나아짐. "
           "일하는 방식: 작은 셀이 목표를 정하고 A/B 실험, 실패는 회고로 남김.")

SYSTEM_A = """너는 면접 질문 글의 품질을 채점한다. 지원자가 실제로 무엇을 했는지는 모른다. 질문 글에 적힌 말만 근거로 한다.
why 를 먼저 40자 안으로 쓰고, 그 근거대로 점수를 매긴다.

[b 불량] 해당 코드를 모두. 없으면 빈 목록.
B1: 같은 갈래가 아닌 두 가지를 '차이·구분'으로 비교함(예: 저장소와 방식, 검수와 도구 호출), 또는 회사 정보와 틀린 사실.
B2: 나이·결혼·출산·출신·종교·건강 등 사생활·차별.
B3: 특정 글·자료를 읽었는지 물음.
B4: 말끝이 깨짐, 같은 말 반복, 뜻이 통하지 않음, 어색한 말끝('되시나요', '방법을 생각하시나요'). 영어 뒤 조사 하나 틀림('LangChain를')은 아님.

[q1 맞춤도] 질문 글에 무엇이 적혀 있나
5 = 특정 프로젝트·업무 이름(예: '사내 규정 검색 챗봇', '고객 이탈 예측')과 그 안의 구체 요소(방법·도구·수치·결정, 예: 'BM25', '78%에서 90%')가 함께
4 = 특정 프로젝트·업무 이름만(구체 요소 없음)
3 = 공고·회사 말: LLM 기반 서비스, RAG, 사내 문서, AI 도입, LangChain, 벡터 DB, AI/AX 엔지니어, AIIT 서비스·AIIT-X·가치·인재상·문화·일하는 방식·AI 구조
2 = 직무 일반: Python, ML, 분류 모델, LLM 일반, 테스트, 메모리, 데이터, 생성형 AI 일반
1 = 누구에게나: 협업·책임감·피드백·우선순위·지원 계기·포부. 'AIIT' 이름만 있어도 1
'프로젝트', '팀 프로젝트', '이력서에 적은 기술', '맡은 업무', '연구'처럼 이름 없는 말은 특정 프로젝트가 아니다.

[q2 깊이 확인] 무엇을 답하게 하나. 여러 개면 높은 쪽
1 = 지식(원리·정의·차이·구분·장단점·'어떤 문제가 생기나요') 또는 의견('끌리는', '계기', '어떻게 이해', '관심', '하고 싶은', '일하고 싶은', '기여하고 싶은', '어떻게 생각', '이루고 싶은'). 회사가 한 일의 이유를 묻는 것도 1
2 = 일반형·현재형·앞으로의 방법·원인·기준('어떻게 측정하시나요', '어떤 방법을 쓰시나요', '조율하시나요', '원인은 무엇이고 어떻게 예방', '확인하시겠어요', '찾으시겠어요'), '경험이 있으신가요', 경험에서 '어떤 점이 가장 중요한가요'
3 = 과거형 본인 경험('~했나요', '~하셨나요', '~였나요', '경험은 어떤 것', '사례를 설명', '배우고 성장', '맡은 역할', '어떻게 반영'), 또는 본인 경험을 옮겨 쓰게 함('어떻게 옮겨 쓰시겠어요')
4 = 본인 판단의 이유·기준('~한 이유', '판단 기준', '어떤 기준으로 ~했나요', '배경'), 또는 '무엇을 먼저' 고르게 함
5 = 4 에 더해 다른 선택지('A와 B 가운데', '무엇을 그대로 쓰고 무엇을 바꾸'), 결과 확인('어떻게 확인하셨나요'), 한계('놓친 것', '왜 멈추') 가운데 하나를 함께 물음

[q3 연결]
먼저: 기술의 원리·정의·차이·장단점을 묻는 지식 질문이면 1.
5 = 회사·공고 업무의 구체적인 문제 상황 + 본인 프로젝트·경험을 그 상황에 적용
4 = 회사·공고 업무의 구체적인 문제 상황('~가 잦다면', '~가 생기면', '4주 만에 ~한다면')을 주고 대응을 물음
3 = 회사 고유 내용(AIIT 서비스·AIIT-X·가치·인재상·문화·일하는 방식·AI 구조·AX) 또는 공고 업무 활동(LLM 기반 서비스 설계·개발·측정, RAG 구축·검색 품질 측정, 사내 문서·AI 도입), AI/AX 엔지니어 직무
2 = 위가 없고 일반 업무·개발 상황(협업·마감·피드백·품질·테스트·운영·오류·메모리·데이터 처리), 본인 과거 프로젝트, 회사 이름만
1 = 업무 상황이 전혀 없음

JSON 만 답한다."""

SYSTEM_B = """너는 면접 질문이 지원자에 대해 틀린 전제를 깔았는지 확인한다.
1) 질문이 지원자의 프로젝트·업무·연구와 같은 일에 대해, 이미 일어난 일로 말하는 구체적인 사건을 premise 에 그대로 옮긴다
   (예: '~에서 실수를 했을 때', '~를 놓친 상황에서', '실제 사용자 요청에서 ~가 나왔을 때', '~에서 더 오르지 않았을 때').
   '~한 일이 있다면', '~경험이 있으신가요', '팀 프로젝트에서 ~했을 때', '실패한 프로젝트를 겪었을 때'처럼 누구에게나 묻는 일반 가정은 사건이 아니다. 사건이 없으면 premise 는 빈 글자.
2) premise 의 사건이 지원자 서류에 적혀 있거나 서류 내용으로 분명히 알 수 있으면 in_docs=true, 서류에 없으면 false. premise 가 비면 true.
예) 서류 'Recall@10 을 0.62→0.79 로 올림' / 질문 '0.79 에서 더 오르지 않았을 때 무엇을 시도했나요' → premise '0.79 에서 더 오르지 않음', in_docs=false
예) 서류 '처음에는 상관없는 문단이 자주 나와 답이 틀렸다' / 질문 '처음에 틀린 답이 자주 나왔을 때 어떻게 고쳤나요' → in_docs=true
예) 질문 '팀 프로젝트에서 의견이 달랐을 때 어떻게 조율했나요' → premise '', in_docs=true
JSON 만 답한다."""

SCHEMA_A = {"type": "object", "properties": {
    "why": {"type": "string", "maxLength": 80},
    "b": {"type": "array", "items": {"type": "string", "enum": ["B1", "B2", "B3", "B4"]}},
    "q1": {"type": "integer", "minimum": 1, "maximum": 5},
    "q2": {"type": "integer", "minimum": 1, "maximum": 5},
    "q3": {"type": "integer", "minimum": 1, "maximum": 5}},
    "required": ["why", "b", "q1", "q2", "q3"]}
SCHEMA_B = {"type": "object", "properties": {
    "premise": {"type": "string", "maxLength": 80}, "in_docs": {"type": "boolean"}},
    "required": ["premise", "in_docs"]}


def personaBrief(p: dict) -> str:
    r = p["resume"]
    parts = [f"{c['company']} {c['role']}: {c['description']}" for c in r.get("career", [])]
    parts += [f"프로젝트 {x['name']}: {x['description']}" for x in r.get("projects", [])]
    return "지원자 서류: " + " / ".join(parts) + " / 자기소개서: " + p["cover"][:500]


def questionMsg(row: dict) -> str:
    return f"질문 종류: {KIND_KO[row['kind']]}\n질문: {row['text']}"


def messagesA(row: dict, examples: list) -> list:
    msgs = [{"role": "system", "content": SYSTEM_A + "\n\n" + POSTING + "\n" + COMPANY}]
    for ex in examples:
        msgs.append({"role": "user", "content": questionMsg(ex)})
        msgs.append({"role": "assistant", "content": json.dumps(
            {"why": EXAMPLES[ex["id"]], "b": [b for b in ex["b"]], "q1": ex["q1"], "q2": ex["q2"], "q3": ex["q3"]},
            ensure_ascii=False)})
    msgs.append({"role": "user", "content": questionMsg(row)})
    return msgs


def messagesB(row: dict, personas: list) -> list:
    return [{"role": "system", "content": SYSTEM_B},
            {"role": "user", "content": f"{personaBrief(personas[row['person'] - 1])}\n질문: {row['text']}"}]


async def chat(client: httpx.AsyncClient, messages: list, schema: dict, maxTokens: int) -> tuple[dict, dict]:
    r = await client.post(f"{URL}/v1/chat/completions", json={
        "messages": messages, "temperature": 0, "max_tokens": maxTokens,
        "response_format": {"type": "json_schema", "json_schema": {"name": "out", "schema": schema}}})
    r.raise_for_status()
    body = r.json()
    try:
        return json.loads(body["choices"][0]["message"]["content"]), body.get("usage", {})
    except (json.JSONDecodeError, KeyError):
        return {}, body.get("usage", {})


async def gradeOne(client: httpx.AsyncClient, row: dict, examples: list, personas: list) -> dict:
    started = time.monotonic()
    a, ua = await chat(client, messagesA(row, examples), SCHEMA_A, 160)
    got = {"b": a.get("b", []), "q1": a.get("q1", 0), "q2": a.get("q2", 0), "q3": a.get("q3", 0), "why": a.get("why", "JSON 아님")}
    premise = None
    if row["kind"] in ("personality", "resume"):
        b, _ = await chat(client, messagesB(row, personas), SCHEMA_B, 100)
        premise = b
        if b and not b.get("in_docs", True) and "B1" not in got["b"]:
            got["b"] = got["b"] + ["B1"]
    return {"id": row["id"], "got": got, "premise": premise, "sec": round(time.monotonic() - started, 2),
            "prompt_tokens": ua.get("prompt_tokens")}


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
    out["sec_p90"] = secs[max(int(n * 0.9) - 1, 0)]
    out["prompt_tokens_max"] = max(x["prompt_tokens"] or 0 for x in results)
    return out


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--parallel", type=int, default=1)
    ap.add_argument("--out", default="/tmp/result_4b.jsonl")
    args = ap.parse_args()
    personas = json.load(open(HERE / "원본_1119" / "personas.json", encoding="utf-8"))
    rows = {r["id"]: r for r in (json.loads(x) for x in open(HERE / "labels.jsonl", encoding="utf-8"))}
    examples = [rows[i] for i in EXAMPLES]
    tests = [r for i, r in rows.items() if i not in EXAMPLES]
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
    with open(args.out, "w", encoding="utf-8") as f:
        for x in results:
            f.write(json.dumps(x, ensure_ascii=False) + "\n")
    s = summarize(rows, results)
    s["wall_sec"] = round(wall, 1)
    s["parallel"] = args.parallel
    print(json.dumps(s, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    asyncio.run(main())
