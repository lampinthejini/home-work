from app.domain.password_policy import checkPassword


def test_validPassword():
    assert checkPassword("Hire#2026ai", "hong@example.com") == []


def test_rules():
    assert checkPassword("Ab#1", "a@b.c")  # 너무 짧음
    assert checkPassword("abcdefgh1", "a@b.c")  # 특수문자 없음
    assert checkPassword("Hong#2026x", "hong@example.com")  # 이메일 아이디 포함
    assert checkPassword("Aaaaa#2026", "z@example.com")  # 같은 문자 4번 연속
    assert checkPassword("A" * 60 + "#1bcdefg", "z@example.com")  # 64자 초과
