"""코드열람가이드 부록 A·B 표를 지금 코드로 다시 쓴다.
줄·인자·부르는 곳은 코드에서 새로 뽑고, '하는 일'은 가이드에 이미 적힌 글을 그대로 둔다 (새 함수만 NEW 로 적는다).
python refresh.py [--dry]"""
import ast
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import desc_py  # noqa: E402
import desc_ts  # noqa: E402
from new_desc import FILE_ROLE, NEW, NEW_TS  # noqa: E402

HUGE = Path(r"C:\big21\hw-repo\HWF(TeamMAKE)\huge")
DOC = Path(r"C:\big21\hw-repo\HWF(TeamMAKE)\개인용\가이드\프로그램명세서.md")  # 2026-11-10: 함수 사전은 명세서가 원본
HERE = Path(__file__).parent
py = json.load(open(HERE / "py.json", encoding="utf-8"))
ts = json.load(open(HERE / "ts.json", encoding="utf-8"))
DRY = "--dry" in sys.argv


def cell(s):
    return (s or "").replace("|", "\\|").replace("\n", " ")


def uncell(s):
    return s.replace("\\|", "|").strip()


def short(where):
    if where.startswith("화면 "):
        return where
    mod, _, fn = where.partition(":")
    mod = mod.removeprefix("app.").replace("services.", "s.").replace("routers.", "r.").replace("interview.", "i.")
    return f"{mod}:{fn}" if fn else mod


FE_SRC = {rel.removeprefix("frontend/"): (HUGE / rel).read_text(encoding="utf-8") for rel in ts}


def screenCallers(route):
    method, _, path = route.partition(" ")
    if not path or method == "WEBSOCKET":
        return [r for r, src in FE_SRC.items() if "/ws/" in src or "ws_url" in src] if method == "WEBSOCKET" else []
    parts = re.split(r"\{[^}]+\}", path)
    pat = re.compile(r"[\"'`]" + r"(?:\$\{[^}]+\}|[^/\"'`]+)".join(map(re.escape, parts)) + r"(?:[\"'`?]|\$\{)")
    return sorted(r for r, src in FE_SRC.items() if pat.search(src))


def callers(it):
    app = [c for c in it["calledBy"] if not c.startswith("tests")]
    if it["route"] and not it["route"].startswith("Celery"):
        scr = screenCallers(it["route"])
        app = [f"화면 {r.removeprefix('app/').removesuffix('/page.tsx')}" for r in scr] + app
    tests = sorted({c.split(":")[0] for c in it["calledBy"] if c.startswith("tests")})
    parts = [short(c) for c in app[:4]]
    if len(app) > 4:
        parts.append(f"외 {len(app) - 4}곳")
    if tests:
        parts.append(f"🧪 테스트 {len(tests)}개 파일")
    return " · ".join(parts) or "—"


def kindLabel(it):
    if it["route"]:
        return "🌐 API" if not it["route"].startswith("Celery") else "⏱ 작업"
    if it["kind"] == "class":
        return "클래스"
    if "." in it["name"]:
        owner = it["name"].rsplit(".", 1)[0].split(".")[-1]
        return "메소드" if owner[0].isupper() else "안쪽 함수"
    return "async 함수" if it["kind"] == "async def" else "함수"


def modelRows(path):
    t = ast.parse(path.read_text(encoding="utf-8"))
    rows = []
    for n in t.body:
        if isinstance(n, ast.ClassDef):
            table, cols = "", []
            for s in n.body:
                if isinstance(s, ast.Assign) and any(getattr(x, "id", "") == "__tablename__" for x in s.targets):
                    table = s.value.value
                elif isinstance(s, ast.AnnAssign) and isinstance(s.target, ast.Name):
                    cols.append(s.target.id)
            rows.append((n.name, n.lineno, table, cols))
    return rows


# ---- 지금 가이드의 절 나누기 ----
text = DOC.read_text(encoding="utf-8")
lines = text.split("\n")
HEAD = re.compile(r"^#### `([^`]+)`")
sections = {}  # 파일 → (시작, 끝) 줄 번호 (끝 = 다음 머리 바로 앞)
starts = [(i, HEAD.match(l).group(1)) for i, l in enumerate(lines) if HEAD.match(l)]
for k, (i, name) in enumerate(starts):
    end = starts[k + 1][0] if k + 1 < len(starts) else next(j for j in range(i + 1, len(lines)) if lines[j].startswith("## "))
    # 절 끝의 '###'·'##'·'---' 앞에서 자른다
    for j in range(i + 1, end):
        if lines[j].startswith(("### ", "## ")) or lines[j] == "---":
            end = j
            break
    sections[name] = (i, end)


def oldDescs(name):
    """기존 표에서 이름 → 하는 일"""
    if name not in sections:
        return {}
    i, end = sections[name]
    out, header = {}, None
    for l in lines[i:end]:
        if l.startswith("| 이름") or l.startswith("| 클래스"):
            header = [c.strip() for c in l.strip("|").split("|")]
            continue
        m = re.match(r"^\| `([^`]+)` \|", l)
        if m and header and "하는 일" in header:
            cells = [c for c in re.split(r"(?<!\\)\|", l.strip().strip("|"))]
            out[m.group(1)] = uncell(cells[header.index("하는 일")])
    return out


missing = []


def pyTable(mod, m):
    key = m["path"].removeprefix("huge/").removeprefix("backend/")
    old = oldDescs(key)
    path = HUGE / "backend" / key
    if key in ("app/models.py", "app/schemas.py"):
        rows = modelRows(path)
        if key == "app/models.py":
            out = ["| 클래스 | 줄 | DB 표 | 칸(일부) |", "|---|---|---|---|"]
            out += [f"| `{n}` | {ln} | `{t}` | {cell(', '.join(c[:9]) + (' …' if len(c) > 9 else ''))} |" for n, ln, t, c in rows]
        else:
            # 칸이 없는 클래스(Strict 등)는 사람이 적어 둔 설명을 그대로 둔다
            i, end = sections.get(key, (0, 0))
            kept = {m.group(1): m.group(2) for m in (re.match(r"^\| `(\w+)` \| \d+ \| (.+) \|$", l) for l in lines[i:end]) if m}
            out = ["| 클래스 | 줄 | 받는 칸 |", "|---|---|---|"]
            out += [f"| `{n}` | {ln} | {cell(', '.join(c[:10]) + (' …' if len(c) > 10 else '')) if c else kept.get(n, '')} |" for n, ln, t, c in rows]
        return out
    out = ["| 이름 | 종류 | 줄 | 인자 → 반환 | 하는 일 | 부르는 곳 |", "|---|---|---|---|---|---|"]
    for it in m["items"]:
        full = f"{mod}:{it['name']}"
        d = NEW.get(full) or old.get(it["name"]) or desc_py.D.get(full) or it["desc"]
        if it["route"] and not it["route"].startswith("Celery") and not d.startswith("`"):
            d = f"`{it['route']}`" + (f" — {d}" if d else "")
        elif it["route"] and it["route"].startswith("Celery") and not d.startswith("Celery"):
            d = "Celery 작업" + (f" — {d}" if d else "")
        if not d:
            missing.append(full)
        out.append(f"| `{it['name']}` | {kindLabel(it)} | {it['line']} | `{cell(it['sig'][:60])}` | {cell(d)} | {cell(callers(it))} |")
    return out


def tsTable(rel, m):
    key = rel.removeprefix("frontend/")
    old = oldDescs(key)
    if not m["items"]:
        return None  # 형식만 있는 파일(lib/admin.ts 등)은 손으로 쓴 표를 둔다
    out = ["| 이름 | 종류 | 줄 | 하는 일 | 쓰는 곳 |", "|---|---|---|---|---|"]
    for it in m["items"]:
        full = f"{key}:{it['name']}"
        d = NEW_TS.get(full) or old.get(it["name"]) or desc_ts.D.get(f"{rel}:{it['name']}", "") or it["desc"]
        if not d:
            missing.append(full)
        kind = {"component": "컴포넌트", "hook": "훅", "function": "함수"}[it["kind"]] + (" · 내보냄" if it["exported"] else "")
        used = ", ".join(f"`{u}`" for u in it["usedBy"][:4]) + (f" 외 {len(it['usedBy']) - 4}" if len(it["usedBy"]) > 4 else "")
        out.append(f"| `{it['name']}` | {kind} | {it['line']} | {cell(d)} | {cell(used or '이 파일 안')} |")
    return out


def replaceTable(name, newTable, body):
    """절 안의 첫 표를 바꾼다. body = 절의 줄 목록"""
    i = next(k for k, l in enumerate(body) if l.startswith("| 이름") or l.startswith("| 클래스"))
    j = i
    while j < len(body) and body[j].startswith("|"):
        j += 1
    return body[:i] + newTable + body[j:]


# 고칠 절 모으기
replacements = {}
for mod, m in py.items():
    key = m["path"].removeprefix("huge/").removeprefix("backend/")
    table = pyTable(mod, m)
    if key in sections:
        i, end = sections[key]
        replacements[key] = replaceTable(key, table, lines[i:end])
    elif m["items"]:
        role = FILE_ROLE.get(key)
        if not role:
            missing.append("FILE " + key)
            continue
        replacements[key] = [f"#### `{key}`", "", f"**역할:** {role}", "", "**가져다 쓰는 모듈:** (채움)", ""] + table + [""]
for rel, m in ts.items():
    key = rel.removeprefix("frontend/")
    table = tsTable(rel, m)
    if table and key in sections:
        i, end = sections[key]
        replacements[key] = replaceTable(key, table, lines[i:end])

if DRY:
    print("설명 없는 항목:", len(missing))
    for x in missing:
        print("  ", x)
    newFiles = [k for k in replacements if k not in sections]
    print("새 절:", newFiles)
    sys.exit()

# 새 절 넣을 자리: 같은 폴더의 알파벳 순서 앞 절 뒤
order = sorted(sections.items(), key=lambda kv: kv[1][0])
out = list(lines)
for key in sorted((k for k in replacements if k not in sections), reverse=True):
    folder = key.rsplit("/", 1)[0] + "/"
    before = [k for k, _ in order if k.startswith(folder) and k.count("/") == key.count("/") and k < key]
    after = [k for k, _ in order if k.startswith(folder) and k.count("/") == key.count("/") and k > key]
    if before:
        at = sections[before[-1]][1]
    else:
        at = sections[after[0]][0]
    sections_new = replacements[key]
    replacements[key] = None
    out[at:at] = sections_new + ([""] if out[at - 1] != "" else [])
    # 뒤로 밀린 절 위치 보정
    shift = len(sections_new) + (1 if out[at - 1] != "" else 0)
    sections = {k: ((s + shift, e + shift) if s >= at else (s, e)) for k, (s, e) in sections.items()}
# 기존 절 바꾸기 (뒤에서부터)
for key, (i, end) in sorted(sections.items(), key=lambda kv: -kv[1][0]):
    if replacements.get(key):
        out[i:end] = replacements[key]
DOC.write_text("\n".join(out), encoding="utf-8")
print("ok, 설명 없는 항목", len(missing), missing[:20])
