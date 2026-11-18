"""코드읽기코스의 '`파일:줄` … `이름`' 짝을 모두 찾아 그 줄에 이름의 정의가 있는지 본다. --fix 면 고친다.
같은 칸에 `:줄` 이 여러 개면(→ 로 이은 것) 같은 순서의 `이름` 과 짝짓는다."""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from course_lines import DOC, defLine, linesOf, resolve  # noqa: E402

FIX = "--fix" in sys.argv
doc = DOC.read_text(encoding="utf-8").split("\n")
REF = re.compile(r"`((?:[\w\[\]-]+/)*[\w\[\]-]+\.(?:py|tsx?)):(\d+)`")
NAME = re.compile(r"`([A-Za-z_]\w*)`")
bad = 0
for i, line in enumerate(doc):
    if line.startswith("```") or re.match(r"^\d+\s", line):
        continue
    for cell in line.split("|") if line.startswith("|") else [line]:
        refs = list(REF.finditer(cell))
        if not refs:
            continue
        if "` ~ `:" in cell or line.startswith("#"):  # 줄 범위·머리글(데코레이터 줄부터 보여 줌)은 course_lines.py 가 본다
            continue
        p = resolve(refs[0].group(1))
        if p is None:
            continue
        nums = [(refs[0].group(0), int(refs[0].group(2)))] + [(m.group(0), int(m.group(1))) for m in re.finditer(r"`:(\d+)`", cell)]
        names = [n for n in NAME.findall(cell[refs[0].end():]) if not n.endswith(("py", "ts", "tsx"))]
        if not names and line.startswith("|"):  # 표에서 이름이 다음 칸에 있을 때
            cells = line.split("|")
            k = cells.index(cell)
            names = NAME.findall(cells[k + 1]) if k + 1 < len(cells) else []
        for (text, n), name in zip(nums, names, strict=False):
            want = defLine(p, name)
            if want is None:
                continue
            if want != n:
                bad += 1
                print(f"[{i + 1}] {p.name}:{n} `{name}` → {want}")
                if FIX:
                    doc[i] = doc[i].replace(text, text.replace(f":{n}`", f":{want}`"), 1)
            elif n > len(linesOf(p)):
                print(f"[{i + 1}] {p.name}:{n} 파일보다 김")
if FIX:
    DOC.write_text("\n".join(doc), encoding="utf-8", newline="")
print("bad", bad)
