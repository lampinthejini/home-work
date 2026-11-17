"""코드 읽기 코스 전용 SVG 도식 (figs.py 의 도구를 그대로 쓴다)."""

from figs import NAVY, arrow, box, diamond, num, path, svg, text

GRAY = "#55607a"


def courseMap():
    stops = [("1 전원 켜기", "gray"), ("2 main.py", "blue"), ("3 데이터 모양", "blue"), ("4 로그인 한 바퀴", "purple"),
             ("5 지원하기", "purple"), ("6 질문 만들기", "yellow"), ("7 면접 진행 ❤", "red"), ("8 코딩테스트", "orange"),
             ("9 채점·결과", "green"), ("10 관리자", "purple"), ("11 뒤에서 도는 일", "gray"), ("12 안전장치", "navy"),
             ("13 테스트", "green")]
    b = []
    w, h, gap = 140, 48, 22
    rows = [stops[0:5], stops[5:9], stops[9:13]]
    pos = []
    for r, row in enumerate(rows):
        y = 10 + r * 86
        for i, (s, col) in enumerate(row):
            idx = i if r % 2 == 0 else (4 - i)
            x = 10 + idx * (w + gap)
            pos.append((x, y))
            b.append(box(x, y, w, h, s, col, 13, True))
    for k in range(len(pos) - 1):
        (x1, y1), (x2, y2) = pos[k], pos[k + 1]
        if y1 == y2:
            if x2 > x1:
                b.append(arrow(x1 + w + 2, y1 + h / 2, x2 - 2, y2 + h / 2))
            else:
                b.append(arrow(x1 - 2, y1 + h / 2, x2 + w + 2, y2 + h / 2))
        else:
            b.append(arrow(x1 + w / 2, y1 + h + 2, x2 + w / 2, y2 - 2))
    b.append(text(405, 278, "정류장 1~4 를 먼저 · 4번(로그인 한 바퀴)을 이해하면 5번부터는 같은 모양의 반복", 12, GRAY, True))
    return svg(810, 292, b)


def upSh():
    b = []
    b.append(box(10, 10, 170, 50, "cd huge 폴더로\n(줄 4)", "gray", 12, True))
    b.append(arrow(182, 35, 218, 35))
    b.append(diamond(310, 35, 180, 56, "huge-front\n길 있나?"))
    b.append(arrow(402, 35, 438, 35, "없으면", lx=420, ly=22))
    b.append(box(440, 12, 150, 46, "create (만들기)", "blue", 12, True))
    b.append(text(310, 78, "있으면 그냥 지나감 (줄 5 · 6 같은 모양)", 11, GRAY, True))
    b.append(box(620, 10, 180, 50, "huge-internal\n바깥 문 없는 복도", "red", 12, True))
    b.append(arrow(592, 35, 618, 35))
    b.append(text(405, 112, "for part in infra ai app  (줄 7~9)", 14, NAVY, True))
    items = [("compose.infra.yml\n창고: DB·Redis·파일·메일", "gray"), ("compose.ai.yml\n요리사: LLM·STT·TTS…", "yellow"),
             ("compose.app.yml\n카운터·홀·일꾼", "blue")]
    for i, (s, col) in enumerate(items):
        x = 10 + i * 270
        b.append(box(x, 130, 250, 56, s, col, 12, True))
        if i < 2:
            b.append(arrow(x + 252, 158, x + 268, 158))
    b.append(text(405, 210, "각각  docker compose -f 파일 up -d --build   (-d = 뒤에서 실행, --build = 바뀐 코드로 새로 만들기)", 11, GRAY, True))
    return svg(810, 224, b)


def lifespanSteps():
    steps = [("표 만들기", "create_all", "gray"), ("칸 붙이기", "addColumns", "gray"), ("기본 데이터", "seedJobCodes", "gray"),
             ("파일 보관함", "ensureBucket", "gray"), ("하다 만 일 정리", "recoverAfterRestart", "orange"),
             ("책갈피 연결", "openSaver", "purple"), ("따로 출발", "warmUp · runForever", "yellow")]
    b = []
    w, gap = 102, 12
    for i, (a, c, col) in enumerate(steps):
        x = 10 + i * (w + gap)
        b.append(box(x, 10, w, 58, f"{a}\n{c}", col, 10, True))
        if i < len(steps) - 1:
            b.append(arrow(x + w + 1, 39, x + w + gap - 1, 39))
    b.append(box(10, 92, 790, 40, "yield  ─  여기서 문이 열린다. 서버가 손님(요청)을 받는 동안 이 줄에서 멈춰 있다", "green", 13, True))
    b.append(box(10, 150, 790, 36, "문 닫을 때: 따로 돌던 일 cancel · 책갈피 연결 closeSaver", "gray", 12))
    b.append(arrow(405, 134, 405, 148))
    return svg(810, 196, b)


def loginLoop():
    b = []
    cols = [(10, "화면 (브라우저)", "blue"), (290, "카운터 (FastAPI)", "purple"), (580, "창고 (PostgreSQL)", "gray")]
    for x, t, col in cols:
        b.append(box(x, 10, 220, 36, t, col, 13, True))
        b.append(f'<line x1="{x + 110}" y1="48" x2="{x + 110}" y2="400" stroke="#c5cee0" stroke-width="2" stroke-dasharray="4 4"/>')
    rows = [
        (70, 120, 400, "① submit → api(\"/auth/login\")\n→ fetch(\"/api/auth/login\")", "login/page.tsx · lib/api.ts"),
        (130, 400, 690, "② 이메일로 User 찾기 (FOR UPDATE)", "routers/auth.py:78"),
        (190, 690, 400, "③ password_hash 돌려줌", ""),
        (250, 400, 690, "④ verifyPassword OK → LoginSession 에\n토큰의 해시만 저장", "security.py:34"),
        (320, 400, 120, "⑤ Set-Cookie: huge_session=토큰\n(httponly) + redirect 주소", "auth.py:96"),
        (385, 120, 400, "⑥ 다음 요청마다 쿠키가 같이 감 → Depends 문지기", "deps.py"),
    ]
    for y, x1, x2, label, where in rows:
        b.append(arrow(x1, y, x2 - (8 if x2 > x1 else -8), y, color="#2f6fed"))
        mid = (x1 + x2) / 2
        b.append(text(mid, y - 18, label, 11, NAVY, True))
        if where:
            b.append(text(mid, y + 13, where, 10, GRAY))
    return svg(810, 410, b)


def guardLadder():
    b = []
    rungs = [("optionalUser", "쿠키 → resolveSession → 누구? (없어도 됨)", "-", "gray"),
             ("currentUser", "로그인 꼭 필요", "401", "blue"),
             ("activeUser", "초기 비밀번호 바꿨나?", "403", "purple"),
             ("requireApplicant / requireAdmin", "지원자만 / 관리자만", "403", "green")]
    for i, (n, d, code, col) in enumerate(rungs):
        x = 10 + i * 40
        y = 10 + i * 62
        b.append(box(x, y, 300, 46, n, col, 13, True))
        b.append(box(x + 310, y, 300, 46, d, col, 12))
        if code != "-":
            b.append(box(x + 620, y + 6, 60, 34, code, "red", 13, True))
        if i < len(rungs) - 1:
            b.append(path(f"M {x + 150} {y + 47} L {x + 190} {y + 60}"))
    b.append(box(130, 262, 560, 40, "창구 함수 실행 (예: createApplication)", "navy", 13, True))
    b.append(arrow(410, 232, 410, 260))
    b.append(text(405, 322, "한 칸이라도 raise 하면 창구 함수는 실행조차 되지 않는다", 12, GRAY, True))
    return svg(810, 336, b)


def letterPhone():
    b = []
    b.append(box(10, 10, 380, 40, "보통 요청 (HTTP) = 편지", "blue", 14, True))
    b.append(box(420, 10, 380, 40, "WebSocket = 전화", "red", 14, True))
    for i, s in enumerate(["화면 → 편지(요청) 한 장", "서버 → 답장 한 장", "끝. 또 하려면 새 편지"]):
        b.append(box(30, 66 + i * 46, 340, 36, s, "gray", 12))
    for i, s in enumerate(["한 번 연결해 두고 계속 주고받음", "화면 → 소리 조각(bytes) · 메시지(text)", "서버 → question · caption · warn · terminate"]):
        b.append(box(440, 66 + i * 46, 340, 36, s, "orange", 12))
    b.append(text(405, 220, "면접은 서로 계속 말해야 해서 전화(/ws/interview/{sessionId})를 쓴다", 12, GRAY, True))
    return svg(810, 234, b)


def interviewGraph():
    b = []
    b.append(box(10, 30, 90, 40, "START", "gray", 12, True))
    b.append(box(120, 30, 110, 40, "prepare\n질문 준비", "gray", 11, True))
    b.append(box(250, 30, 120, 40, "locate\n몇 번째 차례?", "blue", 11, True))
    b.append(box(410, 30, 100, 40, "ask\n질문 내기", "blue", 11, True))
    b.append(box(560, 30, 120, 40, "wait ⏸\n답 기다림", "red", 11, True))
    b.append(box(10, 130, 120, 44, "finish → END", "navy", 12, True))
    b.append(box(250, 130, 120, 44, "advance\n다음 질문으로", "green", 11, True))
    b.append(box(410, 130, 100, 44, "queue_\nfollowup", "orange", 11, True))
    b.append(box(560, 130, 120, 44, "transcribe\n받아쓰기", "purple", 11, True))
    b.append(box(380, 240, 150, 48, "followup\n꼬리질문 할까? (AI)", "yellow", 11, True))
    b.append(diamond(640, 264, 150, 64, "기본 질문\n이었나?"))
    b.append(arrow(102, 50, 118, 50))
    b.append(arrow(232, 50, 248, 50))
    b.append(arrow(372, 50, 408, 50, "있음", lx=390, ly=38))
    b.append(arrow(512, 50, 558, 50))
    b.append(arrow(620, 72, 620, 128, "interrupt → resume", lx=700, ly=100))
    b.append(arrow(630, 176, 638, 230))
    b.append(arrow(563, 264, 534, 264, "예", lx=548, ly=250))
    b.append(arrow(455, 238, 460, 178, "한다", lx=480, ly=208))
    b.append(arrow(460, 128, 460, 74, "다시 ask", lx=492, ly=100))
    b.append(arrow(380, 262, 336, 178, "안 한다", lx=338, ly=222))
    b.append(path("M 640 298 L 640 322 L 280 322 L 280 178"))
    b.append(text(460, 336, "아니오 (꼬리질문이었으면 또 붙이지 않음)", 10, GRAY, True))
    b.append(arrow(310, 128, 310, 74, "다음", lx=332, ly=100))
    b.append(arrow(250, 64, 74, 128, "10번 끝나면", lx=150, ly=86))
    return svg(810, 346, b)


def runLoop():
    b = []
    b.append(box(10, 10, 250, 50, "① compiled.ainvoke({\"seq\": 0})\n진행표를 처음부터", "blue", 12, True))
    b.append(arrow(262, 35, 298, 35))
    b.append(box(300, 10, 210, 50, "wait 칸 interrupt\n⏸ 일시정지하고 돌아옴", "red", 12, True))
    b.append(arrow(512, 35, 548, 35))
    b.append(box(550, 10, 250, 50, "② collectAnswer()\n답이 끝날 때까지 기다림", "orange", 12, True))
    b.append(path("M 675 62 L 675 100 L 405 100 L 405 64"))
    b.append(text(540, 116, "③ ainvoke(Command(resume=끝난 이유)) → wait 칸부터 이어서 → 다음 질문 → 다시 ⏸", 12, NAVY, True))
    b.append(box(200, 140, 410, 40, "__interrupt__ 가 없으면 (finish 도착) → 반복 끝", "green", 12, True))
    b.append(text(405, 202, "책갈피(체크포인트, thread_id = 지원 번호) 덕분에 끊겼다 다시 와도 locate 가 이어 낼 질문을 찾는다", 11, GRAY, True))
    return svg(810, 214, b)


def collectChecks():
    b = []
    checks = [("연결 끊김?", "SessionEnded\n(이 답은 저장 안 함)", "red"), ("경고창 떠 있음?", "확인 누를 때까지\n기다렸다 다시", "orange"),
              ("시간 다 됨?", "\"timeout\"", "yellow"), ("\"답변 끝\" 받음?\n(최대 1초)", "\"done\"", "green")]
    for i, (q, a, col) in enumerate(checks):
        x = 10 + i * 200
        b.append(diamond(x + 90, 50, 170, 70, q))
        b.append(arrow(x + 90, 87, x + 90, 113, "예", lx=x + 106, ly=100))
        b.append(box(x + 10, 115, 160, 50, a, col, 11, True))
        if i < 3:
            b.append(arrow(x + 176, 50, x + 202, 50, "아니오", lx=x + 190, ly=30))
    b.append(path("M 790 50 L 802 50 L 802 190 L 4 190 L 4 50 L 8 50", dash=True))
    b.append(text(405, 205, "네 가지 모두 아니면 1초 뒤 처음부터 다시 확인 (while True)", 11, GRAY, True))
    return svg(810, 216, b)


def evalPipeline():
    b = []
    b.append(box(10, 10, 160, 50, "lifecycle.finish\n면접 끝", "blue", 11, True))
    b.append(arrow(172, 35, 198, 35))
    b.append(box(200, 10, 170, 50, "enqueueEvaluation\nRedis 줄에 주문표", "gray", 11, True))
    b.append(arrow(372, 35, 398, 35))
    b.append(box(400, 10, 180, 50, "worker-eval\nevaluateTask", "orange", 11, True))
    b.append(arrow(582, 35, 608, 35))
    b.append(box(610, 10, 190, 50, "🚩 깃발 꽂기 (nx=True)\n이미 있으면 locked", "yellow", 11, True))
    steps = [("수상한 답변?", "red"), ("문항별 채점\n(AI 0~5점+근거)", "purple"), ("점수 계산\n(계산기·합불)", "green"),
             ("이유·총평\n(AI 글쓰기)", "purple"), ("save\n결과 저장", "blue")]
    for i, (s, col) in enumerate(steps):
        x = 10 + i * 160
        b.append(box(x, 100, 140, 52, s, col, 11, True))
        if i < 4:
            b.append(arrow(x + 142, 126, x + 158, 126))
    b.append(path("M 705 62 L 705 80 L 80 80 L 80 98"))
    b.append(text(405, 172, "AI 없음 → 나중에 다시 (postponed) · 그 밖의 실패 → 몇 번 재시도 (retry) · 수상하거나 너무 오래 → 관리자에게 (needs_review)", 11, GRAY, True))
    return svg(810, 186, b)


def scoreCalc():
    b = []
    b.append(text(405, 16, "전문성 항목을 본 질문 3개: AI 점수 4 · 5 · 3 (5점 만점)", 13, NAVY, True))
    b.append(box(10, 32, 240, 50, "① itemScores\n평균 4 ÷ 5 × 100 = 80", "purple", 12, True))
    b.append(arrow(252, 57, 278, 57))
    b.append(box(280, 32, 250, 50, "② interviewScore\nΣ 항목 점수 × 비율 = 77.50", "blue", 12, True))
    b.append(arrow(532, 57, 558, 57))
    b.append(box(560, 32, 240, 50, "③ totalScore", "green", 13, True))
    items = [("전문성", 80, 30), ("논리", 70, 25), ("관련성", 90, 20), ("전달력", 60, 10), ("조직 적합", 80, 15)]
    for i, (n, s, w) in enumerate(items):
        y = 100 + i * 24
        b.append(text(300, y, f"{n}", 11, NAVY, True, anchor="start"))
        b.append(f'<rect x="360" y="{y - 8}" width="{s * 0.8}" height="14" rx="3" fill="#cfe0ff"/>')
        b.append(text(432, y, f"{s} × {w}% = {s * w / 100:.2f}", 11, NAVY, anchor="start"))
    b.append(box(560, 100, 240, 46, "코딩 끔 → 77.50 그대로", "gray", 12, True))
    b.append(box(560, 156, 240, 62, "코딩 켬 (비율 30%, 코딩 50점)\n77.50×70% + 50×30%\n= 69.25", "orange", 11, True))
    b.append(box(10, 110, 260, 90, "④ 총점 ≥ 기준점 → 합격\n\nAI 는 0~5점과 근거만\n합불은 이 계산기가 정한다", "navy", 12, True))
    b.append(text(405, 236, "Decimal 로 계산해 소수 오차가 없고, roundScore 가 소수 둘째 자리에서 반올림", 11, GRAY, True))
    return svg(810, 250, b)


def tokenHashFig():
    b = []
    b.append(box(10, 30, 200, 50, "secrets.token_urlsafe(32)\n무작위 팔찌 번호", "yellow", 11, True))
    b.append(arrow(212, 45, 288, 25, "원본"))
    b.append(arrow(212, 65, 288, 95, "sha256 해시", lx=250, ly=100))
    b.append(box(290, 6, 250, 40, "쿠키로 손님에게만 (httponly)", "blue", 12, True))
    b.append(box(290, 76, 250, 40, "DB login_sessions 에는 해시만", "gray", 12, True))
    b.append(box(570, 30, 230, 60, "장부를 훔쳐봐도\n팔찌를 만들 수 없다", "green", 12, True))
    b.append(arrow(542, 96, 568, 70))
    return svg(810, 124, b)


def sandboxRoom():
    b = []
    b.append(box(10, 10, 170, 50, "지원자 코드\n+ 시험 입력 + 🔑암호", "purple", 11, True))
    b.append(arrow(182, 35, 218, 35, "create"))
    fill = "#fff3df"
    b.append(f'<rect x="220" y="4" width="380" height="150" rx="14" fill="{fill}" stroke="#d9822b" stroke-width="2"/>')
    b.append(text(410, 22, "놀이방 (일회용 컨테이너)", 13, NAVY, True))
    rules = ["🚫 인터넷", "🔒 읽기 전용", "👤 힘없는 계정", "💾 256MB", "⚙ CPU 1개", "👥 일꾼 64명", "⏱ 시간 제한", "🎫 특권 없음"]
    for i, r in enumerate(rules):
        x = 232 + (i % 4) * 92
        y = 40 + (i // 4) * 50
        b.append(box(x, y, 84, 40, r, "gray", 11, True))
    b.append(arrow(602, 60, 638, 60, "결과"))
    b.append(box(640, 32, 160, 56, "🔑 암호 뒤만 읽기\n→ judge 정답 비교", "green", 11, True))
    b.append(box(640, 104, 160, 46, "finally:\n놀이방 부수기 🧹", "red", 11, True))
    return svg(810, 162, b)
