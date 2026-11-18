"""가이드 PDF 에 넣을 SVG 도식. 모두 손으로 좌표를 잡은 그림이다."""

NAVY = "#1b2a4a"
BLUE = "#2f6fed"
C = {
    "blue": ("#eaf1ff", "#2f6fed"), "green": ("#e6f6ec", "#2e8b57"), "red": ("#fdecec", "#c0392b"),
    "orange": ("#fff3df", "#d9822b"), "gray": ("#f2f3f5", "#8a94a6"), "navy": ("#1b2a4a", "#1b2a4a"),
    "purple": ("#f1ecfd", "#7b52d3"), "yellow": ("#fffbe0", "#c9a400"),
}
FONT = "Malgun Gothic, sans-serif"


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def text(x, y, s, size=13, color=NAVY, bold=False, anchor="middle", lh=1.3):
    lines = s.split("\n")
    y0 = y - (len(lines) - 1) * size * lh / 2
    w = "700" if bold else "400"
    spans = "".join(f'<tspan x="{x}" y="{y0 + i * size * lh:.1f}">{esc(l)}</tspan>' for i, l in enumerate(lines))
    return f'<text font-family="{FONT}" font-size="{size}" font-weight="{w}" fill="{color}" text-anchor="{anchor}" dominant-baseline="middle">{spans}</text>'


def box(x, y, w, h, s, color="blue", size=13, bold=False, r=10, dash=False):
    fill, stroke = C[color]
    tc = "#ffffff" if color == "navy" else NAVY
    d = ' stroke-dasharray="6 4"' if dash else ""
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{fill}" stroke="{stroke}" stroke-width="1.6"{d}/>'
            + text(x + w / 2, y + h / 2, s, size, tc, bold))


def diamond(cx, cy, w, h, s, color="yellow", size=12):
    fill, stroke = C[color]
    pts = f"{cx},{cy - h / 2} {cx + w / 2},{cy} {cx},{cy + h / 2} {cx - w / 2},{cy}"
    return f'<polygon points="{pts}" fill="{fill}" stroke="{stroke}" stroke-width="1.6"/>' + text(cx, cy, s, size, NAVY, True)


def arrow(x1, y1, x2, y2, label="", color="#5b6b88", size=11, dash=False, lx=None, ly=None):
    d = ' stroke-dasharray="5 4"' if dash else ""
    out = f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="1.8" marker-end="url(#ah)"{d}/>'
    if label:
        out += text(lx if lx is not None else (x1 + x2) / 2, ly if ly is not None else (y1 + y2) / 2 - 9, label, size, "#3d4a63", True)
    return out


def path(d, color="#5b6b88", dash=False):
    da = ' stroke-dasharray="5 4"' if dash else ""
    return f'<path d="{d}" fill="none" stroke="{color}" stroke-width="1.8" marker-end="url(#ah)"{da}/>'


def svg(w, h, body):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="100%" style="max-width:{w}px">'
            '<defs><marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
            '<path d="M0,0 L10,5 L0,10 z" fill="#5b6b88"/></marker></defs>' + "".join(body) + "</svg>")


def chain(items, y, w, h, x0=10, gap=34, size=12):
    """가로 한 줄 흐름. items = [(글, 색)]"""
    out = []
    x = x0
    for i, (s, col) in enumerate(items):
        out.append(box(x, y, w, h, s, col, size, True))
        if i < len(items) - 1:
            out.append(arrow(x + w + 2, y + h / 2, x + w + gap - 2, y + h / 2))
        x += w + gap
    return out


def num(cx, cy, n, color=BLUE):
    return f'<circle cx="{cx}" cy="{cy}" r="12" fill="{color}"/>' + text(cx, cy + 1, str(n), 12, "#fff", True)


# ---------------------------------------------------------------- 지원자
def applicantFlow():
    b = []
    row1 = [("회원가입\n로그인", "gray"), ("공고 보기\n[지원하기]", "blue"), ("① 동의\n5가지", "blue"), ("② 이력서\n확인·제출", "blue"), ("③ 환경 점검\n5가지 통과", "blue")]
    row2 = [("④ 시작 안내\n[면접 시작]", "blue"), ("AI 면접\n질문 10 + 꼬리 ≤4", "purple"), ("코딩테스트\n(해당 공고만)", "orange"), ("응시 완료", "green"), ("결과 공개\n알림·메일", "green")]
    b += chain(row1, 20, 128, 58, 10, 34)
    b.append(path("M 714 78 L 714 108 L 74 108 L 74 136"))
    b += chain(row2, 138, 128, 58, 10, 34)
    b.append(text(400, 222, "질문 10개는 이력서를 제출하는 순간부터 AI가 미리 준비합니다 · 결과는 마감 다음 날 10:00에 공개", 12, "#55607a"))
    return svg(820, 236, b)


def interviewLoop():
    b = []
    b += chain([("질문을\n음성 + 자막으로", "blue"), ("3 · 2 · 1", "yellow"), ("말로 답변\n기본 90초 / 꼬리 60초", "purple"),
                ("[답변 완료]\n또는 시간 끝", "blue")], 30, 140, 62, 10, 34)
    b.append(arrow(672, 61, 698, 61))
    b.append(diamond(762, 61, 124, 78, "꼬리질문?"))
    b.append(path("M 762 100 L 762 150 L 602 150"))
    b.append(text(778, 124, "예", 11, "#2e8b57", True))
    b.append(box(440, 125, 160, 50, "AI가 한 번 더 질문\n(종류별 1개, 최대 4개)", "orange", 11, True))
    b.append(path("M 440 150 L 100 150 L 100 94"))
    b.append(path("M 824 61 L 850 61 L 850 205 L 50 205 L 50 94", dash=True))
    b.append(text(450, 221, "아니오 → 다음 기본 질문 (10개 끝나면 코딩테스트 또는 응시 완료)", 11, "#3d4a63", True))
    return svg(870, 234, b)


def disconnectTree():
    b = []
    b.append(box(300, 10, 220, 50, "면접 중 화면이 꺼지거나\n연결이 끊겼다", "gray", 13, True))
    b.append(arrow(410, 60, 410, 84))
    b.append(diamond(410, 120, 250, 70, "내가 직접 닫았나?"))
    b.append(path("M 285 120 L 150 120 L 150 170"))
    b.append(text(215, 108, "예", 12, "#c0392b", True))
    b.append(path("M 535 120 L 670 120 L 670 170"))
    b.append(text(600, 108, "아니오", 12, "#2e8b57", True))
    b.append(box(20, 172, 260, 92, "응시 종료\n새로고침 · 창 닫기 · 권한 끄기\n다시 응시할 수 없음\n답한 문항까지만 평가", "red", 12, True))
    b.append(box(540, 172, 260, 92, "장애 중단 (답변은 저장됨)\n인터넷 · 장치 · 서버 문제\n마이페이지에서 이어가기\n끊긴 질문부터 새 시간으로", "green", 12, True))
    b.append(arrow(670, 264, 670, 290))
    b.append(box(540, 292, 260, 52, "이어가기는 3번까지\n(서버 문제는 세지 않음)", "orange", 12, True))
    b.append(text(150, 300, "판단 기준: 나가기 직전에 브라우저가\n남긴 '나가요' 신호가 있는지", 11, "#55607a"))
    b.append(text(150, 335, "모르면 지원자에게 유리하게 '장애'", 11, "#55607a", True))
    return svg(820, 356, b)


def awayRule():
    b = []
    b.append(box(10, 30, 190, 70, "다른 탭·창으로 이동\n전체 화면 해제(ESC)", "gray", 12, True))
    b.append(arrow(204, 65, 254, 65, "1번째"))
    b.append(box(258, 30, 230, 70, "⚠ 경고 창\n확인하면 멈춘 시점의\n남은 시간부터 이어서", "orange", 12, True))
    b.append(arrow(492, 65, 542, 65, "2번째"))
    b.append(box(546, 30, 230, 70, "면접 자동 취소\n= 1차 불합격", "red", 13, True))
    b.append(text(394, 125, "탭을 한 번 바꿀 때 신호가 여러 개 와도, 3초 안의 신호는 '한 번'으로 셉니다", 11, "#55607a"))
    return svg(790, 140, b)


def resultTimeline():
    b = []
    b.append('<line x1="40" y1="70" x2="780" y2="70" stroke="#c5cee0" stroke-width="6" stroke-linecap="round"/>')
    pts = [(60, "응시 완료", "blue"), (220, "자동 채점\n(보통 몇 분)", "purple"), (400, "결과 공개\n마감 다음 날 10:00", "green"),
           (580, "녹화 삭제\n+3일", "orange"), (750, "응시 데이터 삭제\n공개일 +7일", "red")]
    for x, s, col in pts:
        fill, stroke = C[col]
        b.append(f'<circle cx="{x}" cy="70" r="11" fill="{stroke}"/>')
        b.append(text(x, 118, s, 12, NAVY, True))
    b.append(text(400, 26, "🔔 알림과 메일로 알려 드립니다 · 결과는 7일 동안 마이페이지에서 볼 수 있습니다", 12, "#55607a"))
    return svg(820, 150, b)


# ---------------------------------------------------------------- 관리자
def adminMenu():
    b = []
    items = [("▤ 공고 관리", "만들기 · 게시 · 마감", "blue"), ("▥ 지원자", "점수 · 리포트 · 비교", "purple"), ("▦ 다음 전형", "1차 합격자 연락처", "green"),
             ("▨ 예비 질문", "보기 · 고치기 · 삭제", "yellow"), ("▩ 회사 정보", "회사 소개 · 프로젝트 · 기술 글", "red"),
             ("▧ 대시보드", "통계 · 운영 현황", "orange"), ("⚙ 운영 설정", "동시 면접 상한", "gray")]
    for i, (t, d, col) in enumerate(items):
        x = 10 + (i % 4) * 199
        y = 10 + (i // 4) * 92
        b.append(box(x, y, 186, 76, f"{t}\n{d}", col, 13, True))
    return svg(810, 196, b)


def postingLife():
    b = []
    b += chain([("임시 저장\n(AI 초안 / 직접)", "gray"), ("게시\n접수 중", "blue"), ("마감\n(시각 지나면 1분 안 자동)", "orange"), ("결과 공개\n다음 날 10:00", "green"), ("데이터 삭제\n공개일 +7일", "red")], 20, 138, 62, 10, 25)
    b.append(text(79, 110, "삭제 가능\n(지원자 없음)", 11, "#c0392b", True))
    b.append(text(236, 110, "본문만 고치기 가능\n직무·기간은 잠김", 11, "#55607a"))
    b.append(text(399, 110, "진행 중 면접은 바로 끝\n남은 문항 0점", 11, "#55607a"))
    b.append(text(400, 150, "평가 기준(가중치·코딩테스트·합격 기준)은 첫 응시가 시작되면 잠깁니다", 12, NAVY, True))
    return svg(820, 166, b)


def scoringLanes():
    b = []
    b.append(box(10, 10, 140, 120, "AI가\n하는 일", "purple", 15, True))
    b.append(box(10, 150, 140, 120, "코드(규칙)가\n하는 일", "navy", 15, True))
    b.append(box(180, 30, 190, 80, "① 질문마다 항목별\n0~5점 + 근거 문장\n(4B, 온도 0)", "purple", 12, True))
    b.append(box(180, 170, 190, 80, "② 근거가 실제 답변에\n있는지 확인\n(90% 이상 같으면 인정)", "blue", 12, True))
    b.append(box(400, 170, 190, 80, "③ 가중치로 총점 계산\n④ 총점 ≥ 합격 기준\n→ 1차 합격", "blue", 12, True))
    b.append(box(620, 30, 190, 80, "⑤ 결과 '이유' 쓰기\n(8B, 결과는 못 바꿈)", "purple", 12, True))
    b.append(box(620, 170, 190, 80, "⑥ 이유 검사\n안 되면 1번 다시\n그래도 안 되면 평가 지연", "blue", 12, True))
    b.append(arrow(275, 110, 275, 168))
    b.append(arrow(372, 210, 398, 210))
    b.append(path("M 592 205 L 606 205 L 606 70 L 618 70"))
    b.append(arrow(715, 110, 715, 168))
    return svg(820, 282, b)


def reviewFlow():
    b = []
    b.append(box(10, 60, 170, 70, "평가 지연\n(채점 지시 의심 ·\n이유 검증 실패 등)", "orange", 12, True))
    b.append(path("M 180 80 L 240 40"))
    b.append(path("M 180 110 L 240 150"))
    b.append(box(242, 10, 230, 56, "[다시 돌리기] → 성공하면\n자동 결과로 공개", "blue", 12, True))
    b.append(box(242, 124, 230, 56, "3일 안에 담당자가\n합격·불합격 직접 결정", "green", 12, True))
    b.append(arrow(474, 152, 528, 152))
    b.append(box(530, 124, 270, 56, "지원자 화면에 '담당자 결정'", "green", 12, True))
    b.append(arrow(474, 38, 600, 38, dash=True))
    b.append(text(537, 26, "또 실패", 11, "#c0392b", True))
    b.append(box(602, 12, 198, 52, "계속 실패 → 평가 미완료\n(1차 불합격)", "red", 11, True))
    b.append(text(700, 90, "늦어도 7일 안에 결과 확정", 11, "#55607a", True))
    return svg(810, 192, b)


def dailyJobs():
    b = []
    b.append('<line x1="40" y1="60" x2="780" y2="60" stroke="#c5cee0" stroke-width="6" stroke-linecap="round"/>')
    for x, t, s, col in [(70, "00:00", "", "gray"), (180, "03:00", "보관 기간 지난\n데이터 삭제", "red"), (330, "09:00", "삭제 2일 전\n관리자 안내", "orange"),
                         (480, "10:00", "결과 공개\n(5분 안)", "green"), (750, "24:00", "", "gray")]:
        fill, stroke = C[col]
        b.append(f'<circle cx="{x}" cy="60" r="9" fill="{stroke}"/>')
        b.append(text(x, 32, t, 12, NAVY, True))
        if s:
            b.append(text(x, 102, s, 11, NAVY))
    b.append(box(560, 84, 230, 54, "항상: 1분마다 마감·자리 정리\n5분마다 결과 공개 점검", "blue", 11, True))
    return svg(820, 150, b)


# ---------------------------------------------------------------- 개발자
def restaurant():
    b = []
    rows = [("홀 (손님이 보는 곳)", "화면 · Next.js · frontend/", "blue"), ("카운터 (주문 받기)", "API · FastAPI · routers/", "purple"),
            ("주방 (요리)", "기능 · services/  ·  규칙표 · domain/", "green"), ("뒷주방 (오래 걸리는 요리)", "Celery 작업자 · worker.py (채점·메일·시간표)", "orange"),
            ("요리사 (AI)", "llm-rt 4B · llm-eval 8B · stt · tts · ocr · embed", "yellow"), ("창고", "PostgreSQL 장부 · Redis 메모판 · RustFS 파일", "gray")]
    for i, (a, d, col) in enumerate(rows):
        y = 10 + i * 58
        b.append(box(10, y, 230, 46, a, col, 13, True))
        b.append(box(260, y, 540, 46, d, col, 13))
        if i < len(rows) - 1:
            b.append(arrow(125, y + 47, 125, y + 57))
    return svg(810, 360, b)


def containers():
    b = []
    groups = [(10, "infra (창고)", "gray", ["PostgreSQL + pgvector", "Redis", "RustFS (파일)", "Mailpit (메일)"]),
              (280, "ai (요리사)", "yellow", ["llm-rt  Qwen3 4B  [GPU]", "stt  Whisper  [GPU]", "llm-eval  Qwen3 8B  [CPU]", "tts · ocr · embed  [CPU]"]),
              (550, "app (홀·주방)", "blue", ["frontend  (Next.js)", "api  (FastAPI)", "worker · worker-eval", "worker-sandbox · scheduler"])]
    for x, title, col, items in groups:
        fill, stroke = C[col]
        b.append(f'<rect x="{x}" y="10" width="250" height="230" rx="12" fill="{fill}" stroke="{stroke}" stroke-width="1.6"/>')
        b.append(text(x + 125, 34, title, 15, NAVY, True))
        for i, it in enumerate(items):
            g = "GPU" in it
            b.append(box(x + 14, 56 + i * 44, 222, 36, it, "red" if g else "gray", 12, g))
    b.append(text(405, 262, "그래픽카드 6GB 에는 빨간 두 개만 (실측 5.4 / 6 GB) · 코드만 고치면 app 묶음만 다시 빌드", 12, "#55607a", True))
    return svg(810, 276, b)


def stateBoard():
    """domain/status.py ALLOWED 를 그대로 옮긴 그림."""
    b = []
    # 왼쪽 위: 안내와 범례
    b.append(text(150, 24, "표(ALLOWED)에 없는 칸으로는\n갈 수 없다 → transition() 오류", 11, "#55607a", True))
    b.append(arrow(30, 70, 72, 70))
    b.append(text(80, 70, "끊김", 11, "#3d4a63", True, "start"))
    b.append(arrow(140, 70, 182, 70, dash=True))
    b.append(text(190, 70, "이어가기", 11, "#3d4a63", True, "start"))
    # 위: 장애 중단
    b.append(box(360, 10, 150, 46, "장애 중단\ninterrupted", "yellow", 12, True))
    # 가운데 줄
    b.append(box(10, 110, 110, 50, "작성 중\ndrafting", "gray", 12, True))
    b.append(box(150, 110, 110, 50, "준비됨\nready", "blue", 12, True))
    b.append(box(300, 110, 120, 50, "면접 중\ninterviewing", "purple", 12, True))
    b.append(box(460, 110, 110, 50, "코딩 중\ncoding", "orange", 12, True))
    b.append(arrow(122, 135, 148, 135))
    b.append(arrow(262, 135, 298, 135))
    b.append(arrow(422, 135, 458, 135))
    # 끊김(실선) · 이어가기(점선): 멈췄던 칸으로 돌아간다 (routers/interview.py target)
    b.append(arrow(345, 108, 395, 58))
    b.append(arrow(415, 58, 365, 108, dash=True))
    b.append(arrow(530, 108, 480, 58))
    b.append(arrow(460, 58, 510, 108, dash=True))
    b.append(text(670, 135, "이어가기는 멈췄던 칸으로\n(app.phase 로 기억)\n최대 3번 · 다 쓰면 응시 종료", 11, "#3d4a63", True))
    # 끊긴 채 마감
    b.append(text(640, 22, "끊긴 채 마감", 11, "#3d4a63", True))
    # 아래: 끝나는 칸 묶음 (면접 중·코딩 중 둘 다 이 네 칸으로 갈 수 있다)
    b.append(box(300, 214, 490, 66, "", "gray", 11, False, 12, True))
    for i, (s, col) in enumerate([("완료\ncompleted", "green"), ("응시 종료\nended", "red"),
                                  ("응시 취소\ncancelled", "red"), ("마감 종료\nended_closed", "orange")]):
        b.append(box(310 + i * 120, 226, 112, 42, s, col, 11, True))
    b.append(path("M 512 33 L 765 33 L 765 224"))
    b.append(arrow(360, 162, 360, 212))
    b.append(arrow(515, 162, 515, 212))
    b.append(text(545, 296, "면접 중·코딩 중에서 끝나는 네 칸 (코딩테스트 없는 공고는 면접 중 → 바로 완료)", 11, "#55607a", True))
    # 왼쪽 아래: 시작도 못 하고 마감
    b.append(box(20, 226, 220, 42, "미응시 마감\nnot_taken_closed", "gray", 11, True))
    b.append(arrow(65, 162, 95, 224))
    b.append(arrow(205, 162, 175, 224))
    b.append(text(130, 192, "마감", 11, "#3d4a63", True))
    return svg(800, 310, b)


def questionFunnel():
    b = []
    steps = [("① RAG: 비슷한 예비 질문 3개(유사도 0.5 이상) + 회사 정보·프로젝트·기술 글 → LLM이 새 질문 1개", "purple", 780),
             ("검사: 형식 · 요구 2개 이하 · 글 검사(찌꺼기·답변 방식 지시·말끝) · 이력서 근거 · 베낌 · 중복", "blue", 700),
             ("② 3번 실패 · 60초 초과 · 임베딩 고장 → 예비 질문 (쓴 것 · 같은 문장 제외)", "yellow", 620),
             ("③ 마지막 → 고정 문장 10개 중 안 쓴 것", "gray", 540)]
    for i, (s, col, w) in enumerate(steps):
        x = 10 + (780 - w) / 2
        b.append(box(x, 10 + i * 54, w, 44, s, col, 12, True))
    b.append(text(400, 236, "AI가 완전히 고장 나도 면접은 질문 10개로 진행된다 · 만든 AI 질문은 예비 질문에 쌓인다 (2026-11-16)", 12, "#55607a", True))
    return svg(800, 250, b)


def disconnectTimeline():
    b = []
    b.append(text(20, 20, "A. 인터넷이 끊김", 13, NAVY, True, "start"))
    b.append('<line x1="20" y1="50" x2="790" y2="50" stroke="#c5cee0" stroke-width="4"/>')
    for i in range(4):
        x = 40 + i * 70
        b.append(f'<rect x="{x - 4}" y="40" width="8" height="20" fill="#2e8b57"/>')
    b.append(text(150, 76, "heartbeat 5초마다 \"나 살아 있어\"", 11, "#2e8b57", True))
    b.append(f'<rect x="250" y="36" width="300" height="28" rx="6" fill="#fdecec" stroke="#c0392b" stroke-dasharray="5 4"/>')
    b.append(text(400, 50, "15초(3번) 동안 신호 없음", 12, "#c0392b", True))
    b.append(box(570, 30, 220, 40, "'나가요' 쪽지 없음 → 장애 중단", "green", 12, True))

    b.append(text(20, 120, "B. 창을 닫음", 13, NAVY, True, "start"))
    b.append('<line x1="20" y1="150" x2="790" y2="150" stroke="#c5cee0" stroke-width="4"/>')
    b.append(box(40, 134, 170, 32, "카메라·마이크 먼저 꺼짐", "orange", 11, True))
    b.append(f'<rect x="220" y="136" width="200" height="28" rx="6" fill="#fffbe0" stroke="#c9a400"/>')
    b.append(text(320, 150, "3초 기다림 (E18 고침)", 12, NAVY, True))
    b.append(box(430, 134, 120, 32, "'나가요' 쪽지", "blue", 11, True))
    b.append(box(570, 130, 220, 40, "쪽지 있음 → 응시 종료", "red", 12, True))
    b.append(text(405, 196, "예전에는 장치가 꺼지는 순간 '장치 고장 = 장애'로 정해서, 창을 닫은 사람이 이어가기를 받았다", 11, "#55607a"))
    return svg(810, 212, b)


def seatRace():
    b = []
    b.append(text(200, 16, "따로 하면 (경주 생김)", 13, "#c0392b", True))
    b.append(text(610, 16, "Lua로 한 번에 (안전)", 13, "#2e8b57", True))
    for i, (a, bb) in enumerate([("A: 읽기 1/2", "B: 읽기 1/2"), ("A: 자리 있네!", "B: 자리 있네!"), ("A: +1 → 2", "B: +1 → 3 ❌")]):
        y = 34 + i * 46
        b.append(box(10, y, 180, 36, a, "blue", 12, True))
        b.append(box(210, y, 180, 36, bb, "red" if i == 2 else "purple", 12, True))
    b.append(box(430, 34, 360, 50, "A: [읽기·비교·+1] 끼어들 틈 없이 → 2/2", "green", 12, True))
    b.append(box(430, 96, 360, 50, "B: [읽기·비교] 꽉 참 → 안내 모달", "orange", 12, True))
    b.append(text(400, 190, "+ E10: 자리를 잡고 DB에 저장하기 전 60초 동안 '입장 중' 표시를 남겨, 1분마다 숫자 맞추기가 놓치지 않게", 11, "#55607a", True))
    return svg(810, 206, b)


def sandbox():
    b = []
    layers = [("worker-sandbox만 Docker 열쇠를 가짐 (api는 없음)", "gray", 0), ("일회용 컨테이너 · 권한 없는 사용자(65534)", "blue", 30),
              ("인터넷 끊음 · 파일은 읽기만", "yellow", 60), ("메모리 256MB · CPU 1개 · 프로세스 64개 · 10초", "orange", 90)]
    for s, col, p in layers:
        fill, stroke = C[col]
        b.append(f'<rect x="{10 + p}" y="{10 + p * 0.9:.0f}" width="{780 - 2 * p}" height="{250 - p * 1.8:.0f}" rx="14" fill="{fill}" stroke="{stroke}" stroke-width="1.6"/>')
        b.append(text(400, 26 + p * 0.9, s, 12, NAVY, True))
    b.append(box(300, 128, 200, 50, "지원자 코드 🧪", "purple", 14, True))
    return svg(800, 270, b)


def quoteMatch():
    b = []
    b.append(box(10, 10, 790, 44, "지원자 답변: \"저는 동아리에서 팀장을 맡아 일정을 관리했습니다\"", "gray", 13))
    b.append(box(10, 74, 380, 60, "AI 근거: \"동아리에서 팀장을 맡아서 일정을 관리\"\n(한 글자 다름)", "purple", 12))
    b.append(box(420, 74, 380, 60, "AI 근거: \"리더십 상을 받았습니다\"\n(답변에 없음)", "purple", 12))
    b.append(arrow(200, 136, 200, 160))
    b.append(arrow(610, 136, 610, 160))
    b.append(box(10, 162, 380, 60, "90% 이상 같음 → ✅ 인정\n저장은 답변 속 원래 구절로", "green", 12, True))
    b.append(box(420, 162, 380, 60, "비슷한 구절 없음 → ❌ 거절\n그 항목은 1점", "red", 12, True))
    return svg(810, 234, b)


def precheckRace():
    b = []
    b.append(text(205, 16, "예전 (겹쳐 보냄)", 13, "#c0392b", True))
    b.append(text(615, 16, "지금 (줄 세워 차례로)", 13, "#2e8b57", True))
    b.append(box(10, 30, 190, 36, "① 장치 미확인 요청", "gray", 12, True))
    b.append(box(210, 30, 190, 36, "② 통과 요청", "blue", 12, True))
    b.append(box(210, 76, 190, 36, "② 답: 통과 ✅", "green", 12, True))
    b.append(box(10, 122, 190, 36, "① 답(늦게): 실패", "red", 12, True))
    b.append(box(10, 168, 390, 36, "서버의 통과 표시가 지워짐 → 시작 실패", "red", 12, True))
    b.append(box(420, 30, 380, 36, "① 요청 → ① 답", "gray", 12, True))
    b.append(arrow(610, 68, 610, 90))
    b.append(box(420, 92, 380, 36, "② 요청 → ② 답: 통과 ✅ (마지막이 남음)", "green", 12, True))
    b.append(text(610, 160, "checkQueue: 앞 요청이 끝나야 다음을 보낸다", 12, "#55607a", True))
    return svg(810, 214, b)


def layers():
    b = []
    rows = [("화면", "frontend/app/.../page.tsx", "버튼 → api(\"POST /...\")", "blue"),
            ("API 함수", "routers/*.py", "로그인·권한 검사(deps), 입력 검사(schemas)", "purple"),
            ("기능", "services/*.py · interview/*.py", "실제 일: 질문 만들기, 채점, 면접 진행", "green"),
            ("규칙", "domain/*.py", "상태 이동·점수 계산 (DB·AI 없음)", "yellow"),
            ("장부", "models.py → PostgreSQL", "표에 읽고 쓰기", "gray")]
    for i, (a, f, d, col) in enumerate(rows):
        y = 10 + i * 56
        b.append(box(10, y, 130, 44, a, col, 14, True))
        b.append(box(150, y, 250, 44, f, col, 12))
        b.append(box(410, y, 390, 44, d, col, 12))
        if i < len(rows) - 1:
            b.append(arrow(75, y + 45, 75, y + 55))
    b.append(text(405, 296, "오래 걸리는 일(채점·메일)은 기능 층에서 worker.py(Celery)로 넘긴다", 12, "#55607a", True))
    return svg(810, 310, b)


def funcMachine():
    b = []
    b.append(box(10, 40, 190, 70, "넣는 것 (인자)\npassword = \"abc123!\"", "blue", 12, True))
    b.append(arrow(204, 75, 268, 75))
    b.append(f'<rect x="270" y="10" width="260" height="130" rx="16" fill="#1b2a4a"/>')
    b.append(text(400, 45, "자판기 = 함수", 15, "#ffffff", True))
    b.append(text(400, 80, "hashPassword", 16, "#ffd34d", True))
    b.append(text(400, 112, "(안에서 Argon2 로 갈기)", 11, "#c8d3ea"))
    b.append(arrow(532, 75, 596, 75))
    b.append(box(598, 40, 200, 70, "나오는 것 (반환값)\n$argon2id$v=19$…", "green", 12, True))
    b.append(text(400, 162, "부르기(호출):  result = hashPassword(\"abc123!\")", 12, "#3d4a63", True))
    return svg(810, 178, b)


def classMold():
    b = []
    b.append(box(10, 30, 220, 110, "클래스 (틀)\nLiveSession\n\n할 줄 아는 일(메소드):\nsend · watchdog · endWith", "navy", 12, True))
    for i, (who, col) in enumerate([("민지의 면접 직원\n(객체 1)", "blue"), ("지수의 면접 직원\n(객체 2)", "green"), ("현우의 면접 직원\n(객체 3)", "orange")]):
        y = 10 + i * 52
        b.append(path(f"M 232 85 L 300 {y + 22}"))
        b.append(box(302, y, 200, 44, who, col, 12, True))
        b.append(text(650, y + 22, f"self.appId = 각자 지원서 · self.state = 각자 상태", 11, "#55607a", anchor="middle"))
    return svg(810, 170, b)
