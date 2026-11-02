"""코드 실행 상자 (TRD 9장, ADR-09). 고정 이미지·고정 옵션만 쓰도록 이 한 곳에 모은다 (R-06).

매 실행마다 1회용 컨테이너: 인터넷 없음 · 읽기 전용 · 비루트 · 256MB · CPU 1 · 프로세스 64 · 10초.
코드는 bind mount 가 아니라 환경 변수(base64)로 넣는다 (bind 경로가 호스트 기준이라 보이지 않는 문제를 피함).
1단계는 api 가 직접 부르고, 2단계에서 worker 의 'sandbox' 작업 줄로 옮긴다.

채점 위조 방지: 기대값은 상자 안에 넣지 않는다. 상자는 입력별 실행 결과(repr)만 돌려주고,
정답 비교는 상자 밖(이 모듈)에서 한다. 상자 출력은 지원자 코드가 마음대로 찍을 수 있으므로 형식·개수를 검증한다.
"""

import ast
import base64
import json
import secrets
import threading

import docker
from docker.errors import DockerException, ImageNotFound
from docker.types import LogConfig

IMAGE = "python:3.11-slim"
TIME_LIMIT_SEC = 10
MAX_OUTPUT = 4000
MAX_LOG_BYTES = 512 * 1024
MAX_REPR = 10_000
MAX_PARALLEL = 2

_slots = threading.BoundedSemaphore(MAX_PARALLEL)

# 지원자 코드는 exec 로 따로 실행하고, 입력별 결과를 표식 + 한 줄 JSON 으로 마지막에 찍는다
HARNESS = r'''
import json, sys, io, time, traceback, contextlib
import os, base64
payload = json.loads(base64.b64decode(os.environ.pop("HUGE_PAYLOAD")))
mark = payload["mark"]
results = []
namespace = {}
try:
    compile(payload["code"], "solution.py", "exec")
except SyntaxError as exc:
    print(mark + json.dumps({"status": "syntax_error", "error": f"{exc.msg} (line {exc.lineno})"}))
    sys.exit(0)
try:
    exec(payload["code"], namespace)
    solution = namespace["solution"]
except Exception:
    print(mark + json.dumps({"status": "runtime_error", "error": traceback.format_exc(limit=2)[-1500:]}))
    sys.exit(0)
for no, args in enumerate(payload["args"], start=1):
    out = io.StringIO()
    started = time.perf_counter()
    try:
        with contextlib.redirect_stdout(out):
            actual = eval(f"solution({args})", {"solution": solution})
        results.append({"no": no, "actual": repr(actual)[:10000], "stdout": out.getvalue()[-500:], "stderr": "", "time_ms": round((time.perf_counter() - started) * 1000)})
    except MemoryError:
        print(mark + json.dumps({"status": "memory_exceeded", "results": results}))
        sys.exit(0)
    except Exception:
        results.append({"no": no, "actual": None, "stdout": out.getvalue()[-500:], "stderr": traceback.format_exc(limit=2)[-1500:], "time_ms": round((time.perf_counter() - started) * 1000)})
print(mark + json.dumps({"status": "ran", "results": results}))
'''


class SandboxBusy(Exception):
    pass


class SandboxInfraError(Exception):
    """인프라 오류는 오답이 아니다 (기술 아키텍처 6-6)."""


def expectedRepr(expected: str) -> str:
    return repr(ast.literal_eval(expected))


def judge(raw: dict, cases: list[tuple[str, str]]) -> dict:
    """상자가 돌려준 실행 결과를 기대값과 비교한다. 형식이 틀리면 실행 오류로 본다."""
    status = raw.get("status")
    if status in ("syntax_error", "runtime_error", "memory_exceeded") and not raw.get("results"):
        return {"status": status, "results": [], "error": str(raw.get("error") or "")[:1500] or None}
    items = raw.get("results")
    if not isinstance(items, list) or len(items) > len(cases):
        return {"status": "runtime_error", "results": [], "error": "실행 결과 형식이 올바르지 않습니다."}
    results = []
    for no, (_args, expected) in enumerate(cases, start=1):
        item = items[no - 1] if no <= len(items) and isinstance(items[no - 1], dict) else {}
        actual = item.get("actual")
        actual = actual if isinstance(actual, str) else None
        stderr = str(item.get("stderr") or "")[:1500]
        results.append({
            "no": no, "passed": actual is not None and not stderr and actual == expectedRepr(expected),
            "actual": actual[:200] if actual else None, "stdout": str(item.get("stdout") or "")[:500], "stderr": stderr,
            "time_ms": item.get("time_ms") if isinstance(item.get("time_ms"), int) else 0,
        })
    if status == "memory_exceeded":
        final = "memory_exceeded"
    elif len(items) < len(cases) or any(r["stderr"] for r in results):
        final = "runtime_error"
    else:
        final = "ok"
    return {"status": final, "results": results}


def readLogs(container) -> str:
    # 무한 출력으로 api 메모리가 차지 않도록 앞쪽 상한까지만 읽고, 표식이 있는 끝부분은 따로 읽는다
    head = bytearray()
    for chunk in container.logs(stdout=True, stderr=True, stream=True):
        head += chunk
        if len(head) >= MAX_LOG_BYTES:
            break
    tail = container.logs(stdout=True, stderr=False, tail=5)
    return (bytes(head[:MAX_LOG_BYTES]) + b"\n" + tail).decode(errors="replace")


def run(code: str, cases: list[tuple[str, str]]) -> dict:
    if not _slots.acquire(timeout=5):
        raise SandboxBusy()
    container = None
    mark = "__HUGE_" + secrets.token_hex(8) + "__"
    try:
        client = docker.from_env()
        payload = {"code": code, "args": [args for args, _ in cases], "mark": mark}
        container = client.containers.create(
            IMAGE,
            command=["python", "-I", "-c", HARNESS],
            environment={"HUGE_PAYLOAD": base64.b64encode(json.dumps(payload).encode()).decode()},
            network_disabled=True,
            read_only=True,
            user="65534:65534",
            mem_limit="256m",
            memswap_limit="256m",
            nano_cpus=1_000_000_000,
            pids_limit=64,
            cap_drop=["ALL"],
            security_opt=["no-new-privileges"],
            tmpfs={"/tmp": "size=16m"},
            working_dir="/tmp",
            log_config=LogConfig(type="json-file", config={"max-size": "1m", "max-file": "1"}),
        )
        container.start()
        try:
            exit_info = container.wait(timeout=TIME_LIMIT_SEC)
        except Exception:  # noqa: BLE001 — wait 시간 초과
            return {"status": "timeout", "results": []}
        if exit_info.get("StatusCode") == 137:
            return {"status": "memory_exceeded", "results": []}
        output = readLogs(container)
        marker = output.rfind(mark)
        if marker < 0:
            return {"status": "runtime_error", "results": [], "error": output[-MAX_OUTPUT:]}
        try:
            raw = json.loads(output[marker + len(mark):].splitlines()[0])
        except (ValueError, IndexError):
            return {"status": "runtime_error", "results": [], "error": "실행 결과를 읽지 못했습니다."}
        return judge(raw if isinstance(raw, dict) else {}, cases)
    except ImageNotFound as exc:
        raise SandboxInfraError("image") from exc
    except DockerException as exc:
        raise SandboxInfraError(type(exc).__name__) from exc
    finally:
        if container is not None:
            try:
                container.remove(force=True)
            except DockerException:
                pass
        _slots.release()
