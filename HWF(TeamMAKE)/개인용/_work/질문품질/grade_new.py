"""새로 만든 질문(정답 채점 없음)을 4B 채점기(grade4b.py 3차)로 채점한다 — 자료 3개 바꾼 뒤 비교용 (2026-11-20, C-30).

입력: 실측_1120/new.jsonl (id, person, kind, source, text). 출력: --out 파일에 4B 점수.
api 컨테이너 안에서 grade4b.py 와 같은 방법으로 돌린다.
"""

import argparse
import asyncio
import json

import httpx

import grade4b


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=str(grade4b.HERE / "실측_1120" / "new.jsonl"))
    ap.add_argument("--out", default="/tmp/new_4b.jsonl")
    args = ap.parse_args()
    personas = json.load(open(grade4b.HERE / "원본_1119" / "personas.json", encoding="utf-8"))
    labels = {r["id"]: r for r in (json.loads(x) for x in open(grade4b.HERE / "labels.jsonl", encoding="utf-8"))}
    examples = [labels[i] for i in grade4b.EXAMPLES]
    rows = [json.loads(x) for x in open(args.src, encoding="utf-8")]
    async with httpx.AsyncClient(timeout=120) as client:
        results = [await grade4b.gradeOne(client, r, examples, personas) for r in rows]
    with open(args.out, "w", encoding="utf-8") as f:
        for x in results:
            f.write(json.dumps(x, ensure_ascii=False) + "\n")
    print(len(results), "graded")


if __name__ == "__main__":
    asyncio.run(main())
