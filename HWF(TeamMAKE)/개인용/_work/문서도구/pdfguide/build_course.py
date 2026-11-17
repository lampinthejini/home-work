"""코드읽기코스 md → 그림을 넣은 HTML (render.js 가 PDF 로 인쇄한다)."""
import base64
import re
import sys
from pathlib import Path

import markdown

import figs
import figs2
from build import CSS, LOGO, fixLists

NAME = "코드읽기코스_처음부터순서대로"
SRC = Path(r"C:\big21\hw-repo\HWF(TeamMAKE)\개인용\가이드") / f"{NAME}.md"
OUT = Path(__file__).parent / "html" / f"{NAME}.html"

# 글자 그림(<pre>) → SVG 로 바꾼다. (안에 든 글자, 그림, 설명)
REPLACE_PRE = [
    ("손님(브라우저)", figs.restaurant, "그림. 식당으로 보는 전체 구조"),
    ("drafting(작성 중)", figs.stateBoard, "그림. 응시 상태 말판 (status.py ALLOWED)"),
    ("optionalUser   ", figs2.guardLadder, "그림. 문지기 사다리 (deps.py)"),
    ("START → prepare", figs2.interviewGraph, "그림. 면접 진행표 (graph.py buildInterviewGraph)"),
]

# 머리글 뒤에 그림을 넣는다. (머리글 속 글자, 위치, 그림, 설명)
#   위치 "head" = 머리글 바로 뒤, "look" = 그 절의 첫 '👀 열어 볼 곳' 앞
SHOT = Path(__file__).parent / "shots"


def shot(name: str):
    def make() -> str:
        data = base64.b64encode((SHOT / f"{name}.png").read_bytes()).decode()
        return f'<img class="shot" src="data:image/png;base64,{data}" alt="">'
    return make


PLACE = [
    ("코스 전체 순서", "afterTable", figs2.courseMap, "그림. 코스 지도 — 13개 정류장"),
    ("정류장 1.", "look", figs.containers, "그림. 컨테이너 3묶음"),
    ("정류장 2.", "look", figs2.lifespanSteps, "그림. 서버가 켜질 때 (lifespan)"),
    ("정류장 4.", "look", shot("01-login"), "화면. 로그인 (frontend/app/login/page.tsx)"),
    ("정류장 4.", "look", figs2.loginLoop, "그림. 로그인 한 바퀴 — 화면 → 카운터 → 창고 → 쿠키"),
    ("정류장 5.", "look", shot("02-jobs"), "화면. 공고 목록 (app/jobs/page.tsx)"),
    ("정류장 5.", "look", shot("03-job-detail"), "화면. 공고 상세 — [지원하기]가 createApplication 을 부른다"),
    ("정류장 5.", "look", shot("04-consent"), "화면. 동의 5개 (apply/…/consent)"),
    ("정류장 5.", "look", shot("06-resume-confirm"), "화면. 이력서 확인 — [이력서 제출]이 submitResume 을 부른다"),
    ("정류장 6.", "look", figs.questionFunnel, "그림. 질문 만들기 안전망"),
    ("정류장 7.", "look", shot("07-precheck"), "화면. 환경 점검 (Precheck.tsx)"),
    ("정류장 7.", "look", shot("08-rules"), "화면. 시작 안내 (apply/…/rules)"),
    ("정류장 7.", "look", shot("09-exam"), "화면. 면접 중 — 이 화면과 engine.py 가 WebSocket 으로 이야기한다"),
    ("정류장 7.", "look", figs2.letterPhone, "그림. 편지(HTTP)와 전화(WebSocket)"),
    ("정류장 8.", "look", shot("10-coding-intro"), "화면. 면접이 끝나고 코딩테스트 안내 (lifecycle.enterCoding)"),
    ("정류장 8.", "look", shot("11-coding"), "화면. 코딩테스트 (Coding.tsx)"),
    ("정류장 8.", "look", figs.sandbox, "그림. 코드 실행 상자의 겹겹 보호"),
    ("정류장 9.", "look", figs.scoringLanes, "그림. AI 와 코드의 역할 나누기"),
    ("정류장 10.", "head", shot("12-admin-postings"), "화면. 관리자 공고 목록 (admin/postings)"),
    ("정류장 10.", "head", shot("13-admin-edit"), "화면. 공고 수정 — 코딩테스트 토글과 평가 비율"),
    ("정류장 10.", "head", shot("14-admin-ai"), "화면. AI 공고 초안 (draftAi → posting_draft)"),
    ("정류장 10.", "head", shot("15-admin-applicant"), "화면. 지원자 상세 (applicantDetail)"),
    ("정류장 10.", "head", shot("16-admin-questions"), "화면. 예비 질문 — 종류 탭·NEW·해당 직무만 (admin/questions, 2026-11-16)"),
    ("정류장 10.", "head", shot("17-admin-company"), "화면. 회사 정보 — 이 글이 회사 질문과 AI 공고 초안에 들어간다 (admin/company, 2026-11-16)"),
    ("정류장 10.", "head", figs.layers, "그림. 요청 하나가 지나가는 층 — 관리자 창구도 같은 모양"),
    ("정류장 11.", "look", figs.dailyJobs, "그림. 하루 동안 자동으로 도는 일"),
    ("🧰 출발 전 준비물", "head", figs.funcMachine, "그림. 함수는 자판기"),
    ("🧰 출발 전 준비물", "head", figs.classMold, "그림. 클래스는 틀, 객체는 그 틀로 만든 하나하나"),
    ("(9줄 전부)", "head", figs2.upSh, "그림. up.sh 가 하는 일"),
    ("④ 팔찌 만들기", "head", figs2.tokenHashFig, "그림. 원본은 손님에게, 해시는 장부에"),
    ("③ 진행표 돌리기", "head", figs2.runLoop, "그림. runInterview 의 멈춤·이어가기 반복"),
    ("⑤ 답 기다리기", "head", figs2.collectChecks, "그림. collectAnswer 가 1초마다 하는 확인 네 가지"),
    ("놀이방 만들기:", "head", figs2.sandboxRoom, "그림. 놀이방 규칙표"),
    ("① 뒷주방 요리사", "head", figs2.evalPipeline, "그림. 면접 끝 → 채점 → 저장"),
    ("🧮 예시로 계산해 봐요", "para", figs2.scoreCalc, "그림. 점수 계산 따라 하기"),
]

EXTRA_CSS = """
pre { font-size: 8.4pt; page-break-inside: auto; }
h1 { page-break-before: always; }
figure svg { max-height: 120mm; }
img.shot { width: 100%; max-height: 105mm; object-fit: contain; border: 1px solid #ccd; border-radius: 4px; }
h2 code, h3 code { background: none; color: inherit; font-size: inherit; }
"""


def fig(fn, caption: str) -> str:
    return f"<figure>{fn()}<figcaption>{caption}</figcaption></figure>"


def headingAt(html: str, key: str) -> re.Match:
    m = re.search(r"<h[1-4]>(?:(?!</h).)*" + re.escape(key) + r"(?:(?!</h).)*</h[1-4]>", html, re.S)
    if not m:
        sys.exit(f"heading not found: {key}")
    return m


def place(html: str, key: str, where: str, block: str) -> str:
    if where == "para":
        i = html.find(key)
        if i < 0:
            sys.exit(f"text not found: {key}")
        at = html.find("</p>", i) + 4
        return html[:at] + block + html[at:]
    if where == "afterTable":
        i = html.find(key)
        at = html.find("</table>", i) + len("</table>")
        return html[:at] + block + html[at:]
    m = headingAt(html, key)
    if where == "head":
        at = m.end()
    else:  # look
        nxt = re.search(r"<h2>", html[m.end():])
        limit = m.end() + nxt.start() if nxt else len(html)
        i = html.find("<p>👀", m.end(), limit)
        if i < 0:
            sys.exit(f"👀 not found after: {key}")
        at = i
    return html[:at] + block + html[at:]


def main() -> None:
    md = fixLists(SRC.read_text(encoding="utf-8"))
    html = markdown.markdown(md, extensions=["tables", "fenced_code", "sane_lists"])
    html = re.sub(r"^<h1>.*?</h1>", "", html, count=1, flags=re.S)
    for needle, fn, caption in REPLACE_PRE:
        pat = re.compile(r"<pre><code>(?:(?!</pre>).)*?" + re.escape(needle.replace("<", "&lt;").replace(">", "&gt;")) + r".*?</pre>", re.S)
        if not pat.search(html):
            sys.exit(f"pre not found: {needle}")
        html = pat.sub(lambda _m: fig(fn, caption), html, count=1)
    # 같은 자리에 여러 그림이면 적은 순서대로 보이게 한다.
    # look 은 '👀 앞'에 넣어 기준점이 뒤로 밀리므로 앞에서부터, 나머지는 기준점이 그대로라 뒤에서부터 넣는다
    for key, where, fn, caption in PLACE:
        if where == "look":
            html = place(html, key, where, fig(fn, caption))
    for key, where, fn, caption in reversed(PLACE):
        if where != "look":
            html = place(html, key, where, fig(fn, caption))
    html = html.replace("<blockquote>\n<p>🔧", '<blockquote class="tech">\n<p>🔧')
    doc = f"""<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8"><title>코드 읽기 코스</title><style>{CSS}{EXTRA_CSS}</style></head><body>
<section class="cover"><img src="{LOGO}" alt="AIIT"><h1 style="page-break-before:auto">코드 읽기 코스</h1>
<div class="sub">처음부터 순서대로 — 13개 정류장, 정류장마다 코드 한 줄씩 읽기</div>
<div class="meta">AI 1차 채용면접 자동화 플랫폼 · Team AIIT · 2026-11-11 코드 기준 · 2026-11-16 일부 고침·화면 다시 찍음</div></section>
{html}</body></html>"""
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(doc, encoding="utf-8")
    print(OUT)


if __name__ == "__main__":
    main()
