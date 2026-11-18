"""코드읽기코스의 줄 번호를 지금 코드와 대조한다.

① 표·본문의 `경로:줄` + 바로 뒤 `이름` → 그 줄에 이름의 정의가 있는가
② '#### `경로:줄`' 뒤 코드 블록의 'NNN  코드' 줄 → 그 줄의 코드와 같은가
--fix 를 주면 ①은 이름의 정의가 있는 줄로, ②는 블록 전체를 같은 만큼 옮겨(첫 줄이 맞는 위치) 고친다.
"""
import re
import sys
from pathlib import Path

HUGE = Path(r"C:\big21\hw-repo\HWF(TeamMAKE)\huge")
DOC = Path(r"C:\big21\hw-repo\HWF(TeamMAKE)\개인용\가이드\코드읽기코스_처음부터순서대로.md")
FIX = "--fix" in sys.argv
FILES = [p for p in list((HUGE / "backend").rglob("*.py")) + list((HUGE / "frontend").rglob("*.ts*"))
         if "node_modules" not in p.parts and ".next" not in p.parts]


def resolve(ref: str) -> Path | None:
    ref = ref.replace("\\", "/")
    hits = [p for p in FILES if p.as_posix().endswith("/" + ref.removeprefix("/"))]
    return hits[0] if len(hits) == 1 else None


def norm(code: str) -> str:
    code = re.sub(r"\s+(#|//)\s.*$", "", code)  # 코스는 줄 끝 주석을 뺀다
    return re.sub(r"\s+", "", code)


cache: dict[Path, list[str]] = {}


def linesOf(p: Path) -> list[str]:
    if p not in cache:
        cache[p] = p.read_text(encoding="utf-8").split("\n")
    return cache[p]


def defLine(p: Path, name: str) -> int | None:
    pat = re.compile(rf"^\s*(async\s+def|def|class|(export\s+)?(default\s+)?(async\s+)?function|(export\s+)?const)\s+{re.escape(name)}\b")
    found = [i + 1 for i, l in enumerate(linesOf(p)) if pat.search(l)]
    return found[0] if len(found) == 1 else None


doc = DOC.read_text(encoding="utf-8").split("\n")
problems = 0
current = None
i = 0
while i < len(doc):
    line = doc[i]
    m = re.match(r"^#{3,4} .*?`([^`:]+?\.(?:py|tsx?))(?::(\d+))?`", line)
    if m:
        current = resolve(m.group(1))
        if current is None:
            print(f"[{i + 1}] 파일을 못 찾음: {m.group(1)}")
    # ② 코드 블록
    if line.startswith("```") and current is not None and i + 1 < len(doc) and re.match(r"^\d+\s", doc[i + 1]):
        j = i + 1
        block = []
        while j < len(doc) and not doc[j].startswith("```"):
            mm = re.match(r"^(\d+)(\s+)(.*)$", doc[j])
            if mm:
                block.append((j, int(mm.group(1)), mm.group(3)))
            j += 1
        src = linesOf(current)
        bad = [(k, n, c) for k, n, c in block if "..." not in c and "…" not in c and (n > len(src) or norm(src[n - 1]) != norm(c))]
        if bad:
            problems += 1
            first = block[0]
            where = [n + 1 for n, l in enumerate(src) if norm(l) == norm(first[2])]
            shift = (where[0] - first[1]) if len(where) == 1 else None
            print(f"[{i + 1}] {current.name}: 코드 {len(bad)}/{len(block)}줄 다름, 옮길 칸 {shift}")
            if FIX and shift is not None:
                after = [(k, n + shift, c) for k, n, c in block]
                still = [1 for k, n, c in after if "..." not in c and "…" not in c and (n > len(src) or norm(src[n - 1]) != norm(c))]
                if still:
                    print(f"      옮겨도 {len(still)}줄 다름 — 손으로 볼 것")
                else:
                    for k, n, c in block:
                        mm = re.match(r"^(\d+)(\s+)(.*)$", doc[k])
                        newNo = str(n + shift)
                        pad = mm.group(2) if len(newNo) == len(mm.group(1)) else " " * max(1, len(mm.group(2)) + len(mm.group(1)) - len(newNo))
                        doc[k] = newNo + pad + mm.group(3)
                    current_shift = shift
                    # 블록 뒤 설명의 '줄 N', '줄 N~M' 도 같은 만큼 옮긴다 (다음 '####' 전까지)
                    nums = {n for _, n, _ in block}
                    k = j + 1
                    while k < len(doc) and not doc[k].startswith("#### ") and not doc[k].startswith("### "):
                        doc[k] = re.sub(r"줄 (\d+)(?:~(\d+))?",
                                        lambda x: "줄 " + str(int(x.group(1)) + shift if int(x.group(1)) in nums else int(x.group(1)))
                                        + (("~" + str(int(x.group(2)) + shift if int(x.group(2)) in nums else int(x.group(2)))) if x.group(2) else ""),
                                        doc[k])
                        k += 1
                    hm = re.match(r"^(#### `[^`]+?:)(\d+)(`.*)$", doc[i - 1] if doc[i - 1].startswith("#### ") else "")
                    for h in range(i, max(i - 4, 0), -1):
                        hm = re.match(r"^(#{3,4} .*?`[^`]+?:)(\d+)(`.*)$", doc[h])
                        if hm:
                            doc[h] = f"{hm.group(1)}{int(hm.group(2)) + shift}{hm.group(3)}"
                            break
        i = j
    # ① `경로:줄` 다음에 오는 `이름`
    for mm in re.finditer(r"`((?:backend|frontend)/[^`:]+|[\w/\[\]-]+\.(?:py|tsx?)):(\d+)`(?:, `:(\d+)`)?\s*\|\s*`([A-Za-z_]\w*)`", doc[i] if i < len(doc) else ""):
        p = resolve(mm.group(1))
        if p is None:
            continue
        n, name = int(mm.group(2)), mm.group(4)
        want = defLine(p, name)
        if want and want != n:
            problems += 1
            print(f"[{i + 1}] {p.name}:{n} `{name}` → 지금 {want}")
            if FIX:
                doc[i] = doc[i].replace(f"`{mm.group(1)}:{n}`", f"`{mm.group(1)}:{want}`", 1)
    i += 1

if FIX:
    DOC.write_text("\n".join(doc), encoding="utf-8", newline="")
print("problems", problems)
