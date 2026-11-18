"""post_1118.py 뒤 같은 날 코드가 더 바뀐 것(예비 질문 말투·회사 고유 이름 검사)에 맞춰 개요 줄 수와 설명 2개를 고친다."""
import json
import re
from pathlib import Path

HERE = Path(__file__).parent
DOC = Path(r"C:\big21\hw-repo\HWF(TeamMAKE)\개인용\가이드\프로그램명세서.md")
py = json.load(open(HERE / "py.json", encoding="utf-8"))
s = DOC.read_text(encoding="utf-8")
pyByKey = {m["path"].removeprefix("backend/app/"): m for m in py.values()}


def fixRow(m):
    key, rest = m.group(1), m.group(3)
    if key in pyByKey and " | " in rest:
        cnt, role = rest.split(" | ", 1)
        if cnt.strip().isdigit():
            return f"| `{key}` | {pyByKey[key]['lines']} | {len(pyByKey[key]['items'])} | {role}"
    return m.group(0)


head, sep, tail = s.partition("## 3. 백엔드 프로그램 명세")
s = re.sub(r"^\| `([^`]+)` \| (\d+) \| (.*)$", fixRow, head, flags=re.M) + sep + tail

DESC = {
    "checkGenerated": "만든 질문 확인: 형식·요구하는 일 2개 이하·글 검사, 직무는 경험 질문 금지·회사 고유 이름 금지(job_company_term)·앞 직무 질문과 같은 말끝 금지(same_ending, 2026-11-18), 회사는 입사 전 지원자에게 회사 안 경험 금지, 이력서는 근거 구절과 이름. 문제 코드, 맞으면 None",
    "makeOne": "질문 1개를 만들어 검사한다(글 검사·회사 고유 이름·같은 말끝·다른 회사 이름·중복·예비 질문과 0.8 이상). 직무 자리는 정해 준 꼴(jobForm)로. 2번까지, 실패하면 (None, None)",
}
lines = s.split("\n")
for k, l in enumerate(lines):
    m = re.match(r"\| `([^`]+)` \|", l)
    if m and m.group(1) in DESC:
        cols = re.split(r"(?<!\\) \| ", l)
        cols[4] = DESC[m.group(1)]
        lines[k] = " | ".join(cols)
        DESC.pop(m.group(1))
assert not DESC, DESC
DOC.write_text("\n".join(lines), encoding="utf-8", newline="")
print("ok")
