"""refresh.py 뒤에 프로그램명세서를 2026-11-16 코드에 맞춘다: 개요 표 줄 수·개수, 새 파일 줄, 가져오기 줄, 낡은 '하는 일'·역할, 머리말."""
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
    "routers/admin_questions.py": "관리자 API: 예비 질문 보기·고치기·지우기",
    "services/posting_questions.py": "공고 기반·인터넷 참고 예비 질문",
    "services/question_bank.py": "예비 질문(기본 40개·AI 질문 넣기·지우기)",
    "domain/question_text.py": "AI 질문 글 검사(찌꺼기·답변 방식 지시·말끝·예/아니오)",
}
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


PY_FILES = ["main.py", "manage.py", "models.py", "migrate.py", "config.py", "routers/admin_questions.py", "routers/admin_company.py",
            "services/company.py", "services/job_news.py", "services/question_bank.py", "services/question_compose.py",
            "services/rag.py", "services/posting_questions.py", "services/posting_draft.py"]
for key in PY_FILES:
    lines = s.split("\n")
    i = lines.index(f"#### `app/{key}`")
    j = next(k for k in range(i, i + 8) if lines[k].startswith("**가져다 쓰는 모듈:**"))
    lines[j] = importLine(HUGE / "backend" / "app" / key)
    s = "\n".join(lines)

# ---------- 3. 역할 줄 ----------
ROLE = {
    "app/routers/admin_questions.py": "관리자 API: 예비 질문 — 예비 질문(AI 가 질문을 만들 때 보는 예시이자 대신 내는 질문)을 보고, 글을 고치고, '해당 직무만'을 정하고, 지운다. AI 질문은 승인 없이 들어오고 하루가 안 된 질문은 NEW (CONFLICTS C-20).",
    "app/services/posting_questions.py": "공고 기반 예비 질문 — 게시한 공고로 직무·회사 질문을 만들어 승인 없이 예비 질문에 넣고(같은 종류와 0.8 이상 비슷하거나 100개가 찼으면 뺌), 인터넷 참고 후보 파일을 불러온다 (CONFLICTS C-17·C-20)",
    "app/services/question_bank.py": "예비 질문 — 질문 DB 는 예비 질문(source='reserve') 하나만 쓴다. 기본 질문 40개(종류마다 10개)와 AI 가 만든 질문을 넣고 지운다. 엑셀 질문 DB 는 2026-11-16 에 지웠다 (CONFLICTS C-20).",
    "app/services/rag.py": "임베딩과 벡터 검색 — 예비 질문 임베딩과 비슷한 질문 찾기(유사도 0.5 미만 예시는 뺌), 베낌·중복 0.9 기준 (TRD 7-4 ①②③, 테이블 정의서 4-16 questions.embedding).",
    "app/domain/question_text.py": "AI 질문 글 검사 — 본질문(T2·T3)과 꼬리질문(T4)이 같이 쓰는 규칙. 찌꺼기·답변 방식 지시·질문 아님·어색한 말끝·100자, 예/아니오 질문 판별 (CONFLICTS C-16·C-17, 두 가지 묻기 검사는 C-19 로 뺌)",
}
for key, role in ROLE.items():
    lines = s.split("\n")
    i = next(k for k, l in enumerate(lines) if l.startswith(f"#### `{key}`"))
    j = next(k for k in range(i, i + 6) if lines[k].startswith("**역할:**"))
    lines[j] = f"**역할:** {role}"
    s = "\n".join(lines)
s = s.replace("**가져다 쓰는 모듈:** (채움)\n", "**가져다 쓰는 모듈:** (채움)\n")  # 새 절은 아래 2번 목록에 들어 있어 이미 채워짐
assert "(채움)" not in s, "가져오기 줄이 비었다"

# ---------- 4. 낡은 '하는 일' ----------
DESC = {
    ("app/manage.py", "loadQuestions"): "명령 `load_questions`: 기본 예비 질문 40개를 넣는다(예비 질문이 이미 있으면 건너뜀)",
    ("app/manage.py", "embedQuestions"): "명령 `embed_questions`: 임베딩이 없는 예비 질문의 벡터를 만든다",
    ("app/manage.py", "loadWebQuestions"): "명령 `load_web_questions <공고 id>`: 인터넷 참고 후보 파일(WEB_QUESTIONS_PATH)을 예비 질문에 넣는다",
    ("app/routers/admin_questions.py", "view"): "예비 질문을 화면용 dict 로 (종류·글·출처 category·직무 이름·'해당 직무만'·NEW)",
    ("app/routers/admin_questions.py", "listQuestions"): "`GET /admin/questions` — 예비 질문 목록(종류로 거르기, 최신 순)과 종류별 개수·상한(100)",
    ("app/services/posting_questions.py", "schedule"): "공고 기반 질문 만들기를 뒤에서 시작한다 (게시 응답을 기다리게 하지 않음)",
    ("app/services/posting_questions.py", "saveCandidate"): "질문 1개를 적용 범위(직무 질문만 그 직무)를 붙여 예비 질문에 넣는다(saveReserve). 넣었으면 True",
    ("app/services/posting_questions.py", "examplesFor"): "예비 질문 예시와 찾을 글의 벡터 (회사 질문은 이 벡터로 가까운 최근 소식을 고른다). 임베딩 서버가 없으면 빈 목록",
    ("app/services/posting_questions.py", "makeOne"): "질문 1개를 만들어 검사한다(글 검사·다른 회사 이름·중복·예비 질문과 0.8 이상). 2번까지, (글, 벡터) 또는 (None, None)",
    ("app/services/posting_questions.py", "generateForPosting"): "공고 하나로 직무 질문(줄마다 1개, 최대 6) + 회사 질문 3개(초점이 서로 다름, 회사 정보·소식 참고)를 만들어 예비 질문에 넣고 감사 기록을 남긴다. 실패해도 오류를 던지지 않는다",
    ("app/services/posting_questions.py", "loadWebCandidates"): "인터넷 참고 후보 파일에서 예비 질문에 넣는다(saveReserve 규칙). 직무 질문은 그 공고의 직무만, 나머지는 공통. 이미 있는 글은 건너뛴다",
    ("app/services/question_bank.py", "excludedReason"): "다른 회사 이름·관계없는 질문이면 제외 이유 (예비 질문에 넣지 않음)",
    ("app/services/question_compose.py", "candidates"): "대체 후보: 같은 종류 예비 질문 중 적용 범위가 맞는 것(공통·같은 직무)을 그 공고에서 덜 쓴 순으로",
    ("app/services/question_compose.py", "ragPrompt"): "질문 1개를 만드는 프롬프트: 종류 안내·꼴 예·말끝 안내 + 기술 주제(직무)나 초점(회사) + 공고·이력서·예시 질문·이미 낸 질문 + 회사 정보·소식(회사) / 직무 소식(직무) + 이전 답의 문제 (TRD 7-4 ③-3)",
    ("app/services/question_compose.py", "checkGenerated"): "만든 질문 확인: 형식·요구하는 일 2개 이하(C-19)·글 검사, 직무는 경험 질문 금지, 회사는 입사 전 지원자에게 회사 안 경험 묻기 금지, 이력서는 근거·이름 확인. 문제 코드, 맞으면 None",
    ("app/services/question_compose.py", "bankFallback"): "예비 질문에서 적게 쓴 것부터 고른다. 이미 고른 질문과 뜻이 0.9 이상 비슷하면 건너뛴다 (TRD 7-4 ②)",
    ("app/services/question_compose.py", "buildComposeGraph"): "질문 10칸 채우기 순서도: 고르기 → 예시 → 생성 → 검사 → (실패 시) 예비 질문 → 고정 문장",
    ("app/services/question_compose.py", "buildComposeGraph.examples"): "① 찾기: 공고·이력서로 같은 종류 예비 질문 예시를 찾는다(유사도 0.5 미만은 뺌)",
    ("app/services/question_compose.py", "buildComposeGraph.bank"): "예비 질문. 예비 질문도 없으면 고정 문장. 질문 바꾸기는 감점·장애가 아니다",
    ("app/services/question_compose.py", "buildComposeGraph.afterPick"): "갈림길: RAG 가능하면 examples, 아니면 bank(예비 질문)",
    ("app/services/question_compose.py", "buildComposeGraph.afterExamples"): "갈림길: 예시가 없어도 generate. 시간이 없거나 임베딩 서버가 없을 때만 bank(예비 질문)",
    ("app/services/question_compose.py", "buildComposeGraph.afterGenerate"): "갈림길: 시간 초과면 bank(예비 질문), 아니면 check",
    ("app/services/question_compose.py", "buildComposeGraph.afterCheck"): "갈림길: 통과면 다음 칸, 실패면 재생성 또는 bank(예비 질문)",
    ("app/services/question_compose.py", "compose"): "지원 건의 질문 10개를 만들고 저장(TTS 포함), 상태를 ready/failed 로. 시작 때 직무 소식을 찾고(job_news.collect) 끝나면 지우며, AI 질문은 예비 질문에 넣는다(saveGenerated)",
    ("app/services/question_compose.py", "personalTerms"): "지원자를 가리킬 수 있는 말: 이름·학교·회사·프로젝트·자격 이름. 우리 회사 이름은 넣지 않는다 (질문에 회사 이름을 쓴다, C-20)",
    ("app/services/question_compose.py", "isPersonal"): "질문에 지원자 고유의 말이나 이력서 문구가 들어 있으면 True (예비 질문에 넣지 않는다)",
    ("app/services/question_compose.py", "scopeFor"): "예비 질문 적용 범위: 직무 질문은 그 직무만('해당 직무만 보기'), 나머지는 공통 (C-20. 회사 정보가 하나라 회사 질문도 공통)",
    ("app/services/rag.py", "Example"): "비슷한 예비 질문 하나(문장, 유사도, 벡터)",
    ("app/services/rag.py", "indexQuestions"): "임베딩이 없는 예비 질문을 모두 숫자 목록으로 바꿔 넣는다 (manage.py embed_questions, 앱 시작 때도). 다시 돌려도 남은 것만 한다",
    ("app/services/rag.py", "similar"): "같은 종류 예비 질문 중 뜻이 가장 가까운 것 count 개 (RAG 예시, TRD 7-4 ③-2). 다른 직무 전용 질문은 뺀다",
    ("app/services/rag.py", "maxStoredSimilarity"): "같은 종류 예비 질문 전체에서 가장 비슷한 정도 (0.8 이상이면 예비 질문에 넣지 않음)",
    ("app/admin/questions/page.tsx", "Questions"): "예비 질문 화면: 종류 탭(개수/100), 질문·직무·'해당 직무만'·NEW, [수정]·[삭제]·[고른 질문 삭제]",
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
        cols = l.split(" | ")
        idx = 4 if not cur.endswith(".tsx") else 3
        cols[idx] = DESC[(cur, m.group(1))].replace("|", "\\|")
        lines[k] = " | ".join(cols)
        done.add((cur, m.group(1)))
s = "\n".join(lines)
assert done == set(DESC), set(DESC) - done

# ---------- 5. 프론트 회사 정보 화면 절 ----------
if "#### `app/admin/company/page.tsx`" not in s:
    items = {i["name"]: i for i in ts["frontend/app/admin/company/page.tsx"]["items"]}
    sec = ["#### `app/admin/company/page.tsx`  ·  `/admin/company`", "",
           "**가져다 쓰는 모듈:** 🏠 우리 `components/AdminShell`, `components/Providers`, `components/Ui`, `lib/api`, `lib/format` · 📦 외부 `react`", "",
           "| 이름 | 종류 | 줄 | 하는 일 | 쓰는 곳 |", "|---|---|---|---|---|",
           f"| `CompanyBody` | 컴포넌트 | {items['CompanyBody']['line']} | 회사 정보 화면 본문: 칸 고치기·[저장], 최근 소식 목록·[새로 찾기]·[제거] | 이 파일 안 |",
           f"| `CompanyPage` | 컴포넌트 · 내보냄 | {items['CompanyPage']['line']} | 화면 입구 (Next.js 가 `/admin/company` 에서 부름) | 이 파일 안 |", "", ""]
    anchor = "#### `app/admin/compare/page.tsx`"
    rep(anchor, "\n".join(sec) + anchor)

# ---------- 6. 머리말과 보정 상자 ----------
nPy = len(py)
nTs = len(ts)
nItems = sum(len(m["items"]) for m in py.values()) + sum(len(m["items"]) for m in ts.values())
rep("| 기준 | 2026-11-10 코드 (커밋 `53ac891` 이후) |", "| 기준 | 2026-11-16 코드 (커밋 `796aeaa` 이후, 표는 2026-11-16 에 다시 뽑음) |")
s, n = re.subn(r"\| 범위 \| 파일 \d+개, 함수·클래스·화면 \d+개 \|", f"| 범위 | 파일 {nPy + nTs}개, 함수·클래스·화면 {nItems}개 |", s)
assert n == 1
start = s.index("> **2026-11-16 보정 — 이 명세서에서 낡은 곳.**")
end = s.index("\n\n", s.index("> | `frontend/app/admin/questions/page.tsx`"))
s = s[:start] + ("> **2026-11-16 보정.** 2026-11-16 변경(CONFLICTS C-19·C-20: 엑셀 질문 DB → 예비 질문, 회사 정보·회사 최근 소식, 직무 관련 최근 소식)에 맞춰 "
                 "모든 표의 줄 번호·인자·부르는 곳을 코드에서 다시 뽑았다. 새 파일 `routers/admin_company.py`·`services/company.py`·`services/job_news.py`·"
                 "`app/admin/company/page.tsx` 절을 넣고, 질문은행·검토 대기를 말하던 '하는 일'·역할을 고쳤다.") + s[end:]

DOC.write_text(s, encoding="utf-8", newline="")
print("ok", nPy, nTs, nItems)
