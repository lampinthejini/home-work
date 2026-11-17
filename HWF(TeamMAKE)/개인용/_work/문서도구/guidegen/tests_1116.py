"""프로그램명세서 5장 테스트 대응표를 2026-11-16 테스트 파일에 맞춘다."""
import re
from pathlib import Path

DOC = Path(r"C:\big21\hw-repo\HWF(TeamMAKE)\개인용\가이드\프로그램명세서.md")
s = DOC.read_text(encoding="utf-8")

ROWS = {
    "backend/tests/test_posting_questions.py": (8, "질문 적용 범위와 공고 기반 예비 질문 (C-17, 2026-11-16 C-20 으로 바뀜): 직무 질문은 같은 직무에서만, 나머지는 공통, 게시하면 예비 질문에 바로."),
    "backend/tests/test_question_dedup.py": (3, "질문 10개 안에 같은 질문이 두 번 나오지 않게 하는 비교."),
    "backend/tests/test_question_rag.py": (36, "질문 10개 RAG 구성 (TRD 7-4, 사용자 결정 U5): RAG 로 먼저 만들고, 못 만들면 예비 질문 (C-20: 예시도 예비 질문)."),
    "backend/tests/test_question_text.py": (16, "AI 가 만든 질문 글 검사 (본질문·꼬리질문 공통, 2026-11-10 사용자 결정): 찌꺼기·답변 방식 지시. 두 가지를 묻는 질문은 막지 않는다 (2026-11-16, C-19)."),
    "backend/tests/test_away_coding.py": (4, "화면 이탈 1회째 (CHT-02·05, CONFLICTS C-18): 코딩테스트는 첫 이탈에도 시계를 멈추지 않고, 이탈 시각·시간을 기록한다."),
    "backend/tests/test_job_news.py": (7, "직무 관련 최근 소식(임시 자료)과 회사 소식 거르기 (C-20): 30초 안에 끝난 검색만, 직무와 상관없는 제목은 뺌, 최대 10개, DB 에 남기지 않음."),
    "backend/tests/test_reserve_company.py": (15, "예비 질문과 회사 정보 (C-20): 기본 질문 종류마다 10개, AI 질문은 승인 없이(0.8 이상 비슷하면 뺌, 100개까지), 관리자 예비 질문 화면 API, 회사 정보·최근 소식·회사 질문 RAG."),
}
lines = s.split("\n")
head = next(k for k, l in enumerate(lines) if l.startswith("## 5. 테스트 대응표"))
t0 = next(k for k in range(head, len(lines)) if lines[k].startswith("| 파일 | 테스트 수 |"))
t1 = t0 + 2
while lines[t1].startswith("| `"):
    t1 += 1
rows = {re.match(r"\| `([^`]+)`", l).group(1): l for l in lines[t0 + 2:t1]}
for key, (n, what) in ROWS.items():
    rows[key] = f"| `{key}` | {n} | {what} |"
backend = sorted(k for k in rows if k.startswith("backend/"))
e2e = sorted(k for k in rows if not k.startswith("backend/"))
lines[t0 + 2:t1] = [rows[k] for k in backend + e2e]
DOC.write_text("\n".join(lines), encoding="utf-8", newline="")
print("ok", len(rows))
