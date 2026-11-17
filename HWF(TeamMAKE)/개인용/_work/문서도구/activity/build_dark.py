# html/*.html 의 SVG 색을 다크용으로 바꿔 PDF 용 문서 하나(dark/doc.html)로 묶는다
import ast
import html
import re
from pathlib import Path

HERE = Path(__file__).parent
OUT = HERE / "dark"
OUT.mkdir(exist_ok=True)

# 밝은 색 → 어두운 배경에서 읽히는 색
DARK = {
    "#fff": "#1e293b", "#ffffff": "#111a2e", "#f8fafc": "#0f172a",
    "#e2e8f0": "#1e293b", "#cbd5e1": "#334155",
    "#111827": "#e5e7eb", "#4b5563": "#9ca3af", "#374151": "#94a3b8",
    "#1d4ed8": "#60a5fa", "#6d28d9": "#a78bfa", "#b45309": "#f59e0b",
    "#be185d": "#f472b6", "#0f766e": "#2dd4bf", "#047857": "#34d399",
    "#fffbeb": "#2a2112", "#fefce8": "#2a2614", "#a16207": "#ca8a04", "#713f12": "#fde68a",
}
CANVAS = "#0b1120"
HEX = re.compile(r"#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3})(?![0-9a-fA-F])")


def darkSvg(svg):
    # 맨 바깥 배경 사각형은 따로 칠한다 (#fff 는 행동 상자 색으로 쓰이므로)
    svg = re.sub(r'(<rect width="[\d.]+" height="[\d.]+") fill="#fff"/>', rf'\1 fill="{CANVAS}"/>', svg, count=1)
    return HEX.sub(lambda m: m.group(0) if m.group(0) == CANVAS else DARK.get(m.group(0).lower(), m.group(0)), svg)


def loadItems():
    tree = ast.parse((HERE / "make_md.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and node.targets[0].id == "ITEMS":
            return ast.literal_eval(node.value)


ITEMS = loadItems()
LEGEND = [
    ("● 검은 원", "시작"), ("◉ 테두리 원", "활동 끝 (전체 흐름 종료)"), ("⊗ X 원", "흐름 끝 (이 갈래만 끝남)"),
    ("둥근 사각형", "행동"), ("◇ 마름모", "판단 또는 합류. [조건] 은 그 길로 가는 조건"),
    ("굵은 가로 막대", "분기: 아래 흐름들이 동시에 진행"), ("모래시계", "시간 이벤트"),
    ("접힌 종이", "메모"), ("세로 칸", "그 행동을 맡은 쪽"),
]

css = [f"""
* {{ box-sizing: border-box; }}
html, body {{ margin: 0; background: {CANVAS}; color: #e5e7eb; font-family: 'Malgun Gothic', sans-serif; }}
section {{ break-after: page; background: {CANVAS}; }}
section:last-child {{ break-after: auto; }}
svg {{ display: block; }}
.rules {{ padding: 6px 28px 24px; font-size: 15px; line-height: 1.7; }}
.rules li {{ margin: 2px 0; }}
.cover {{ page: cover; width: 1400px; height: 990px; padding: 70px 80px; }}
.cover h1 {{ font-size: 40px; margin: 0 0 8px; }}
.cover .sub {{ color: #9ca3af; font-size: 17px; margin-bottom: 36px; }}
table {{ border-collapse: collapse; font-size: 15px; }}
td, th {{ border: 1px solid #334155; padding: 7px 14px; text-align: left; }}
th {{ background: #1e293b; }}
td:first-child, th:first-child {{ white-space: nowrap; }}
.cols {{ display: flex; gap: 48px; }}
h2 {{ font-size: 20px; margin: 0 0 12px; color: #a78bfa; }}
@page cover {{ size: 1400px 990px; margin: 0; }}
"""]

body = ['<section class="cover"><h1>활동 다이어그램</h1>'
        '<div class="sub">AI 1차 채용면접 플랫폼 · 기능별 동작 흐름 (UML Activity Diagram) · 2026-11-11 구현 코드 기준 · 2026-11-16 03·09 고침</div>'
        '<div class="cols"><div><h2>목록</h2><table><tr><th>번호</th><th>다이어그램</th><th>맡은 쪽</th></tr>']
for key, title, lanes, _ in ITEMS:
    body.append(f"<tr><td>{key[:2]}</td><td>{html.escape(title)}</td><td>{html.escape(lanes)}</td></tr>")
body.append('</table></div><div><h2>읽는 법</h2><table>')
for a, b in LEGEND:
    body.append(f"<tr><td>{html.escape(a)}</td><td>{html.escape(b)}</td></tr>")
body.append("</table></div></div></section>")

for i, (key, title, lanes, rules) in enumerate(ITEMS):
    src = (HERE / "html" / f"{key}.html").read_text(encoding="utf-8")
    svg = darkSvg(re.search(r"<svg.*</svg>", src, re.S).group(0))
    w = int(re.search(r'width="(\d+)"', svg).group(1))
    h = int(re.search(r'height="(\d+)"', svg).group(1))
    ph = h + 40 + 30 * len(rules)
    css.append(f"@page p{i} {{ size: {w}px {ph}px; margin: 0; }}\n.p{i} {{ page: p{i}; width: {w}px; height: {ph}px; }}")
    items = "".join(f"<li>{html.escape(r)}</li>" for r in rules)
    body.append(f'<section class="p{i}">{svg}<ul class="rules">{items}</ul></section>')

doc = ("<!DOCTYPE html><html><head><meta charset='utf-8'><style>" + "\n".join(css) +
       "</style></head><body>" + "".join(body) + "</body></html>")
(OUT / "doc.html").write_text(doc, encoding="utf-8")
print("ok", len(ITEMS))
