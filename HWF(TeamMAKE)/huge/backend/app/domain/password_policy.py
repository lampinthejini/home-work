"""비밀번호 규칙 (PRD 5-1, TRD 11장). 가입·변경·재설정이 같은 함수를 쓴다."""

import re

MIN_LEN = 8
MAX_LEN = 64


def checkPassword(password: str, email: str) -> list[str]:
    """어긴 규칙의 안내 문구 목록. 비어 있으면 통과."""
    violations = []
    if not MIN_LEN <= len(password) <= MAX_LEN:
        violations.append("8~64자로 입력해 주세요")
    if not (re.search(r"[A-Za-z]", password) and re.search(r"\d", password) and re.search(r"[^A-Za-z0-9]", password)):
        violations.append("영문·숫자·특수문자를 각각 1자 이상 넣어 주세요")
    localPart = email.split("@", 1)[0].lower()
    if localPart and localPart in password.lower():
        violations.append("이메일 아이디를 포함할 수 없습니다")
    if re.search(r"(.)\1{3,}", password):
        violations.append("같은 문자를 4번 이상 연속으로 쓸 수 없습니다")
    return violations
