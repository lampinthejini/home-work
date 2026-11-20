"""8B(llm-eval, CPU) 로 면접 질문의 문체만 다듬어 보는 시험 (2026-11-20).

질문 글만 준다(서류 없음). 8B 는 문체 문제가 있는지, 고친 문장을 낸다.
비교: labels.jsonl 의 B4(문체 불량) 와 맞는지, 멀쩡한 질문을 건드리는지, 걸린 시간.
api 컨테이너 안에서:  docker exec -w /tmp/qq huge-app-api-1 python polish8b.py [--limit N] [--out /tmp/파일]
"""

import argparse
import json
import time
from pathlib import Path

import httpx

HERE = Path(__file__).parent
URL = "http://llm-eval:8080"

SYSTEM = """너는 AI 면접관이 지원자에게 읽어 줄 질문의 문장만 다듬는다.
지켜야 할 것: 묻는 내용·질문 개수·고유명사·숫자·기술 이름은 바꾸지 않는다. 내용을 더하거나 빼지 않는다. 문제가 없으면 한 글자도 바꾸지 않는다.
고칠 것:
- 말끝이 깨지거나 면접 존댓말로 어색함 (좋은 말끝: '~나요?', '~셨나요?', '~인가요?', '~주시겠어요?', '~있으신가요?')
- 같은 말을 두 번 씀, 물결표·기호 찌꺼기
- 조사가 틀림 (영어 단어 뒤 조사는 읽는 소리 기준: 'LangChain을', 'API를')
- 앞뒤가 맞지 않거나 뜻이 바로 들어오지 않는 문장
판단:
- ok: 문제가 없으면 true
- meaning_clear: 무엇을 묻는지 분명하면 true. 단어 조합이 이상해 무엇을 묻는지 알 수 없으면 false (이때 fixed 는 원문 그대로)
- problem: 문제를 20자 안으로 (없으면 빈 글자)
- fixed: 고친 질문 (ok 면 원문 그대로)
JSON 만 답한다."""

SCHEMA = {"type": "object", "properties": {
    "problem": {"type": "string", "maxLength": 60},
    "ok": {"type": "boolean"},
    "meaning_clear": {"type": "boolean"},
    "fixed": {"type": "string", "maxLength": 300}},
    "required": ["problem", "ok", "meaning_clear", "fixed"]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", default="/tmp/polish8b.jsonl")
    args = ap.parse_args()
    rows = [json.loads(x) for x in open(HERE / "labels.jsonl", encoding="utf-8")]
    if args.limit:
        rows = rows[:args.limit]
    out, started = [], time.monotonic()
    with httpx.Client(timeout=300) as client:
        for r in rows:
            t0 = time.monotonic()
            resp = client.post(f"{URL}/v1/chat/completions", json={
                "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": f"질문: {r['text']}"}],
                "temperature": 0, "max_tokens": 300,
                "response_format": {"type": "json_schema", "json_schema": {"name": "out", "schema": SCHEMA}}})
            resp.raise_for_status()
            body = resp.json()
            try:
                got = json.loads(body["choices"][0]["message"]["content"])
            except (json.JSONDecodeError, KeyError):
                got = {"problem": "JSON 아님", "ok": True, "meaning_clear": True, "fixed": r["text"]}
            rec = {"id": r["id"], "truth_b4": "B4" in r["b"], "text": r["text"], **got,
                   "changed": got.get("fixed", r["text"]).strip() != r["text"].strip(),
                   "sec": round(time.monotonic() - t0, 2), "usage": body.get("usage", {})}
            out.append(rec)
            print(json.dumps({k: rec[k] for k in ("id", "truth_b4", "ok", "meaning_clear", "changed", "sec")}, ensure_ascii=False), flush=True)
    with open(args.out, "w", encoding="utf-8") as f:
        for x in out:
            f.write(json.dumps(x, ensure_ascii=False) + "\n")
    n = len(out)
    secs = sorted(x["sec"] for x in out)
    print(json.dumps({"n": n, "wall_sec": round(time.monotonic() - started, 1), "sec_avg": round(sum(secs) / n, 2),
                      "sec_p90": secs[max(int(n * 0.9) - 1, 0)],
                      "b4_total": sum(x["truth_b4"] for x in out),
                      "b4_caught": [x["id"] for x in out if x["truth_b4"] and (not x["ok"] or not x["meaning_clear"])],
                      "clean_changed": [x["id"] for x in out if not x["truth_b4"] and x["changed"]]},
                     ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
