"""기능별 UML 활동 다이어그램 정의. python diagrams.py → html/*.html, mermaid/*.mmd"""
from pathlib import Path

from uml import Diagram

APPLICANT = ("applicant", "지원자", 1)
ADMIN = ("admin", "관리자", 1)


def bar(d, left, right):
    """(레인, 칸) 두 점 사이를 덮는 병렬 분기 막대의 (가운데, 너비)."""
    x1, x2 = d.colX(*left), d.colX(*right)
    return ((x1 + x2) / 2, x2 - x1 + 70)


def login():
    d = Diagram("01. 로그인", [("user", "사용자", 1), ("front", "프론트엔드 (Next.js)", 2), ("api", "백엔드 API (FastAPI)", 2), ("db", "DB (PostgreSQL)", 1)],
                "POST /api/auth/login · 실패 잠금 · 세션 쿠키 발급")
    A = d.add
    A("s", "user", 0, "start")
    A("n1", "user", 1, "action", "이메일·비밀번호 입력\n[로그인] 클릭")
    A("d1", "front", 2, "decision", "필수 입력값\n모두 있음?")
    A("f1", "front", 2, "action", "입력 안내 메시지 표시", col=1)
    A("ff1", "front", 3, "flowfinal", col=1)
    A("n2", "front", 3, "action", "로그인 요청\nPOST /api/auth/login")
    A("n3", "api", 4, "action", "요청 수신\n접속 IP 확인")
    A("n4", "db", 5, "action", "IP 차단 상태 조회\n이메일로 사용자 조회\n(행 잠금)")
    A("d2", "api", 6, "decision", "인증 성공?\n(Argon2 검증·\n관리자 잠금 확인)")
    A("f2", "api", 6, "action", "실패 기록\n관리자: 계정 실패 횟수\nIP: 실패 횟수", col=1)
    A("d3", "api", 7, "decision", "IP 차단 중인\n지원자?")
    A("f3", "api", 7, "action", "오류 응답\n401 인증 실패 또는\n429 IP 차단", col=1)
    A("f4", "front", 8, "action", "오류 메시지 표시", col=1)
    A("ff2", "front", 9, "flowfinal", col=1)
    A("n5", "api", 8, "action", "실패 횟수 초기화\n로그인 세션 생성")
    A("n6", "db", 9, "action", "세션 저장\n(토큰 해시·만료 시각)")
    A("n7", "api", 10, "action", "HttpOnly 세션 쿠키 설정")
    A("d4", "api", 11, "decision", "사용자 역할?")
    A("n8", "api", 11, "action", "이동 경로: /admin/postings\n(초기 비밀번호면\n비밀번호 변경 화면)", col=1)
    A("n9", "api", 12, "action", "이동 경로:\nnext 경로 또는 /jobs")
    A("m1", "api", 13, "merge")
    A("n10", "api", 14, "action", "200 응답\n(user_id·role·redirect)")
    A("n11", "front", 15, "action", "사용자 정보 갱신\n응답 경로로 화면 이동")
    A("n12", "user", 16, "action", "목적 화면 표시")
    A("e", "user", 17, "final")
    E = d.edge
    E("s", "n1"); E("n1", "d1")
    E("d1", "f1", "아니요", out="right", inp="left"); E("f1", "ff1")
    E("d1", "n2", "예"); E("n2", "n3"); E("n3", "n4"); E("n4", "d2")
    E("d2", "f2", "실패", out="right", inp="left"); E("f2", "f3")
    E("d2", "d3", "성공"); E("d3", "f3", "예", out="right", inp="left")
    E("f3", "f4", mid=d.rowY(8) - 34); E("f4", "ff2")
    E("d3", "n5", "아니요"); E("n5", "n6"); E("n6", "n7"); E("n7", "d4")
    E("d4", "n8", "관리자", out="right", inp="left"); E("d4", "n9", "지원자")
    E("n9", "m1"); E("n8", "m1", inp="right"); E("m1", "n10"); E("n10", "n11"); E("n11", "n12"); E("n12", "e")
    return d, ["세션은 활동이 없으면 2시간 뒤 만료된다(운영 설정 session_idle_hours). 요청이 올 때마다 만료 시각이 늘어난다.",
               "로그아웃은 서버 세션 삭제 + 쿠키 삭제. 비밀번호 변경·재설정 때는 다른 기기의 세션도 지운다."]


def apply():
    d = Diagram("02. 지원서 작성 (지원 → 동의 → 이력서 제출)",
                [APPLICANT, ("front", "프론트엔드", 2), ("api", "백엔드 API", 2), ("worker", "백그라운드 작업", 1), ("db", "DB·파일 저장소", 1)],
                "POST /applications → /consent → /resume/upload(선택) → /resume")
    A = d.add
    A("s", "applicant", 0, "start")
    A("a1", "applicant", 1, "action", "공고 상세에서\n[지원하기]")
    A("a2", "front", 2, "action", "지원 요청\nPOST /applications")
    A("d1", "api", 3, "decision", "지원 가능?\n(게시 중·접수 기간\n·직무·중복 확인)")
    A("x1", "api", 3, "action", "409·400 오류 응답", col=1)
    A("ff1", "api", 4, "flowfinal", col=1)
    A("a3", "db", 4, "action", "지원 생성\nattempt_status = drafting")
    d.note("api", 5.15, "같은 공고에 작성 중(drafting)인\n지원이 있으면 새로 만들지 않고\n그 건을 이어서 쓴다", col=1)
    A("a4", "applicant", 5, "action", "필수 동의 5개 항목 체크")
    A("a5", "front", 6, "action", "동의 제출\nPOST …/consent")
    A("d2", "api", 7, "decision", "모두 동의 +\n문구 버전 일치?")
    A("x2", "api", 7, "action", "400·409 오류 응답", col=1)
    A("ff2", "api", 8, "flowfinal", col=1)
    A("a6", "db", 8, "action", "동의 기록 저장\n(이메일 해시·버전·항목)")
    A("d3", "front", 9, "decision", "이력서 작성 방식?")
    A("u1", "front", 9, "action", "파일 업로드\nPOST …/resume/upload", col=1)
    A("u2", "api", 10, "action", "형식·크기 검사\n파일 저장 후 202 응답", col=1)
    A("u3", "worker", 11, "action", "이력서 추출 (비동기)\nPDF 텍스트 / 이미지 OCR\n→ LLM 항목 정리")
    A("u4", "front", 12, "action", "추출 상태 조회 (폴링)\n결과로 양식 채우기", col=1)
    A("a7", "front", 10, "action", "빈 양식 표시")
    A("m1", "front", 13, "merge")
    A("a8", "applicant", 14, "action", "내용 확인·수정\n[이력서 제출]")
    A("a9", "front", 15, "action", "이력서 제출\nPOST …/resume")
    A("d4", "api", 16, "decision", "동의·접수 기간·\n필수 항목 충족?")
    A("x3", "api", 16, "action", "409·400 오류 응답", col=1)
    A("ff3", "api", 17, "flowfinal", col=1)
    A("a10", "db", 17, "action", "이력서 스냅샷 저장\ndrafting → ready\n평가 기준 버전 고정")
    A("b1", "api", 18, "bar", w=bar(d, ("front", 0), ("worker", 0)))
    A("a11", "front", 19, "action", "응답 수신 (마감·결과 공개 시각)\n환경 점검 화면으로 이동")
    A("e", "front", 20, "final")
    A("a12", "worker", 19, "action", "면접 질문 생성 시작\n(→ 03 질문 생성)")
    A("ff4", "worker", 20, "flowfinal")
    E = d.edge
    E("s", "a1"); E("a1", "a2"); E("a2", "d1")
    E("d1", "x1", "아니요", out="right", inp="left"); E("x1", "ff1")
    E("d1", "a3", "예"); E("a3", "a4"); E("a4", "a5"); E("a5", "d2")
    E("d2", "x2", "아니요", out="right", inp="left"); E("x2", "ff2")
    E("d2", "a6", "예"); E("a6", "d3")
    E("d3", "u1", "파일 업로드", out="right", inp="left"); E("u1", "u2"); E("u2", "u3"); E("u3", "u4")
    E("d3", "a7", "직접 작성"); E("a7", "m1"); E("u4", "m1", inp="right")
    E("m1", "a8"); E("a8", "a9"); E("a9", "d4")
    E("d4", "x3", "아니요", out="right", inp="left"); E("x3", "ff3")
    E("d4", "a10", "예"); E("a10", "b1")
    E("b1", "a11"); E("a11", "e"); E("b1", "a12"); E("a12", "ff4")
    return d, ["업로드한 파일은 추출 결과를 지원자가 확인·수정한 뒤 제출한다. 제출 전까지는 drafting 이라 다시 고칠 수 있다."]


def compose():
    d = Diagram("03. 면접 질문 생성 (질문 구성 그래프, LangGraph)",
                [("worker", "백그라운드 작업 (질문 구성 그래프)", 3), ("ai", "AI 서비스 (임베딩·LLM·TTS)", 1), ("db", "DB·파일 저장소", 1)],
                "기본 질문 10개를 한 자리씩 채운다. 이력서 제출 직후 시작하고, 면접 시작 때 안 끝났으면 다시 시작한다.")
    A = d.add
    A("s", "worker", 0, "start", col=2)
    A("w1", "worker", 1, "action", "questions_status = composing\n시간 예산 설정\n직무 관련 최근 소식 찾기(30초)", col=2)
    A("w2", "worker", 2, "action", "다음 자리의 질문 종류 결정\n(10개 순서표)", col=2)
    A("d1", "worker", 3, "decision", "RAG 사용 가능·\n시간 남음?", col=2)
    A("a1", "ai", 4, "action", "질의 임베딩 생성\n(공고·이력서 요약)")
    A("a2", "db", 5, "action", "같은 종류 예비 질문\n예시 유사도 검색\n(pgvector, 0.5 이상)")
    A("d2", "worker", 6, "action", "가까운 예시만 남김\n(0.5 미만은 빼고,\n없으면 주제만으로)", col=2)
    A("a3", "ai", 7, "action", "LLM 질문 1개 생성\n(예시·이력서·공고 요약·\n회사/직무 소식, 고른 것 제외)")
    A("d3", "worker", 8, "decision", "검사 통과?\n(형식·근거·\n베낌·중복)", col=2)
    A("d4", "worker", 8, "decision", "재생성 한도\n남음? (3회)", col=1)
    A("bk", "worker", 9, "action", "예비 질문으로 대체\n→ 없으면 고정 문장\n(대체 사유 기록)", col=0)
    A("ac", "worker", 9, "action", "질문 채택\n(출처: 생성)", col=2)
    A("m1", "worker", 10, "merge", col=2)
    A("d5", "worker", 11, "decision", "10개 모두 채움?", col=2)
    A("a4", "db", 12, "action", "질문 10개 저장 · ready\nAI 질문은 예비 질문에도\n(직무 소식은 지움)")
    A("a5", "ai", 13, "action", "TTS: 질문 음성 미리 생성\n(실패한 질문은 자막만)")
    A("a6", "db", 14, "action", "음성 파일 저장")
    A("e", "db", 15, "final")
    d.note("worker", 12.2, "임베딩·LLM 장애나 시간 예산 초과가\n생기면 남은 자리는 기다리지 않고\n바로 예비 질문으로 채운다", col=0)
    E = d.edge
    E("s", "w1"); E("w1", "w2"); E("w2", "d1")
    E("d1", "bk", "아니요", out="left", inp="top")
    E("d1", "a1", "예"); E("a1", "a2"); E("a2", "d2")
    E("d2", "a3"); E("a3", "d3")
    E("d3", "d4", "아니요", out="left", inp="right")
    E("d4", "a3", "예", out="top", inp="left")
    E("d4", "bk", "아니요", out="bottom", inp="right")
    E("d3", "ac", "예"); E("ac", "m1"); E("bk", "m1", out="bottom", inp="left")
    E("m1", "d5")
    E("d5", "w2", "아니요", out="left", inp="left", xm=d.lx["worker"][0] + 8)
    E("d5", "a4", "예"); E("a4", "a5"); E("a5", "a6"); E("a6", "e")
    return d, ["질문 종류 순서: 인성·회사·이력서·이력서·직무×4·인성·회사. 이력서 질문은 경력·프로젝트가 없으면 바로 대체한다.",
               "질문 바꾸기(대체)는 감점이나 장애가 아니다. 대체 사유는 질문마다 기록한다."]


def interview():
    d = Diagram("04. AI 면접 진행", [APPLICANT, ("front", "프론트엔드", 2), ("api", "백엔드 API · 면접 엔진 (WebSocket, LangGraph)", 3),
                                     ("ai", "AI 서비스 (STT·LLM)", 1), ("db", "DB·파일 저장소", 1)],
                "환경 점검 → 시작 → 질문·답변 반복(기본 10개 + 꼬리질문) → 종료. 이탈·끊김은 05·06 참고.")
    A = d.add
    A("s", "applicant", 0, "start")
    A("a1", "applicant", 1, "action", "환경 점검\n(마이크·카메라·\n스피커·네트워크)")
    A("a2", "front", 2, "action", "점검 결과 전송\nPOST …/precheck")
    A("d1", "api", 3, "decision", "모든 항목 통과?\n(AI 서버 포함)")
    A("f1", "front", 3, "action", "실패 항목 표시", col=1)
    A("a3", "db", 4, "action", "점검 통과 유효시간 기록\n(15분)")
    A("a4", "applicant", 5, "action", "응시 규칙 확인\n[면접 시작]")
    A("a5", "front", 6, "action", "전체 화면 전환\nPOST …/interview/start")
    A("d2", "api", 7, "decision", "시작 가능?\n(1회 응시·접수 중\n·점검·동시 자리)")
    A("x1", "api", 7, "action", "409·429 오류 응답", col=1)
    A("ff1", "api", 8, "flowfinal", col=1)
    A("a6", "db", 8, "action", "ready → interviewing\n면접 세션 생성")
    A("a7", "front", 9, "action", "WebSocket 연결\n카메라 녹화 시작\n(10초 조각 업로드)")
    A("d3", "api", 10, "decision", "면접 질문 준비됨?")
    A("x2", "api", 10, "action", "준비 진행률 전송\n질문 생성 끝까지 대기", col=1)
    A("m1", "api", 11, "merge")
    A("a8", "api", 12, "action", "질문 전송 (글·TTS 음성)\n첫 질문 때 응시 횟수 사용·\n평가 기준 잠금")
    A("a9", "front", 13, "action", "질문 재생 → 3초 카운트다운\n→ 답변 녹음·실시간 자막")
    A("a10", "applicant", 14, "action", "답변 후 [답변 완료]\n(또는 답변 시간 종료)")
    A("a11", "ai", 15, "action", "STT: 답변 음성 → 글자\n(실패 시 재시도)")
    A("a12", "db", 16, "action", "답변 저장\n(글자·음성 파일)")
    A("d4", "api", 17, "decision", "방금 질문이\n기본 질문?")
    A("a13", "ai", 17, "action", "LLM: 꼬리질문 필요\n판단·질문 생성")
    A("d5", "api", 18, "decision", "꼬리질문 채택?\n(한도·시간·\n금지 주제)", col=2)
    d.note("api", 15.4, "꼬리질문은 기본 질문 하나에\n최대 1개, 면접 전체 최대 4개", col=2)
    A("a14", "api", 19, "action", "꼬리질문 저장\n다음 질문으로 지정", col=2)
    A("a15", "api", 19, "action", "다음 기본 질문 번호로", col=1)
    A("d6", "api", 20, "decision", "남은 기본\n질문 있음?", col=1)
    A("m2", "api", 21, "merge", col=1)
    A("f2", "api", 22, "action", "기본 질문 10개 종료\n면접 자리 반환")
    A("d7", "api", 23, "decision", "코딩테스트\n적용 공고?")
    A("c1", "api", 23, "action", "interviewing → coding\n문제 배정\n(→ 07 코딩테스트)", col=1)
    A("ef", "api", 24, "final", col=1)
    A("f3", "api", 24, "action", "interviewing → completed\n채점 작업 대기열 등록\n(→ 08 채점)")
    A("f4", "front", 25, "action", "응시 완료 화면")
    A("e", "front", 26, "final")
    E = d.edge
    E("s", "a1"); E("a1", "a2"); E("a2", "d1")
    E("d1", "f1", "아니요", out="left", inp="right"); E("f1", "a1", out="top", inp="right")
    E("d1", "a3", "예"); E("a3", "a4"); E("a4", "a5"); E("a5", "d2")
    E("d2", "x1", "아니요", out="right", inp="left"); E("x1", "ff1")
    E("d2", "a6", "예"); E("a6", "a7"); E("a7", "d3")
    E("d3", "x2", "아니요", out="right", inp="left"); E("x2", "m1")
    E("d3", "m1", "예"); E("m1", "a8"); E("a8", "a9"); E("a9", "a10"); E("a10", "a11"); E("a11", "a12"); E("a12", "d4")
    E("d4", "a13", "예", out="right", inp="left"); E("a13", "d5")
    E("d5", "a14", "예"); E("d5", "a15", "아니요", out="left", inp="top")
    E("d4", "a15", "아니요"); E("a15", "d6")
    E("d6", "m2", "예"); E("a14", "m2", out="bottom", inp="right")
    E("m2", "m1", out="left", inp="left", xm=d.lx["api"][0] + 8)
    E("d6", "f2", "아니요", out="left", inp="top")
    E("f2", "d7")
    E("d7", "c1", "예", out="right", inp="left"); E("c1", "ef")
    E("d7", "f3", "아니요"); E("f3", "f4"); E("f4", "e")
    return d, ["답변 시간은 기본 질문 90초, 꼬리질문 60초. 답변 중 음성은 WebSocket 으로 계속 보내고, 끝나면 서버가 STT 로 바꿔 저장한다.",
               "면접 진행표(LangGraph)는 답을 기다리는 동안 멈추고, 상태를 DB 체크포인트에 저장해 서버가 다시 켜져도 이어갈 수 있다."]


def away():
    d = Diagram("05. 화면 이탈 처리", [APPLICANT, ("front", "프론트엔드", 1), ("api", "면접 엔진 (WebSocket)", 3), ("db", "DB", 1)],
                "탭 전환·창 이탈·전체 화면 해제: 1회 경고, 2회째 응시 취소")
    A = d.add
    A("s", "applicant", 0, "start")
    A("a1", "applicant", 1, "action", "탭 전환·창 이탈·\n전체 화면 해제")
    A("a2", "front", 2, "action", "이탈 신호 전송\n(WebSocket)")
    A("d1", "api", 3, "decision", "창 이탈이\n2초 미만?")
    A("ff1", "api", 3, "flowfinal", col=1, label="무시")
    A("d2", "api", 4, "decision", "경고창이 이미\n떠 있음?")
    A("d3", "api", 4, "decision", "같은 이탈의\n후속 신호?", col=1)
    A("ff2", "api", 4, "flowfinal", col=2, label="무시")
    A("a3", "api", 5, "action", "이탈 횟수 + 1")
    A("a4", "api", 5, "action", "이탈 횟수 = 2", col=1)
    A("a5", "db", 6, "action", "이탈 이벤트 기록\n(판정: 부정행위)")
    A("d4", "api", 7, "decision", "이탈 횟수 ≥ 2?")
    A("c1", "api", 7, "action", "→ cancelled\n종료 메시지 전송·연결 종료", col=1)
    A("c2", "api", 8, "action", "채점 대기열 등록\n(응시 취소: 0점·불합격)", col=1)
    A("ec", "api", 9, "final", col=1, label="응시 취소")
    A("w1", "api", 8, "action", "1회차 경고 전송\n답변 남은 시간·\n코딩 타이머 정지")
    A("w2", "front", 9, "action", "경고창 표시")
    A("w3", "applicant", 10, "action", "[확인]")
    A("w4", "api", 11, "action", "멈춘 지점부터 재개\n(질문 음성·카운트다운 중\n이탈이면 그 질문 처음부터)")
    A("e", "api", 12, "final")
    E = d.edge
    E("s", "a1"); E("a1", "a2"); E("a2", "d1")
    E("d1", "ff1", "예", out="right", inp="left"); E("d1", "d2", "아니요")
    E("d2", "d3", "예", out="right", inp="left")
    E("d3", "ff2", "예", out="right", inp="left"); E("d3", "a4", "아니요")
    E("d2", "a3", "아니요"); E("a3", "a5"); E("a4", "a5"); E("a5", "d4")
    E("d4", "c1", "예", out="right", inp="left"); E("c1", "c2"); E("c2", "ec")
    E("d4", "w1", "아니요"); E("w1", "w2"); E("w2", "w3"); E("w3", "w4"); E("w4", "e")
    return d, ["이탈 판정은 서버가 한다. 이탈 기록은 부정행위 판정으로 남고, 응시 취소 건은 채점하지 않고 0점·불합격으로 결정한다.",
               "연결 자체가 끊기면 06 연결 끊김 흐름으로 간다."]


def disconnect():
    d = Diagram("06. 연결 끊김 처리와 이어가기", [APPLICANT, ("front", "프론트엔드", 1), ("api", "면접 엔진 · 백엔드 API", 2), ("db", "DB", 1)],
                "끊긴 원인을 판정해 장애면 중단(이어가기 가능), 지원자 쪽 종료면 응시 종료")
    A = d.add
    A("s", "api", 0, "start", label="WebSocket 비정상 종료")
    A("a1", "api", 1, "action", "판정 대기 15초\n(heartbeat 5초 × 3회)")
    A("a2", "db", 2, "action", "끊기기 직전 30초\n이벤트 조회")
    A("d1", "api", 3, "decision", "창 닫기·권한 해제\n기록 있음?")
    A("n1", "api", 3, "action", "지원자 쪽 종료로 판정\n→ ended, 채점 등록", col=1)
    A("en1", "api", 4, "final", col=1, label="응시 종료")
    A("a3", "api", 4, "action", "장애로 판정 (fault)")
    A("d2", "api", 5, "decision", "남은 이어가기\n> 0? (기본 3회)")
    A("n2", "api", 5, "action", "→ ended (이어가기 소진)\n채점 등록", col=1)
    A("en2", "api", 6, "final", col=1, label="응시 종료")
    A("a4", "api", 6, "action", "→ interrupted\n시간 정지·자리 맡아 둠\n중단 안내 전송")
    A("a5", "applicant", 7, "action", "마이페이지에서\n[이어하기]")
    A("a6", "front", 8, "action", "환경 재점검 후\nPOST …/interview/resume")
    A("d3", "api", 9, "decision", "마감 전·\n점검 유효?")
    A("n3", "api", 9, "action", "409 응답\n(마감이면 ended_closed)", col=1)
    A("ff3", "api", 10, "flowfinal", col=1)
    A("a7", "api", 10, "action", "interrupted → interviewing\n또는 coding, 새 세션 생성")
    A("a8", "api", 11, "action", "멈춘 질문을 처음부터 다시\n(코딩은 남은 시간부터)")
    A("e", "api", 12, "final")
    d.note("api", 11.6, "마감 시각이 지나면 스케줄러가\n중단(interrupted) 건을\nended_closed 로 바꾼다", col=1)
    E = d.edge
    E("s", "a1"); E("a1", "a2"); E("a2", "d1")
    E("d1", "n1", "예", out="right", inp="left"); E("n1", "en1")
    E("d1", "a3", "아니요"); E("a3", "d2")
    E("d2", "n2", "아니요", out="right", inp="left"); E("n2", "en2")
    E("d2", "a4", "예"); E("a4", "a5"); E("a5", "a6"); E("a6", "d3")
    E("d3", "n3", "아니요", out="right", inp="left"); E("n3", "ff3")
    E("d3", "a7", "예"); E("a7", "a8"); E("a8", "e")
    return d, ["원인을 모르면 지원자에게 유리하게 장애로 본다. 서버 오류·재시작으로 끊긴 것은 이어가기 횟수에 넣지 않는다."]


def coding():
    d = Diagram("07. 코딩테스트", [APPLICANT, ("front", "프론트엔드", 2), ("api", "백엔드 API", 2), ("sandbox", "격리 실행 환경 (worker-sandbox)", 1),
                                  ("db", "DB", 1)],
                "코딩테스트를 켠 공고만. 2문항 · 60분 · Python. 실행은 격리 컨테이너에서만 한다.")
    A = d.add
    A("s", "api", 0, "start", label="AI 면접 종료")
    A("b1", "db", 1, "action", "interviewing → coding\n문제 2개 배정 (시작 코드)\n면접 자리 반환")
    A("b2", "front", 2, "action", "코딩테스트 안내 화면")
    A("b3", "applicant", 3, "action", "[시작]\n(60초 지나면 자동 시작)")
    A("b4", "api", 4, "action", "60분 타이머 시작\nPOST /coding/{id}/start")
    A("b5", "applicant", 5, "action", "코드 작성\n(주기적 자동 저장·\n붙여넣기 차단)")
    A("d1", "applicant", 6, "decision", "다음 동작?")
    A("r1", "front", 6, "action", "예시 실행 요청\nPOST …/run", col=1)
    A("r2", "sandbox", 7, "action", "공개 예시 실행\n(네트워크 차단·\n10초·256MB 제한)")
    A("r3", "front", 8, "action", "예시별 통과·출력 표시", col=1)
    d.note("api", 7.05, "[실행] 결과는 점수에 쓰지 않는다\n(공개 예시 확인용)")
    A("p1", "front", 9, "action", "최종 제출 확인\nPOST …/submit")
    A("t1", "api", 9, "time", "60분 경과\n(서버 감시)", col=1)
    A("p2", "api", 10, "action", "제출 수신\n(시간 초과면 자동 제출로)")
    A("p3", "api", 10, "action", "마지막 저장 코드로\n자동 제출", col=1)
    A("p4", "db", 11, "action", "코드 저장\ncoding → completed")
    A("b6", "api", 12, "bar", w=bar(d, ("front", 0), ("db", 0)))
    A("q1", "front", 13, "action", "응시 완료 화면")
    A("e", "front", 14, "final")
    A("q2", "api", 13, "action", "채점 작업 대기열 등록\n(→ 08 채점)")
    A("ff1", "api", 14, "flowfinal")
    A("q3", "sandbox", 13, "action", "숨은 테스트 실행\n(인프라 오류는 오답 아님\n→ 다시 채점)")
    A("q4", "db", 14, "action", "문제별 통과 수 저장")
    A("ff2", "db", 15, "flowfinal")
    E = d.edge
    E("s", "b1"); E("b1", "b2"); E("b2", "b3"); E("b3", "b4"); E("b4", "b5"); E("b5", "d1")
    E("d1", "r1", "실행", out="right", inp="left"); E("r1", "r2"); E("r2", "r3")
    E("r3", "b5", out="left", inp="right", xm=d.lx["front"][0] + 12)
    E("d1", "p1", "최종 제출"); E("p1", "p2")
    E("t1", "p3"); E("p2", "p4"); E("p3", "p4")
    E("p4", "b6"); E("b6", "q1"); E("q1", "e"); E("b6", "q2"); E("q2", "ff1"); E("b6", "q3"); E("q3", "q4"); E("q4", "ff2")
    return d, ["시간이 지난 뒤 들어온 자동 저장·실행은 받지 않는다. 마감 시점의 마지막 저장 코드로 채점한다.",
               "코딩테스트 중 이탈·연결 끊김은 면접과 같은 규칙(05·06)을 따르며, 코딩 타이머도 함께 멈춘다."]


def evaluate():
    d = Diagram("08. 채점과 결과 공개", [("worker", "백그라운드 워커 (Celery)", 3), ("ai", "AI 서비스 (LLM)", 1), ("db", "DB", 1),
                                        ("admin", "관리자", 2), APPLICANT],
                "AI 는 루브릭 점수와 근거만 내고, 점수 계산과 합불 판정(총점 ≥ 기준점)은 코드가 한다.")
    A = d.add
    A("s", "worker", 0, "start", label="응시 끝남 (완료·종료·취소)")
    A("g1", "worker", 1, "action", "채점 작업 수신\n지원 건 잠금 (중복 실행 방지)")
    A("d1", "worker", 2, "decision", "채점 대상?\n(최종 상태·\n결과 없음)")
    A("ff1", "worker", 2, "flowfinal", col=1, label="건너뜀")
    A("d2", "worker", 3, "decision", "채점 지시\n의심 문구?")
    A("nr", "worker", 3, "action", "확인 필요(needs_review)\n표시·관리자 알림", col=2)
    A("d3", "worker", 4, "decision", "응시 취소 건?")
    A("c1", "worker", 4, "action", "0점·불합격으로 결정\n(채점하지 않음)", col=1)
    A("d4", "worker", 5, "decision", "숨은 테스트\n채점 끝남?")
    A("ff2", "worker", 5, "flowfinal", col=1, label="30초 뒤 다시")
    A("d5", "worker", 6, "decision", "LLM 서버 정상?")
    A("ff3", "worker", 6, "flowfinal", col=1, label="1분 뒤 다시")
    A("ai1", "ai", 7, "action", "질문별 루브릭 채점\n5개 항목 1~5점\n+ 답변 근거 인용")
    A("w2", "worker", 8, "action", "근거 인용을 답변 원문과 대조\n점수 계산(코드): 가중 합\n→ 코딩 비율 반영 → 총점")
    A("w3", "worker", 9, "action", "합불 판정(코드)\n총점 ≥ 합격 기준점")
    A("ai2", "ai", 10, "action", "판정 사유·요약·강점·\n개선점·코드 리뷰 작성")
    A("r1", "db", 11, "action", "결과 저장 (decided)\n공개 예정 시각 지정")
    A("t1", "worker", 12, "time", "공개 시각 도달\n(5분마다 점검)")
    A("r2", "db", 13, "action", "release_status = released\n지원자 알림 생성")
    A("p1", "applicant", 14, "action", "알림·메일 수신\n마이페이지 결과 확인")
    A("e", "applicant", 15, "final")
    A("m1", "admin", 4, "action", "확인 필요 건 검토\n(답변·사유 확인)")
    A("m2", "admin", 5, "decision", "처리 방법?")
    A("m3", "admin", 6, "action", "합격·불합격 직접 결정\n(사유 기록)")
    A("m4", "admin", 5, "action", "다시 분석 요청\n(채점 처음부터)", col=1)
    A("ff4", "admin", 6, "flowfinal", col=1)
    d.note("admin", 8.1, "기한 안에 처리되지 않으면\n스케줄러가 다시 채점하거나\n'평가 미완료 불합격'으로 마감", col=1)
    d.note("worker", 8.0, "기한(30분)이 지나도 못 끝내면\n확인 필요로 넘긴다", col=1)
    E = d.edge
    E("s", "g1"); E("g1", "d1")
    E("d1", "ff1", "아니요", out="right", inp="left"); E("d1", "d2", "예")
    E("d2", "nr", "예", out="right", inp="left"); E("nr", "m1")
    E("d2", "d3", "아니요")
    E("d3", "c1", "예", out="right", inp="left"); E("c1", "r1", out="right", inp="left", xm=d.colX("worker", 2))
    E("d3", "d4", "아니요")
    E("d4", "ff2", "아니요", out="right", inp="left"); E("d4", "d5", "예")
    E("d5", "ff3", "아니요", out="right", inp="left"); E("d5", "ai1", "예")
    E("ai1", "w2"); E("w2", "w3"); E("w3", "ai2"); E("ai2", "r1")
    E("m1", "m2"); E("m2", "m3", "직접 판정"); E("m2", "m4", "다시 분석", out="right", inp="left"); E("m4", "ff4")
    E("m3", "r1", out="bottom", inp="right")
    E("r1", "t1"); E("t1", "r2"); E("r2", "p1"); E("p1", "e")
    return d, ["시선·표정·음성 같은 비언어 정보는 점수에 쓰지 않는다. 채점 근거(인용)는 답변 원문에 있는지 코드로 다시 확인한다.",
               "결과는 공고의 결과 공개 시각(마감 다음 날 10시) 전에는 지원자에게 보이지 않는다."]


def posting():
    d = Diagram("09. 관리자 공고 작성·게시", [ADMIN, ("front", "프론트엔드", 2), ("api", "백엔드 API", 2), ("worker", "백그라운드 작업·AI", 1), ("db", "DB", 1)],
                "직접 작성 또는 AI 초안 → 평가 기준 설정 → 게시 검증 → 게시")
    A = d.add
    A("s", "admin", 0, "start")
    A("p1", "admin", 1, "action", "[새 공고 만들기]")
    A("p2", "front", 2, "action", "POST /admin/postings")
    A("p3", "db", 3, "action", "공고 생성 (draft)\n평가 기준 v1 (기본 비율·\n코딩 끔·합격 70점)")
    A("d1", "admin", 4, "decision", "작성 방식?")
    A("q0", "front", 4, "action", "기본 정보 입력\n(직무·기간·인원·업무·기술)", col=1)
    A("q1", "api", 5, "action", "POST …/draft-ai\n정해진 값은 바로 저장\n(AI 거치지 않음)", col=1)
    A("q2", "worker", 6, "action", "AI 초안 그래프 (LLM)\n회사 소개·업무·자격 문장\n(실패 시 기본 문구)")
    A("q3", "front", 7, "action", "진행 상태 조회 (폴링)\n초안 표시", col=1)
    A("p4", "front", 5, "action", "공고 항목 직접 입력")
    A("p5", "front", 8, "action", "내용 확인·수정\n평가 비율·코딩테스트·합격 기준\n(PATCH 저장)")
    d.note("front", 9.15, "AI 초안은 게시 전까지\n칸별로 '다시 쓰기' 요청 가능", col=1)
    A("p6", "admin", 9, "action", "[게시]")
    A("p7", "front", 10, "action", "POST …/publish")
    A("d2", "api", 11, "decision", "게시 검증 통과?\n(필수 항목·직무\n·기간)")
    A("x1", "api", 11, "action", "400 오류\n부족한 항목 안내", col=1)
    A("p8", "db", 12, "action", "draft → published\n결과 공개 시각 계산")
    A("b1", "api", 13, "bar", w=bar(d, ("front", 0), ("worker", 0)))
    A("p9", "front", 14, "action", "게시 완료\n(지원자 공고 목록에 노출)")
    A("e", "front", 15, "final")
    A("p10", "worker", 14, "action", "직무·회사 질문 생성\n→ 예비 질문에 바로 넣음")
    A("ff1", "worker", 15, "flowfinal")
    E = d.edge
    E("s", "p1"); E("p1", "p2"); E("p2", "p3"); E("p3", "d1")
    E("d1", "q0", "AI 초안", out="right", inp="left"); E("q0", "q1"); E("q1", "q2"); E("q2", "q3")
    E("d1", "p4", "직접 작성"); E("p4", "p5"); E("q3", "p5", out="bottom", inp="right")
    E("p5", "p6"); E("p6", "p7"); E("p7", "d2")
    E("d2", "x1", "아니요", out="right", inp="left"); E("x1", "p5", out="top", inp="right")
    E("d2", "p8", "예"); E("p8", "b1")
    E("b1", "p9"); E("p9", "e"); E("b1", "p10"); E("p10", "ff1")
    return d, ["첫 응시가 시작되면 그 공고의 평가 기준은 잠겨서 바꿀 수 없다.",
               "마감 시각이 지나면 작성 중·응시 전 지원은 not_taken_closed, 진행 중이던 응시는 ended_closed 로 바뀐다."]


ALL = [("01_로그인", login), ("02_지원서작성", apply), ("03_면접질문생성", compose), ("04_AI면접진행", interview),
       ("05_화면이탈", away), ("06_연결끊김_이어가기", disconnect), ("07_코딩테스트", coding),
       ("08_채점_결과공개", evaluate), ("09_공고작성_게시", posting)]

if __name__ == "__main__":
    here = Path(__file__).parent
    (here / "html").mkdir(exist_ok=True)
    (here / "mermaid").mkdir(exist_ok=True)
    for name, fn in ALL:
        d, footer = fn()
        (here / "html" / f"{name}.html").write_text(f'<!DOCTYPE html><html><body style="margin:0">{d.svg(footer)}</body></html>', encoding="utf-8")
        (here / "mermaid" / f"{name}.mmd").write_text(d.mermaid(), encoding="utf-8")
        print(name, d.width)
