"""가이드 마크다운 3개 → 그림을 넣은 HTML 3개 (render.js 가 PDF 로 인쇄한다)."""
import base64
import re
import sys
from pathlib import Path

import markdown

import figs

ROOT = Path(r"C:\big21\hw-repo\HWF(TeamMAKE)")
SRC = ROOT / "개인용" / "가이드"
OUT = Path(__file__).parent / "html"
OUT.mkdir(exist_ok=True)
LOGO = "data:image/png;base64," + base64.b64encode((ROOT / "brand" / "logo" / "aiit-wordmark@2x.png").read_bytes()).decode()

DOCS = {
    "이용자가이드_지원자": ("지원자 이용 가이드", "지원부터 AI 면접, 결과 확인까지", [
        ("2. 전체 흐름", figs.applicantFlow, "그림 1. 지원부터 결과까지 한눈에"),
        ("5. AI 면접 보는 법", figs.interviewLoop, "그림 2. 질문 하나가 진행되는 순서"),
        ("하면 안 되는 것", figs.awayRule, "그림 3. 화면 이탈 규칙"),
        ("연결이 끊겼을 때", figs.disconnectTree, "그림 4. 끊겼을 때 어떻게 되나"),
        ("7. 결과 확인", figs.resultTimeline, "그림 5. 응시 뒤 일정"),
    ]),
    "이용자가이드_관리자": ("관리자 이용 가이드", "공고 운영과 AI 면접 결과 관리", [
        ("1. 처음 로그인", figs.adminMenu, "그림 1. 관리자 메뉴 지도"),
        ("2. 공고 만들기", figs.postingLife, "그림 2. 공고의 한살이"),
        ("3. 지원자 보기", figs.scoringLanes, "그림 3. 점수는 이렇게 나옵니다 — AI는 채점 도우미, 합격 계산은 코드"),
        ("평가 지연", figs.reviewFlow, "그림 4. 평가 지연 건 처리"),
        ("8. 자동으로 일어나는 일", figs.dailyJobs, "그림 5. 하루 동안 자동으로 도는 일"),
    ]),
    "코드열람가이드_파일과함수": ("코드 열람 가이드", "파일·함수·메소드 사전과 찾아 읽는 법", [
    ]),
    "프로그램명세서": ("프로그램 명세서", "파일·함수·클래스의 입력·출력·하는 일·호출 관계", [
    ]),
    "개발자가이드_나를위한": ("개발자 가이드", "이 프로그램은 어떻게, 왜 이렇게 만들었나", [
        ("0. 한 장으로 보는", figs.restaurant, "그림 1. 식당으로 보는 전체 구조"),
        ("1. 컨테이너를", figs.containers, "그림 2. 컨테이너 3묶음과 GPU 배치"),
        ("3. 응시 상태", figs.stateBoard, "그림 3. 응시 상태 말판"),
        ("6. 질문 10개", figs.questionFunnel, "그림 4. 질문 만들기 안전망"),
        ("7-1. 끊김 판정", figs.disconnectTimeline, "그림 5. 인터넷 끊김과 창 닫기를 구분하는 법"),
        ("8. 동시 면접 자리", figs.seatRace, "그림 6. 번호표 경주와 Lua 해결"),
        ("9. 코딩테스트", figs.sandbox, "그림 7. 코드 실행 상자의 겹겹 보호"),
        ("10. 채점", figs.scoringLanes, "그림 8. AI와 코드의 역할 나누기"),
        ("10-1. 근거 문장", figs.quoteMatch, "그림 9. 근거 90% 일치 규칙 예시"),
        ("13. 화면", figs.precheckRace, "그림 10. 환경 점검 요청 경주와 해결"),
    ]),
}

CSS = """
@page { size: A4; margin: 18mm 16mm 18mm 16mm; }
@page :first { margin: 0; }
* { box-sizing: border-box; }
body { word-break: keep-all; font-family: 'Malgun Gothic', sans-serif; color: #1b2a4a; font-size: 10.5pt; line-height: 1.65; margin: 0; }
.cover { height: 296mm; display: flex; flex-direction: column; justify-content: center; page-break-after: always;
         background: linear-gradient(160deg, #1b2a4a 0%, #2f6fed 100%); color: #fff; margin: 0; padding: 0 24mm; }
.cover img { width: 150px; background: #fff; padding: 10px 14px; border-radius: 10px; margin-bottom: 40px; }
.cover h1 { font-size: 34pt; margin: 0 0 10px; border: 0; color: #fff; }
.cover .sub { font-size: 15pt; opacity: .9; }
.cover .meta { margin-top: 60px; font-size: 10pt; opacity: .8; }
h1 { font-size: 20pt; border-bottom: 3px solid #2f6fed; padding-bottom: 6px; }
h2 { font-size: 15pt; color: #fff; background: #1b2a4a; padding: 6px 12px; border-radius: 6px; margin-top: 26px; page-break-after: avoid; }
h3 { font-size: 12.5pt; color: #2f6fed; border-left: 5px solid #2f6fed; padding-left: 8px; margin-top: 20px; page-break-after: avoid; }
table { border-collapse: collapse; width: 100%; margin: 10px 0 14px; font-size: 9.5pt; page-break-inside: auto; }
tr { page-break-inside: avoid; }
th { background: #eaf1ff; color: #1b2a4a; border: 1px solid #b9c8e8; padding: 6px 7px; text-align: left; }
td { border: 1px solid #d5dbe8; padding: 5px 7px; vertical-align: top; }
tr:nth-child(even) td { background: #f8faff; }
code { font-family: Consolas, 'Malgun Gothic', monospace; background: #eef1f7; padding: 1px 4px; border-radius: 4px; font-size: 9pt; }
pre { background: #f4f6fb; border: 1px solid #d5dbe8; border-radius: 8px; padding: 10px 12px; font-size: 9pt; white-space: pre-wrap; page-break-inside: avoid; }
pre code { background: none; padding: 0; }
blockquote { margin: 10px 0; padding: 8px 12px; background: #fff8e6; border-left: 5px solid #d9822b; border-radius: 4px; }
blockquote p { margin: 3px 0; }
blockquote:has(p > strong:first-of-type) { }
.tech { background: #eef3ff; border-left-color: #2f6fed; }
blockquote.note { background: #f4f6fb; border-left-color: #9aa6c0; font-size: 9.5pt; color: #3a4663; margin-top: -4px; }
figure { margin: 14px 0 18px; padding: 12px; border: 1px solid #d5dbe8; border-radius: 10px; background: #fff; page-break-inside: avoid; text-align: center; }
figcaption { font-size: 9.5pt; color: #55607a; margin-top: 6px; font-weight: 700; }
hr { border: 0; border-top: 1px dashed #c5cee0; margin: 18px 0; }
strong { color: #10203f; }
p { orphans: 3; widows: 3; }
p:has(+ ul), p:has(+ ol), p:has(+ pre), p:has(+ table) { break-after: avoid; }
.mk { display: inline-block; font-size: .82em; line-height: 1; margin-right: 1px; vertical-align: .04em; }
.mk-bi + code { background: #eef1f7; box-shadow: inset 0 -2px 0 #8a94ab; }
[class*=mk-] + code { border-radius: 4px 4px 0 0; }
.mk-std + code { background: #e8f5ec; box-shadow: inset 0 -2px 0 #5aa97a; }
.mk-web + code { background: #e3f4f6; box-shadow: inset 0 -2px 0 #4aa5b5; }
.mk-ext + code { background: #eaf1ff; box-shadow: inset 0 -2px 0 #2f6fed; }
.mk-home + code { background: #fff3dd; box-shadow: inset 0 -2px 0 #e0a85a; }
blockquote.tech .mk-bi + code { background: #e3ebfb; }
"""


LIST = re.compile(r"^(\s*)([-*]|\d+\.) ")


DENSE = """
table { font-size: 7.6pt; }
td, th { padding: 3px 5px; overflow-wrap: anywhere; }
td code, th code { font-size: 7.2pt; word-break: break-all; }
h2 code { background: none; color: #fff; }
table:has(th:nth-child(6)) { table-layout: fixed; }
table:has(th:nth-child(6)) th:nth-child(1) { width: 21%; }
table:has(th:nth-child(6)) th:nth-child(2) { width: 8%; }
table:has(th:nth-child(6)) th:nth-child(3) { width: 5%; }
table:has(th:nth-child(6)) th:nth-child(4) { width: 18%; }
table:has(th:nth-child(6)) th:nth-child(5) { width: 28%; }
table:has(th:nth-child(6)) th:nth-child(6) { width: 20%; }
td:first-child code { word-break: normal; overflow-wrap: anywhere; }
h4 { font-size: 11pt; margin: 18px 0 6px; padding: 4px 8px; background: #eef3ff; border-radius: 4px; page-break-after: avoid; }
h4 code { background: none; font-size: 10.5pt; }
pre { font-size: 8pt; }
.imports { display: flex; flex-wrap: wrap; align-items: baseline; gap: 2px 14px; margin: 6px 0 10px; padding: 3px 9px; background: #f8faff; border: 1px solid #e1e7f3; border-radius: 6px; font-size: 8.3pt; line-height: 1.95; break-inside: avoid; break-after: avoid; }
.imports .it { font-size: 8pt; font-weight: 700; color: #55607a; }
.imports .grp { border-left: 3px solid #8a94ab; padding-left: 6px; }
.imports .g-home { border-left-color: #e0a85a; }
.imports .g-std { border-left-color: #5aa97a; }
.imports .g-ext { border-left-color: #2f6fed; }
.imports .gl { font-weight: 700; margin-right: 2px; white-space: nowrap; }
.imports code { font-size: 7.4pt; margin: 0 1px; padding: 0 3px; background: #fff; border: 1px solid #dfe5f1; white-space: nowrap; }
table.origin { table-layout: fixed; font-size: 8.6pt; }
table.origin th:nth-child(1) { width: 7%; text-align: center; white-space: nowrap; }
table.origin th:nth-child(2) { width: 27%; }
table.origin th:nth-child(3) { width: 14%; }
table.origin th:nth-child(4) { width: 31%; }
table.origin th:nth-child(5) { width: 21%; }
table.origin td:first-child { text-align: center; vertical-align: middle; font-size: 15pt; line-height: 1.2; }
table.origin td:first-child .mk { font-size: 1em; margin: 0; }
table.origin td code { word-break: normal; overflow-wrap: normal; white-space: nowrap; font-size: 7.6pt; }
table.origin tr:nth-child(1) td:first-child { background: #eef1f7; }
table.origin tr:nth-child(2) td:first-child { background: #e8f5ec; }
table.origin tr:nth-child(3) td:first-child { background: #e3f4f6; }
table.origin tr:nth-child(4) td:first-child { background: #eaf1ff; }
table.origin tr:nth-child(5) td:first-child { background: #fff3dd; }
table.fn:not(:has(th:nth-child(6))) { table-layout: fixed; }
table.fn:not(:has(th:nth-child(6))) th:nth-child(1) { width: 22%; }
table.fn:not(:has(th:nth-child(6))) th:nth-child(2) { width: 11%; }
table.fn:not(:has(th:nth-child(6))) th:nth-child(3) { width: 6%; }
table.fn:not(:has(th:nth-child(6))) th:nth-child(4) { width: 33%; }
table.fn:not(:has(th:nth-child(6))) th:nth-child(5) { width: 28%; }
table.fn th:nth-child(3), table.fn td:nth-child(3) { white-space: nowrap; text-align: right; }
"""


def fixLists(md: str) -> str:
    """문장 바로 다음 줄의 목록은 마크다운이 목록으로 보지 않는다 → 사이에 빈 줄을 넣는다 (원본 .md 는 그대로)"""
    out = []
    for line in md.split("\n"):
        if re.match(r"^ {2,3}([-*]|\d+\.) ", line):  # 2~3칸 하위 목록 → 4칸 (python-markdown 규칙)
            line = "    " + line.lstrip()
        prev = out[-1] if out else ""
        if LIST.match(line) and prev.strip() and not LIST.match(prev) and not prev.startswith(("|", ">", "    ")):
            out.append("")
        out.append(line)
    return "\n".join(out)


ORIGIN = {"🧰": "bi", "🐍": "std", "🌐": "web", "📦": "ext", "🏠": "home"}
ORIGIN_CH = "".join(ORIGIN)
IMPORT_P = re.compile(r"<p><strong>가져다 쓰는 모듈:</strong>\s*(.*?)</p>", re.S)


def importBox(m: re.Match) -> str:
    """'🏠 우리 `a`, `b` · 🐍 표준 `c`' 한 줄 → 묶음별 색 막대 상자"""
    groups = re.split(r"\s·\s(?=[" + ORIGIN_CH + "])", m.group(1).strip())
    parts = []
    for g in groups:
        mm = re.match(r"([" + ORIGIN_CH + r"])\s*(\S+)\s*(.*)", g, re.S)
        if not mm:
            parts.append(f'<span class="grp">{g}</span>')
            continue
        icon, label, rest = mm.groups()
        rest = re.sub(r",\s+(?=<code>)", " ", rest)  # 칩 사이 쉼표는 칩 간격이 대신한다
        parts.append(f'<span class="grp g-{ORIGIN[icon]}"><span class="gl">{icon} {label}</span> {rest}</span>')
    return '<div class="imports"><span class="it">가져다 쓰는 모듈</span>' + "".join(parts) + "</div>"


def markEmoji(html: str) -> str:
    """출처 이모지를 <span class="mk mk-종류"> 로 감싼다 (<pre> 안은 그대로 둔다)"""
    parts = re.split(r"(<pre>.*?</pre>)", html, flags=re.S)
    for i in range(0, len(parts), 2):
        # 칩(<code>)이 바로 붙은 표시만 종류 클래스를 준다 — CSS '+' 는 사이 글자를 건너뛰고 짝을 짓기 때문
        parts[i] = re.sub("([" + ORIGIN_CH + "])(?=(<code>)?)",
                          lambda m: f'<span class="mk{" mk-" + ORIGIN[m.group(1)] if m.group(2) else ""}">{m.group(1)}</span>', parts[i])
    return "".join(parts)


def decorate(html: str) -> str:
    """코드 열람 가이드 전용 후처리 (표 종류 표시, 가져오기 줄, 출처 이모지)"""
    html = re.sub(r"<table>(?=\s*<thead>\s*<tr>\s*<th>표시</th>)", '<table class="origin">', html)
    html = re.sub(r"<table>(?=\s*<thead>\s*<tr>\s*<th>이름</th>\s*<th>종류</th>\s*<th>줄</th>)", '<table class="fn">', html)
    html = IMPORT_P.sub(importBox, html)  # markEmoji 보다 먼저
    return markEmoji(html)


def build(name: str) -> Path:
    title, sub, placements = DOCS[name]
    md = fixLists((SRC / f"{name}.md").read_text(encoding="utf-8"))
    html = markdown.markdown(md, extensions=["tables", "fenced_code", "sane_lists"])
    html = re.sub(r"^<h1>.*?</h1>", "", html, count=1, flags=re.S)  # 표지가 제목을 대신한다
    if name.startswith(("코드열람", "프로그램명세서")):
        html = decorate(html)  # 그림(SVG) 삽입보다 먼저여야 SVG 안의 글자를 건드리지 않는다
    for key, fn, caption in placements:
        pat = re.compile(r"(<h[234]>[^<]*" + re.escape(key) + r"[^<]*</h[234]>)")
        if not pat.search(html):
            sys.exit(f"{name}: heading not found: {key}")
        fig = f"<figure>{fn()}<figcaption>{caption}</figcaption></figure>"
        # 머리글 바로 뒤 첫 문단(설명) 다음에 그림을 둔다
        m = pat.search(html)
        after = html.find("</p>", m.end())
        # 안내 상자(blockquote) 안의 문단이면 상자가 끝난 뒤에 둔다
        if after != -1 and html.count("<blockquote>", m.end(), after) > html.count("</blockquote>", m.end(), after):
            after = html.find("</blockquote>", after) + len("</blockquote>") - 4  # insertAt = after + 4 → 상자 바로 뒤
        nextHead = re.search(r"<h[234]>", html[m.end():])
        insertAt = m.end() if after == -1 or (nextHead and m.end() + nextHead.start() < after) else after + 4
        html = html[:insertAt] + fig + html[insertAt:]
    captions = {"funcMachine": "그림. 함수는 자판기", "classMold": "그림. 클래스는 틀, 객체는 그 틀로 만든 하나하나",
                "layers": "그림. 요청 하나가 지나가는 층"}
    html = html.replace("<blockquote>\n<p>🔧", '<blockquote class="tech">\n<p>🔧')
    # 그림 자리 계산이 끝난 뒤에 붙인다 (자리 계산이 '<blockquote>' 를 센다)
    html = html.replace("<blockquote>\n<p><strong>원래 뜻:", '<blockquote class="note">\n<p><strong>원래 뜻:')
    # 빈 줄로 나눈 '> ' 상자 두 개를 마크다운이 하나로 합친다 → 안쪽 '원래 뜻' 앞에서 상자를 끊는다
    html = re.sub(r'(?<!">\n)(?<!<blockquote>\n)<p><strong>원래 뜻:',
                  '</blockquote>\n<blockquote class="note">\n<p><strong>원래 뜻:', html)
    html = re.sub(r"<p>\[\[FIG:(\w+)\]\]</p>",
                  lambda m: f"<figure>{getattr(figs, m.group(1))()}<figcaption>{captions.get(m.group(1), '')}</figcaption></figure>", html)
    extra = DENSE if name.startswith(("코드열람", "프로그램명세서")) else ""
    if name.startswith("개발자가이드"):
        extra = """
h2 { page-break-before: always; }
h2:first-of-type { page-break-before: auto; }
h4 { font-size: 11pt; margin: 16px 0 6px; padding: 4px 8px; background: #eef3ff; border-radius: 4px; page-break-after: avoid; }
h4 code { background: none; }
"""
    doc = f"""<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8"><title>{title}</title><style>{CSS}{extra}</style></head><body>
<section class="cover"><img src="{LOGO}" alt="AIIT"><h1>{title}</h1><div class="sub">{sub}</div>
<div class="meta">AI 1차 채용면접 자동화 플랫폼 · Team AIIT · 2026-11-16 프로그램 기준</div></section>
{html}</body></html>"""
    out = OUT / f"{name}.html"
    out.write_text(doc, encoding="utf-8")
    return out


if __name__ == "__main__":
    for n in (sys.argv[1:] or DOCS):
        print(build(n))
