"""코딩테스트 문제 목록 (PRD COD-02: AI/AX 엔지니어 문제 목록에서 기초 1 · 응용 1, Python 3, 60분).

숨겨진 테스트와 정답은 어떤 응답에도 넣지 않는다 (COD-05). 문제 관리 화면은 범위 밖이라 코드에 둔다.
"""

import hashlib

LEVELS = ("기초", "응용")

PROBLEMS = {
    "basic_token_count": {
        "level": "기초",
        "title": "토큰 개수 세기",
        "statement": "공백(스페이스·탭·줄바꿈)으로 나눈 단어 수를 돌려주는 함수를 작성하세요. 공백만 있으면 0입니다.",
        "signature": "def solution(text: str) -> int:",
        "starter": "def solution(text: str) -> int:\n    # 여기에 코드를 작성하세요\n    return 0\n",
        "examples": [("'hello world'", "2"), ("'  AI   interview  '", "2")],
        "hidden": [("''", "0"), ("'a'", "1"), ("'a\\tb\\nc'", "3"), ("'   '", "0"), ("'one two three four five'", "5")],
    },
    "basic_top_word": {
        "level": "기초",
        "title": "가장 많이 나온 단어",
        "statement": "단어 리스트 words 에서 가장 많이 나온 단어를 돌려주세요. 횟수가 같으면 사전 순으로 앞선 단어를 돌려줍니다. words 는 비어 있지 않습니다.",
        "signature": "def solution(words: list[str]) -> str:",
        "starter": "def solution(words: list[str]) -> str:\n    # 여기에 코드를 작성하세요\n    return ''\n",
        "examples": [("['ai', 'ml', 'ai']", "'ai'"), ("['b', 'a']", "'a'")],
        "hidden": [("['x']", "'x'"), ("['c', 'b', 'a']", "'a'"), ("['b', 'b', 'a', 'a', 'c']", "'a'"),
                   ("['z', 'z', 'z', 'a', 'a']", "'z'"), ("['b'] * 50000 + ['a'] * 50000", "'a'")],
    },
    "basic_mask_digits": {
        "level": "기초",
        "title": "숫자 가리기",
        "statement": "문자열 text 에 있는 숫자(0~9)를 모두 * 로 바꿔 돌려주세요. 나머지 글자는 그대로 둡니다.",
        "signature": "def solution(text: str) -> str:",
        "starter": "def solution(text: str) -> str:\n    # 여기에 코드를 작성하세요\n    return ''\n",
        "examples": [("'tel 010-1234'", "'tel ***-****'"), ("'no digit'", "'no digit'")],
        "hidden": [("''", "''"), ("'0'", "'*'"), ("'a1b2c3'", "'a*b*c*'"), ("'9876543210'", "'**********'"),
                   ("'한글 7개 포함'", "'한글 *개 포함'")],
    },
    "basic_accuracy": {
        "level": "기초",
        "title": "모델 정확도 계산",
        "statement": (
            "같은 길이의 정수 리스트 preds(예측)와 labels(정답)가 주어질 때, "
            "값이 같은 위치의 비율을 소수 둘째 자리로 반올림(round)해 돌려주세요. "
            "리스트가 비어 있으면 0.0 입니다."
        ),
        "signature": "def solution(preds: list[int], labels: list[int]) -> float:",
        "starter": "def solution(preds: list[int], labels: list[int]) -> float:\n    # 여기에 코드를 작성하세요\n    return -1.0\n",
        "examples": [("[1, 0, 1], [1, 1, 1]", "0.67"), ("[0, 0], [0, 0]", "1.0")],
        "hidden": [("[], []", "0.0"), ("[1], [0]", "0.0"), ("[1, 2, 3, 4], [1, 2, 0, 0]", "0.5"),
                   ("[1, 1, 1, 1, 1, 1, 1, 0], [1, 1, 1, 1, 1, 1, 1, 1]", "0.88"), ("[1] * 100000, [1] * 99999 + [0]", "1.0")],
    },
    "basic_unique_keep_order": {
        "level": "기초",
        "title": "순서를 지켜 중복 없애기",
        "statement": "정수 리스트 items 에서 중복을 없애고, 처음 나온 순서를 유지한 리스트를 돌려주세요.",
        "signature": "def solution(items: list[int]) -> list[int]:",
        "starter": "def solution(items: list[int]) -> list[int]:\n    # 여기에 코드를 작성하세요\n    return []\n",
        "examples": [("[3, 1, 3, 2]", "[3, 1, 2]"), ("[1, 1]", "[1]")],
        "hidden": [("[]", "[]"), ("[5]", "[5]"), ("[2, 1]", "[2, 1]"), ("[-1, 0, -1, 0]", "[-1, 0]"),
                   ("[7, 8, 9] * 40000", "[7, 8, 9]")],
    },
    "applied_window_max": {
        "level": "응용",
        "title": "구간 합 최댓값",
        "statement": "정수 리스트 nums 와 정수 k 가 주어질 때, 연속한 k 개 원소 합의 최댓값을 돌려주세요. 1 ≤ k ≤ len(nums) 입니다.",
        "signature": "def solution(nums: list[int], k: int) -> int:",
        "starter": "def solution(nums: list[int], k: int) -> int:\n    # 여기에 코드를 작성하세요\n    return 0\n",
        "examples": [("[1, 3, 2], 2", "5"), ("[-1, -2, -3], 1", "-1")],
        "hidden": [("[5], 1", "5"), ("[1, 2, 3, 4, 5], 5", "15"), ("[4, -1, 2, 1], 2", "3"),
                   ("[0, 0, 0, 7, 0], 3", "7"), ("list(range(100000)), 3", "299994")],
    },
    "applied_top_k_words": {
        "level": "응용",
        "title": "자주 나온 단어 k개",
        "statement": (
            "단어 리스트 words 와 정수 k 가 주어질 때, "
            "많이 나온 순서로 단어 k 개를 돌려주세요. "
            "횟수가 같으면 사전 순으로 앞선 단어가 먼저입니다. "
            "1 ≤ k ≤ 서로 다른 단어 수입니다."
        ),
        "signature": "def solution(words: list[str], k: int) -> list[str]:",
        "starter": "def solution(words: list[str], k: int) -> list[str]:\n    # 여기에 코드를 작성하세요\n    return []\n",
        "examples": [("['a', 'b', 'a'], 1", "['a']"), ("['b', 'a', 'c', 'c'], 2", "['c', 'a']")],
        "hidden": [("['x'], 1", "['x']"), ("['c', 'b', 'a'], 3", "['a', 'b', 'c']"), ("['a', 'a', 'b', 'b', 'c'], 2", "['a', 'b']"),
                   ("['d', 'd', 'd', 'a', 'a', 'z'], 3", "['d', 'a', 'z']"),
                   ("[str(i % 1000) for i in range(100000)] + ['999'], 2", "['999', '0']")],
    },
    "applied_chunk_tokens": {
        "level": "응용",
        "title": "문서 청크 나누기",
        "statement": (
            "정수 리스트 tokens 를 길이 size 인 청크로 나눠 돌려주세요. "
            "다음 청크는 앞 청크의 마지막 overlap 개와 겹치게 시작합니다(시작 위치가 size - overlap 씩 뒤로 갑니다). "
            "청크가 리스트 끝에 닿으면 멈추며, 마지막 청크는 size 보다 짧을 수 있습니다. "
            "tokens 가 비어 있으면 빈 리스트입니다. "
            "0 ≤ overlap < size 입니다."
        ),
        "signature": "def solution(tokens: list[int], size: int, overlap: int) -> list[list[int]]:",
        "starter": "def solution(tokens: list[int], size: int, overlap: int) -> list[list[int]]:\n    # 여기에 코드를 작성하세요\n    return []\n",
        "examples": [("[1, 2, 3, 4, 5], 3, 1", "[[1, 2, 3], [3, 4, 5]]"), ("[1, 2, 3, 4], 2, 0", "[[1, 2], [3, 4]]")],
        "hidden": [("[], 3, 1", "[]"), ("[1], 3, 1", "[[1]]"), ("[1, 2, 3, 4], 3, 1", "[[1, 2, 3], [3, 4]]"),
                   ("[1, 2, 3, 4, 5], 2, 1", "[[1, 2], [2, 3], [3, 4], [4, 5]]"), ("[1, 2, 3], 3, 2", "[[1, 2, 3]]"),
                   ("[1, 2, 3, 4, 5], 2, 0", "[[1, 2], [3, 4], [5]]")],
    },
    "applied_merge_intervals": {
        "level": "응용",
        "title": "시간 구간 합치기",
        "statement": (
            "[시작, "
            "끝] 구간의 리스트 intervals 에서 겹치거나 맞닿은 구간을 합쳐, "
            "시작 순으로 정렬한 리스트를 돌려주세요. "
            "입력은 정렬되어 있지 않을 수 있습니다. "
            "각 구간은 시작 ≤ 끝 입니다."
        ),
        "signature": "def solution(intervals: list[list[int]]) -> list[list[int]]:",
        "starter": "def solution(intervals: list[list[int]]) -> list[list[int]]:\n    # 여기에 코드를 작성하세요\n    return []\n",
        "examples": [("[[1, 3], [2, 6], [8, 9]]", "[[1, 6], [8, 9]]"), ("[[1, 2], [2, 3]]", "[[1, 3]]")],
        "hidden": [("[]", "[]"), ("[[5, 5]]", "[[5, 5]]"), ("[[8, 9], [1, 3]]", "[[1, 3], [8, 9]]"),
                   ("[[1, 10], [2, 3], [4, 5]]", "[[1, 10]]"), ("[[1, 2], [4, 5], [3, 3]]", "[[1, 2], [3, 3], [4, 5]]"),
                   ("[[i, i + 1] for i in range(100000)]", "[[0, 100000]]")],
    },
    "applied_longest_unique": {
        "level": "응용",
        "title": "중복 없는 가장 긴 구간",
        "statement": "문자열 text 에서 같은 글자가 두 번 나오지 않는 연속 구간 중 가장 긴 구간의 길이를 돌려주세요. 빈 문자열이면 0 입니다.",
        "signature": "def solution(text: str) -> int:",
        "starter": "def solution(text: str) -> int:\n    # 여기에 코드를 작성하세요\n    return -1\n",
        "examples": [("'abcabcbb'", "3"), ("'bbbb'", "1")],
        "hidden": [("''", "0"), ("'a'", "1"), ("'pwwkew'", "3"), ("'abba'", "2"), ("'abcdef'", "6"),
                   ("''.join(chr(0xAC00 + i) for i in range(50000)) * 2", "50000")],
    },
}


def pickProblems(applicationId: str) -> list[str]:
    """지원 건마다 기초 1 · 응용 1 을 고른다. 같은 지원 건은 언제나 같은 문제다. 고른 결과는 coding_submissions 에 남는다."""
    picked = []
    for level in LEVELS:
        keys = sorted(k for k, p in PROBLEMS.items() if p["level"] == level)
        digest = hashlib.sha256(f"{applicationId}:{level}".encode()).digest()
        picked.append(keys[int.from_bytes(digest[:8], "big") % len(keys)])
    return picked


def publicView(problemNo: int, key: str) -> dict:
    p = PROBLEMS[key]
    return {
        "problem_no": problemNo,
        "level": p["level"],
        "title": p["title"],
        "statement": p["statement"],
        "signature": p["signature"],
        "starter": p["starter"],
        "examples": [{"input": i, "output": o} for i, o in p["examples"]],
        "limits": {"time_sec": 10, "memory_mb": 256},
    }
