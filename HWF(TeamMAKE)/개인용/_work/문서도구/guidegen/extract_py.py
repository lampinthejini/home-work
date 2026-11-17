"""backend/app 의 모든 함수·클래스와 호출 관계를 JSON 으로 뽑는다."""
import ast, json, pathlib, sys
ROOT = pathlib.Path(r"C:\big21\hw-repo\HWF(TeamMAKE)\huge\backend")
APP = ROOT / "app"

def modName(p):
    return ".".join(p.relative_to(ROOT).with_suffix("").parts)

def seg(src, node):
    return ast.get_source_segment(src, node) or ""

def describe(node, lines, src):
    d = ast.get_docstring(node)
    if d:
        return d.strip().split("\n\n")[0].replace("\n", " "), "doc"
    # 바로 위 주석
    i = (node.decorator_list[0].lineno if getattr(node, "decorator_list", None) else node.lineno) - 2
    com = []
    while i >= 0 and lines[i].strip().startswith("#"):
        com.insert(0, lines[i].strip().lstrip("#").strip()); i -= 1
    if com:
        return " ".join(com), "comment"
    # 몸통 첫 줄 주석
    if node.body:
        j = node.body[0].lineno - 2
        if j >= node.lineno - 1 and lines[j].strip().startswith("#"):
            return lines[j].strip().lstrip("#").strip(), "comment"
    return "", ""

def route(node, src):
    for d in getattr(node, "decorator_list", []):
        if isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.func.attr in ("get","post","put","patch","delete","websocket"):
            path = d.args[0].value if d.args and isinstance(d.args[0], ast.Constant) else ""
            return f"{d.func.attr.upper()} {PREFIX.get(modName(CURRENT[0]), '')}{path}"
        if isinstance(d, ast.Attribute) and d.attr == "task" or (isinstance(d, ast.Call) and getattr(d.func, "attr", "") == "task"):
            return "Celery task"
    return ""

def sig(node, src):
    a = node.args
    parts = []
    for x in a.posonlyargs + a.args:
        parts.append(x.arg)
    if a.vararg: parts.append("*" + a.vararg.arg)
    for x in a.kwonlyargs: parts.append(x.arg)
    if a.kwarg: parts.append("**" + a.kwarg.arg)
    ret = ""
    if node.returns is not None:
        ret = " -> " + seg(src, node.returns)
    return f"({', '.join(parts)}){ret}"

import re as _re
PREFIX = {}
for _f in (APP / "routers").glob("*.py"):
    _m = _re.search(r'APIRouter\(prefix="([^"]+)"', _f.read_text(encoding="utf-8"))
    if _m: PREFIX[modName(_f)] = _m.group(1)
CURRENT = [None]
out = {}
for f in sorted(APP.rglob("*.py")):
    CURRENT[0] = f
    src = f.read_text(encoding="utf-8"); lines = src.splitlines()
    t = ast.parse(src)
    m = {"path": str(f.relative_to(ROOT.parent)).replace("\\","/"), "lines": len(lines), "doc": (ast.get_docstring(t) or "").strip(), "items": [], "imports": []}
    for n in t.body:
        if isinstance(n, ast.ImportFrom) and n.module and (n.module.startswith("app") or n.level):
            m["imports"].append(n.module or "")
    def walk(body, prefix="", depth=0):
        for n in body:
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                d, src_ = describe(n, lines, src)
                m["items"].append({"kind": "async def" if isinstance(n, ast.AsyncFunctionDef) else "def", "name": prefix + n.name, "short": n.name,
                    "line": n.lineno, "end": n.end_lineno, "sig": sig(n, src), "desc": d, "descSrc": src_, "route": route(n, src), "depth": depth})
                walk(n.body, prefix + n.name + ".", depth + 1)
            elif isinstance(n, ast.ClassDef):
                d, src_ = describe(n, lines, src)
                bases = ", ".join(seg(src, b) for b in n.bases)
                m["items"].append({"kind": "class", "name": prefix + n.name, "short": n.name, "line": n.lineno, "end": n.end_lineno, "sig": f"({bases})" if bases else "", "desc": d, "descSrc": src_, "route": "", "depth": depth})
                walk(n.body, prefix + n.name + ".", depth + 1)
    walk(t.body)
    out[modName(f)] = m

# 호출 관계: import 를 따라가 "어느 모듈의 함수인지" 확인된 호출만 센다
defs = {mod: {it["short"] for it in m["items"]} for mod, m in out.items()}
topDefs = {mod: {it["short"] for it in m["items"] if it["depth"] == 0} for mod, m in out.items()}

def resolveFrom(callerMod, level, module):
    if level == 0:
        return module or ""
    base = callerMod.split(".")[:-level] if not callerMod.endswith("__init__") else callerMod.split(".")[:-level]
    return ".".join(base + ([module] if module else []))

calls = {}
SCAN = list(APP.rglob("*.py")) + list((ROOT / "tests").rglob("*.py"))
for f in SCAN:
    src = f.read_text(encoding="utf-8")
    try: t = ast.parse(src)
    except SyntaxError: continue
    callerMod = modName(f)
    names, aliases = {}, {}
    for n in ast.walk(t):
        if isinstance(n, ast.ImportFrom):
            target = resolveFrom(callerMod, n.level, n.module)
            for al in n.names:
                sub = target + "." + al.name if target else al.name
                if sub in out:
                    aliases[al.asname or al.name] = sub
                elif target in out:
                    names[al.asname or al.name] = target
        elif isinstance(n, ast.Import):
            for al in n.names:
                if al.name in out:
                    aliases[(al.asname or al.name).split(".")[-1] if al.asname else al.name] = al.name
    stack = []
    def record(mod, nm):
        where = callerMod + (":" + stack[-1] if stack else "")
        calls.setdefault((mod, nm), set()).add(where)
    class V(ast.NodeVisitor):
        def visitFn(self, n):
            stack.append(n.name); self.generic_visit(n); stack.pop()
        visit_FunctionDef = visit_AsyncFunctionDef = visitFn
        def visit_Attribute(self, n):
            v = n.value
            if isinstance(v, ast.Name):
                if v.id in aliases and n.attr in defs.get(aliases[v.id], ()):
                    record(aliases[v.id], n.attr)
                elif v.id == "self" and callerMod in out and n.attr in defs[callerMod]:
                    record(callerMod, n.attr)
            self.generic_visit(n)
        def visit_Name(self, n):
            if isinstance(n.ctx, ast.Load):
                if n.id in names and n.id in defs.get(names[n.id], ()):
                    record(names[n.id], n.id)
                elif callerMod in out and n.id in topDefs[callerMod] and stack:
                    record(callerMod, n.id)
    V().visit(t)
for mod, m in out.items():
    for it in m["items"]:
        it["calledBy"] = sorted(x for x in calls.get((mod, it["short"]), ()) if x != mod + ":" + it["short"])
json.dump(out, open("py.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
tot = sum(len(m["items"]) for m in out.values())
nodesc = [(mod, it["name"]) for mod, m in out.items() for it in m["items"] if not it["desc"] and not it["route"]]
print("items", tot, "no desc/route", len(nodesc), "nested", sum(1 for m in out.values() for it in m["items"] if it["depth"] and it["kind"]!="class" and not m["items"][0] is None and "." in it["name"] and not it["name"].split(".")[0][0].isupper()))
