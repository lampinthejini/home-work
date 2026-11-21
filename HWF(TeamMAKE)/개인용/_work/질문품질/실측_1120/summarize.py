"""실측 결과 요약과 질문 보기 파일. 사용: python summarize.py c31b c31c  (마지막 TAG 로 {TAG}_view.md 를 만든다)"""
import json
import statistics
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).parent
KIND = {"personality": "인성", "company": "회사", "resume": "이력서", "job": "직무"}


def load(path):
    return [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]


def summary(tag):
    rows = load(HERE / f"{tag}.jsonl")
    grades = {g["id"]: g["got"] for g in load(HERE / f"{tag}_4b.jsonl")}
    times = [t["total"] for t in load(HERE / f"{tag}_time.jsonl")]
    attempts = load(HERE / f"{tag}_attempts.jsonl")
    print(f"== {tag}: 질문 {len(rows)}개, AI {sum(r['source'] == 'ai' for r in rows)}개")
    print(f"   시간 평균 {statistics.mean(times):.1f}초 ({min(times):.0f}~{max(times):.0f})")
    for kind, name in KIND.items():
        got = [grades[r["id"]] for r in rows if r["kind"] == kind and r["source"] == "ai" and r["id"] in grades]
        if got:
            q = [statistics.mean(g[k] for g in got) for k in ("q1", "q2", "q3")]
            print(f"   {name}: {q[0]:.2f} / {q[1]:.2f} / {q[2]:.2f} · 불량 {sum(bool(g['b']) for g in got)} (AI {len(got)}개)")
    ai = [r["text"] for r in rows if r["source"] == "ai"]
    print(f"   '차이' {sum('차이' in t for t in ai)}개, 'RAG와 사내 문서' {sum('RAG와 사내 문서' in t for t in ai)}, "
          f"'사용자 중심' {sum('사용자 중심' in t for t in ai)}, '변호사' {sum('변호사' in t for t in ai)}")
    print("   실패 이유:", Counter(a["problem"].split(" — ")[0][:30] for a in attempts if a["problem"]).most_common(6))
    jobItems = Counter(a["topic"] or a["item"] for a in attempts if a["kind"] == "직무" and not a["problem"] and (a["topic"] or a["item"]))
    print("   직무 주제(받은 것) 상위:", [(i[:75], n) for i, n in jobItems.most_common(4)])
    compItems = Counter(a["item"] for a in attempts if a["kind"] == "회사" and not a["problem"] and a["item"])
    print("   회사 항목(받은 것) 상위:", [(i[:40], n) for i, n in compItems.most_common(3)])
    return rows, grades


def view(tag, rows, grades):
    out = [f"# {tag} (7명 × 3세트) — 4B 점수 q1/q2/q3, 불량", ""]
    last = None
    for r in rows:
        if (r["round"], r["person"]) != last:
            last = (r["round"], r["person"])
            out += ["", f"## {r['round']}세트 · 사람 {r['person']}", ""]
        g = grades.get(r["id"])
        score = f"`{g['q1']}/{g['q2']}/{g['q3']}`" if g else "`-`"
        bad = f" **[불량 {','.join(g['b'])}]**" if g and g["b"] else ""
        spare = f" **[예비: {r['reason']}]**" if r["source"] != "ai" else ""
        out.append(f"- {KIND.get(r['kind'], r['kind'])} {score}{bad}{spare} {r['text']}")
    (HERE / f"{tag}_view.md").write_text("\n".join(out) + "\n", encoding="utf-8")


if __name__ == "__main__":
    for t in sys.argv[1:]:
        rows, grades = summary(t)
    view(sys.argv[-1], rows, grades)
