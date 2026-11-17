"""frontend 의 함수·컴포넌트·훅을 정규식으로 뽑는다(최상위 + 컴포넌트 안 한 단계)."""
import json, pathlib, re
FE = pathlib.Path(r"C:\big21\hw-repo\HWF(TeamMAKE)\huge\frontend")
files = sorted(p for d in ("app", "components", "lib") for p in (FE / d).rglob("*.ts*") if p.suffix in (".ts", ".tsx"))
files += [FE / "proxy.ts"]
PAT = re.compile(r"^(\s*)(export\s+)?(default\s+)?(async\s+)?function\s+(\w+)\s*(<[^>]*>)?\s*\(([^)]*)\)|^(\s*)(export\s+)?const\s+(\w+)\s*(?::[^=]+)?=\s*(async\s*)?(\([^)]*\)|\w+)\s*(?::\s*[^=]+)?=>", re.M)
out = {}
for f in files:
    src = f.read_text(encoding="utf-8"); lines = src.splitlines()
    rel = str(f.relative_to(FE.parent)).replace("\\", "/")
    head = []
    for l in lines[:6]:
        s = l.strip()
        if s.startswith("//") : head.append(s.lstrip("/ ").strip())
        elif s.startswith(("/*", "*")) and "*/" not in s[:2]: head.append(s.strip("/* ").strip())
    items = []
    for m in PAT.finditer(src):
        ind = m.group(1) if m.group(5) else m.group(8)
        if len(ind or "") > 4: continue
        name = m.group(5) or m.group(10)
        exported = bool(m.group(2) or m.group(9))
        params = (m.group(7) if m.group(5) else m.group(12)) or ""
        lineNo = src[:m.start(5) if m.group(5) else m.start(10)].count("\n") + 1  # 이름 위치 기준 (앞 빈 줄을 세지 않게)
        com = []
        i = lineNo - 2
        while i >= 0 and lines[i].strip().startswith(("//", "*", "/*")):
            com.insert(0, lines[i].strip().strip("/*").strip()); i -= 1
        kind = "component" if name[0].isupper() else "hook" if re.match(r"use[A-Z]", name) else "function"
        items.append({"name": name, "line": lineNo, "exported": exported, "default": bool(m.group(3)), "params": re.sub(r"\s+", " ", params)[:60],
                      "desc": " ".join(c for c in com if c), "kind": kind, "depth": 0 if not ind else 1})
    out[rel] = {"lines": len(lines), "head": " ".join(head), "items": items}
# 사용처: import 하는 파일
for rel, m in out.items():
    for it in m["items"]:
        if not it["exported"]: it["usedBy"] = []; continue
        users = []
        for rel2 in out:
            if rel2 == rel: continue
            s = (FE.parent / rel2).read_text(encoding="utf-8")
            if re.search(r"import[^;]*\b" + it["name"] + r"\b[^;]*from", s, re.S): users.append(rel2.replace("frontend/", ""))
        it["usedBy"] = users
json.dump(out, open("ts.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
n = sum(len(m["items"]) for m in out.values()); nd = sum(1 for m in out.values() for it in m["items"] if not it["desc"])
print(len(out), "files", n, "items", nd, "no desc")
for rel, m in out.items():
    print(rel, m["lines"], "|", m["head"][:60], "|", ", ".join(("*" if it["exported"] else "") + it["name"] + ("" if it["desc"] else "?") for it in m["items"]))
