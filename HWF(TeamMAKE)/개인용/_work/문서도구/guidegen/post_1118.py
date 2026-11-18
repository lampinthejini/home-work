"""refresh.py 뒤에 프로그램명세서를 2026-11-18 코드에 맞춘다: 개요 표 줄 수·개수, 새 파일 줄, 가져오기 줄, 낡은 '하는 일'·역할, 머리말."""
import ast
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
HUGE = Path(r"C:\big21\hw-repo\HWF(TeamMAKE)\huge")
DOC = Path(r"C:\big21\hw-repo\HWF(TeamMAKE)\개인용\가이드\프로그램명세서.md")
py = json.load(open(HERE / "py.json", encoding="utf-8"))
ts = json.load(open(HERE / "ts.json", encoding="utf-8"))
s = DOC.read_text(encoding="utf-8")


def rep(a, b, n=1):
    global s
    assert s.count(a) == n, (s.count(a), a[:80])
    s = s.replace(a, b)


# ---------- 1. 개요 표 줄 수·개수 다시 세기 ----------
pyByKey = {m["path"].removeprefix("backend/app/"): m for m in py.values()}
tsByKey = {k.removeprefix("frontend/"): m for k, m in ts.items()}


def fixRow(m):
    key, lines, rest = m.group(1), m.group(2), m.group(3)
    if key in pyByKey and rest.count(" | ") >= 1:
        cnt, role = rest.split(" | ", 1)
        if cnt.strip().isdigit():
            info = pyByKey[key]
            return f"| `{key}` | {info['lines']} | {len(info['items'])} | {role}"
    if key in tsByKey:
        return f"| `{key}` | {tsByKey[key]['lines']} | {rest}"
    return m.group(0)


head, sep, tail = s.partition("## 3. 백엔드 프로그램 명세")
head = re.sub(r"^\| `([^`]+)` \| (\d+) \| (.*)$", fixRow, head, flags=re.M)
s = head + sep + tail

ROLE_ROWS = {
    "routers/admin_company.py": "관리자 API: 회사 정보·기술 글·회사 프로젝트",
    "services/company.py": "회사 정보와 회사 프로젝트(관리자가 적음)",
    "services/job_news.py": "직무 관련 최근 소식(질문 만들 때만, 저장 안 함)",
    "services/llm.py": "LLM 호출 공통·요청 길이 재기(4,096토큰)",
    "services/recording.py": "카메라 녹화 조각 저장·보관 기한(결과 공개 + 3일)",
}
for key, after, role in (("services/company_defaults.py", "services/company.py", "회사 정보 처음 값(회사 소개서 PDF)"),
                         ("services/tech_blog.py", "services/storage.py", "회사 기술 블로그 최신 글(D2 Atom)")):
    if f"| `{key}` |" not in s:
        info = pyByKey[key]
        s = re.sub(rf"^(\| `{re.escape(after)}` \|.*)$", lambda m: m.group(1) + "\n" + f"| `{key}` | {info['lines']} | {len(info['items'])} | {role}", s, count=1, flags=re.M)
for key, role in ROLE_ROWS.items():
    s, n = re.subn(rf"^(\| `{re.escape(key)}` \| \d+ \| \d+ \| ).*$", lambda m: m.group(1) + role, s, count=1, flags=re.M)
    assert n == 1, key

NEW_ROWS = {
    "routers/admin_company.py": "관리자 API: 회사 정보·회사 최근 소식",
    "services/company.py": "회사 정보와 회사 최근 소식(Google 뉴스 RSS)",
    "services/job_news.py": "직무 관련 최근 소식(질문 만들 때만, 저장 안 함)",
}


def insertRow(table_start, key, row):
    """같은 표에서 이름 순서 자리에 줄을 넣는다."""
    global s
    if f"| `{key}` |" in s:
        return
    lines = s.split("\n")
    i = next(k for k, l in enumerate(lines) if l.startswith(table_start))
    j = i + 2
    while j < len(lines) and lines[j].startswith("| `"):
        name = re.match(r"\| `([^`]+)`", lines[j]).group(1)
        if name > key:
            break
        j += 1
    lines.insert(j, row)
    s = "\n".join(lines)


for key, role in NEW_ROWS.items():
    info = pyByKey[key]
    insertRow("| 파일 | 줄 | 함수·클래스 | 역할 |", key, f"| `{key}` | {info['lines']} | {len(info['items'])} | {role} |")
insertRow("| 파일 | 줄 | 화면 주소 / 역할 |", "app/admin/company/page.tsx",
          f"| `app/admin/company/page.tsx` | {tsByKey['app/admin/company/page.tsx']['lines']} | /admin/company |")

# ---------- 2. 가져다 쓰는 모듈 줄 (바뀐·새 파일만 코드에서 다시 읽음) ----------
STD = set(sys.stdlib_module_names)


def importLine(path: Path) -> str:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    ours, std, ext = [], set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level:
                if node.module:
                    ours.append(node.module)
                else:
                    ours += [a.name for a in node.names]
            else:
                top = node.module.split(".")[0]
                (std if top in STD else ext).add(top)
        elif isinstance(node, ast.Import):
            for a in node.names:
                top = a.name.split(".")[0]
                (std if top in STD else ext).add(top)
    ours = list(dict.fromkeys(ours))
    parts = []
    if ours:
        parts.append("🏠 우리 " + ", ".join(f"`{x}`" for x in ours))
    if std:
        parts.append("🐍 표준 " + ", ".join(f"`{x}`" for x in sorted(std)))
    if ext:
        parts.append("📦 외부 " + ", ".join(f"`{x}`" for x in sorted(ext)))
    return "**가져다 쓰는 모듈:** " + " · ".join(parts)


PY_FILES = ["main.py", "migrate.py", "models.py", "config.py", "routers/admin_company.py", "services/company.py", "services/job_news.py", "services/llm.py", "services/posting_draft.py", "services/posting_questions.py", "services/question_compose.py", "services/recording.py", "services/resume_extract.py", "services/retention.py", "services/speech.py", "services/tech_blog.py"]
for key in PY_FILES:
    lines = s.split("\n")
    i = lines.index(f"#### `app/{key}`")
    j = next(k for k in range(i, i + 8) if lines[k].startswith("**가져다 쓰는 모듈:**"))
    lines[j] = importLine(HUGE / "backend" / "app" / key)
    s = "\n".join(lines)


# ---------- 3. 역할 줄 ----------
ROLE = {
    "app/routers/admin_company.py": "관리자 회사 정보 API — 회사 정보 보기·고치기, 회사 기술 글 새로 가져오기·[제거], 회사 프로젝트 더하기·고치기·지우기 (CONFLICTS C-20·C-21·C-22)",
    "app/services/company.py": "회사 정보와 회사 프로젝트 — 가상 회사 AIIT 정보(처음 값은 company_defaults, 회사 소개서 PDF), 관리자가 적는 회사 프로젝트, 회사 질문·AI 공고 초안에 넣을 참고 글. 예전의 '최근 소식'(뉴스 자동 찾기)은 지웠다 (CONFLICTS C-21·C-22)",
    "app/services/recording.py": "카메라 녹화 조각 저장·재생·보관 기한 — 기한은 결과 공개 + 3일(2026-11-18 C-24), 녹화는 평가에 쓰지 않는다",
}
for key, role in ROLE.items():
    lines = s.split("\n")
    i = next(k for k, l in enumerate(lines) if l.startswith(f"#### `{key}`"))
    j = next(k for k in range(i, i + 6) if lines[k].startswith("**역할:**"))
    lines[j] = f"**역할:** {role}"
    s = "\n".join(lines)
assert "(채움)" not in s, "가져오기 줄이 비었다"

# ---------- 4. 낡은 '하는 일' ----------
DESC = {
    ("app/routers/admin.py", "recordingVideo"): "`GET /admin/media/recordings/{applicationId}/{segmentNo}` — 녹화 다시 보기. 보관 기한(결과 공개 + 3일)이 지났으면 410. 재생할 때마다 감사 로그 (API 명세서 2-6).",
    ("app/routers/admin_company.py", "companyView"): "화면에 돌려줄 회사 정보 + 보이는 기술 글 목록 + 회사 프로젝트 목록",
    ("app/services/company.py", "questionContext"): "회사 질문에 넣는 회사 정보 + 가까운 프로젝트 2개 + 기술 글 1개(같은 면접에서 앞 질문이 쓴 글은 뺀다).",
    ("app/services/company.py", "postingContext"): "AI 공고 초안에 넣는 회사 정보(직무 소개·인재상·기술 스택 포함) + 그 공고와 가까운 프로젝트. projectCount=0 이면 프로젝트를 넣지 않는다(초안은 길이를 맞추며 따로 붙임, C-24).",
    ("app/services/company.py", "addProject"): "회사 프로젝트를 더한다(감사 기록). 30개가 차 있으면 None",
    ("app/services/recording.py", "baseExpiry"): "이 건의 결과 공개 시각(없으면 공고의 공개 시각) + 3일. 결과가 늦게 나오면 그 건의 공개 시각으로 늦춰진다 (C-24).",
    ("app/services/recording.py", "expiresAt"): "보관 기한. 공개 시각이 바뀔 수 있어(늦은 결과·마감일 변경) 저장한 expires_at 이 아니라 지금 값(baseExpiry)으로 센다.",
    ("app/services/resume_extract.py", "structure"): "이력서 글을 LLM 으로 칸에 나눠 담는다. 길면 조각마다 차례로 정리해 합친다(남은 시간을 함께 씀, C-24)",
    ("app/services/resume_extract.py", "extractUpload"): "업로드 하나 추출 전체: 읽기 → OCR → LLM 정리 → 결과 저장. 글이 길면 예상 시간·실패 기준을 글 길이에 맞춰 늘린다 (C-24)",
    ("app/services/retention.py", "purgeRecordings"): "보관 기한(결과 공개 + 3일)이 지난 녹화 파일·행을 지운다. 결과를 못 정한 건은 최대 7일 더 기다린다. 지원 건은 남긴다. 실패한 건은 다음 시간에 다시.",
    ("app/admin/applicants/[applicationId]/page.tsx", "Recordings"): "카메라 녹화 다시 보기 (결과 공개 + 3일). 부정행위 확인용이며 평가에는 쓰지 않는다",
    ("app/admin/company/page.tsx", "CompanyBody"): "회사 정보 화면 본문: 칸 고치기·[저장], 기술 글 목록·[새로 가져오기]·[제거], 회사 프로젝트 더하기·[수정]·[삭제]",
}
lines = s.split("\n")
cur = None
done = set()
for k, l in enumerate(lines):
    m = re.match(r"#### `([^`]+)`", l)
    if m:
        cur = m.group(1)
        continue
    m = re.match(r"\| `([^`]+)` \|", l)
    if m and (cur, m.group(1)) in DESC:
        cols = re.split(r"(?<!\\) \| ", l)
        idx = 4 if not cur.endswith(".tsx") else 3
        cols[idx] = DESC[(cur, m.group(1))].replace("|", "\|")
        lines[k] = " | ".join(cols)
        done.add((cur, m.group(1)))
s = "\n".join(lines)
assert done == set(DESC), set(DESC) - done

# ---------- 5. 테스트 대응표 ----------
ROWS = {
    "backend/tests/test_posting_graph.py": (17, "AI 공고 초안 그래프 (2026-11-10 사용자 결정): 참고 공고 찾기 → 초안 → 칸별 검사 → 문제 칸만 다시 쓰기 → 저장. 입력이 길면 참고를 빼고, 다시 쓰기가 너무 길면 LLM 을 부르지 않음 (C-24)."),
    "backend/tests/test_question_rag.py": (41, "질문 10개 RAG 구성 (TRD 7-4, 사용자 결정 U5): RAG 로 먼저 만들고, 못 만들면 예비 질문 (C-20). 기술 글은 질문마다 다른 글 (C-22)."),
    "backend/tests/test_recording.py": (9, "카메라 녹화 (API 명세서 6장 POST /interview/{sid}/recording · 2-6 미디어, 테이블 정의서 4-10). 결과 공개 + 3일 삭제, 결과를 못 정한 건은 기다림 (C-24)."),
    "backend/tests/test_reserve_company.py": (15, "예비 질문과 회사 정보 (C-20·C-21): 기본 질문 종류마다 10개, AI 질문은 승인 없이(0.8 이상 비슷하면 뺌, 100개까지), 관리자 예비 질문 화면 API, 회사 정보·회사 프로젝트·회사 질문 RAG."),
    "backend/tests/test_resume_extract.py": (23, "이력서 읽기: PDF 글자·OCR·LLM 정리·뒷정리. 긴 이력서는 나눠 정리하고 합침(앞 조각의 칸 제목, 같은 항목 하나만, C-24)."),
    "backend/tests/test_stt_hints.py": (3, "답변을 받아 적을 때 STT 에 주는 참고 말 (2026-11-17 사용자 결정, STT 방식 '가')."),
    "backend/tests/test_tech_blog.py": (10, "회사 기술 블로그 최신 글과 회사 정보 새 칸 (C-22): Atom 읽기·news 분류 빼기·회사 이름 바꾸기·[제거]·질문마다 다른 글."),
}
lines = s.split("\n")
h = next(k for k, l in enumerate(lines) if l.startswith("## 5. 테스트 대응표"))
t0 = next(k for k in range(h, len(lines)) if lines[k].startswith("| 파일 | 테스트 수 |"))
t1 = t0 + 2
while lines[t1].startswith("| `"):
    t1 += 1
rows = {re.match(r"\| `([^`]+)`", l).group(1): l for l in lines[t0 + 2:t1]}
for key, (n, what) in ROWS.items():
    rows[key] = f"| `{key}` | {n} | {what} |"
backend = sorted(k for k in rows if k.startswith("backend/"))
e2e = sorted(k for k in rows if not k.startswith("backend/"))
lines[t0 + 2:t1] = [rows[k] for k in backend + e2e]
s = "\n".join(lines)

# ---------- 6. 머리말 ----------
nPy, nTs = len(py), len(ts)
nItems = sum(len(m["items"]) for m in py.values()) + sum(len(m["items"]) for m in ts.values())
s, n = re.subn(r"\| 기준 \| 2026-11-\d+ 코드 [^|]*\|", "| 기준 | 2026-11-18 코드 (커밋 `70dfe34` 이후 작업 중인 코드, 표는 2026-11-18 에 다시 뽑음) |", s)
assert n == 1
s, n = re.subn(r"\| 범위 \| 파일 \d+개, 함수·클래스·화면 \d+개 \|", f"| 범위 | 파일 {nPy + nTs}개, 함수·클래스·화면 {nItems}개 |", s)
assert n == 1
old = s[s.index("> **2026-11-16 보정.**"):]
old = old[:old.index("\n")]
s = s.replace(old, "> **2026-11-18 보정.** 2026-11-17·18 변경(CONFLICTS C-21 회사 최근 소식 → 회사 프로젝트, C-22 회사 소개서로 회사 정보·회사 기술 글, C-23 가중치 자동 맞춤, "
              "C-24 녹화 보관 결과 공개 + 3일·LLM 요청 길이 맞추기)에 맞춰 모든 표의 줄 번호·인자·부르는 곳을 코드에서 다시 뽑았다. 새 파일 `services/tech_blog.py` 절을 넣고, "
              "회사 소식·녹화 기한을 말하던 '하는 일'·역할을 고쳤다.\n>\n" + old.replace("> **2026-11-16 보정.**", "> 이전 보정(2026-11-16):"))

DOC.write_text(s, encoding="utf-8", newline="")
print("ok", nPy, nTs, nItems)
