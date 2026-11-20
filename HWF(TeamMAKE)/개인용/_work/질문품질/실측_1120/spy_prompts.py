import asyncio, json, sys
sys.path.insert(0, "/srv")
from app.services import llm, question_compose
real = llm.structured
seen = []
async def spy(schema, system, user, *a, **k):
    if schema is question_compose.RagQuestion:
        seen.append(user)
    return await real(schema, system, user, *a, **k)
llm.structured = spy
from app.db import SessionLocal
from app.models import Application
db = SessionLocal(); db.get(Application, sys.argv[1]).questions_status = "none"; db.commit(); db.close()
asyncio.run(question_compose.compose(sys.argv[1]))
def sec(p, tag):
    return p.split(f"<{tag}>\n")[1].split(f"\n</{tag}>")[0] if f"<{tag}>\n" in p else None
out = []
for p in seen:
    kind = p.split("[만들 질문] ")[1].split(" ")[0]
    if kind in ("회사", "직무"):
        info = sec(p, "회사") or ""
        extra = info.split("회사가 진행한 프로젝트:")[1] if "회사가 진행한 프로젝트:" in info else ""
        extra += info.split("회사가 요즘 다루는 기술")[1] if "회사가 요즘 다루는 기술" in info else ""
        out.append({"kind": kind, "company_extra": extra.strip()[:200], "tech": sec(p, "기술"), "news": sec(p, "소식"),
                    "sections": [t for t in ("공고", "회사", "소식", "기술", "이력서") if f"<{t}>" in p]})
json.dump(out, open("/tmp/spy.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(len(seen), "prompts")
