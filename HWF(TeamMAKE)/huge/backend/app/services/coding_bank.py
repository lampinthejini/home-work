"""코딩테스트 문제 목록 (PRD COD-02: AI/AX 엔지니어 문제 목록에서 기초 1 · 응용 1, Python 3, 60분).

숨겨진 테스트와 정답은 어떤 응답에도 넣지 않는다 (COD-05). 문제 관리 화면은 범위 밖이라 코드에 둔다.
"""

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
}

SELECTED = ["basic_token_count", "applied_window_max"]  # 문제 목록이 늘면 지원 번호로 고르게 바꾼다


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
