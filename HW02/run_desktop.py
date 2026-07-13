import socket
import subprocess
import threading
import time
import urllib.request
from urllib.parse import urlparse
import os

import uvicorn
import webview
from dotenv import load_dotenv

HOST = "127.0.0.1"
CONTAINER_NAME = "hw02-postgres"


def find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((HOST, 0))
        return s.getsockname()[1]


PORT = find_free_port()


def _docker(*args, check=False):
    try:
        return subprocess.run(["docker", *args], capture_output=True, text=True, check=check)
    except FileNotFoundError:
        print("Docker를 찾을 수 없습니다. Docker Desktop이 설치되어 실행 중인지 확인해주세요.")
        raise SystemExit(1)
    except subprocess.CalledProcessError as e:
        print(f"Docker 명령이 실패했습니다: {e.stderr.strip()}")
        raise SystemExit(1)


def _wait_for_postgres_ready(user, attempts=30, interval=1.0):
    for _ in range(attempts):
        result = _docker("exec", CONTAINER_NAME, "pg_isready", "-U", user)
        if result.returncode == 0:
            return
        time.sleep(interval)
    print("Postgres 컨테이너가 준비될 때까지 기다렸지만 응답이 없습니다.")
    raise SystemExit(1)


def ensure_postgres_container():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        return

    parsed = urlparse(database_url)
    if parsed.hostname not in ("localhost", "127.0.0.1"):
        return

    port = parsed.port or 5432
    user = parsed.username
    password = parsed.password
    db_name = parsed.path.lstrip("/")

    status = _docker("inspect", "-f", "{{.State.Running}}", CONTAINER_NAME)
    if status.returncode != 0:
        _docker(
            "run", "-d", "--name", CONTAINER_NAME,
            "-e", f"POSTGRES_USER={user}",
            "-e", f"POSTGRES_PASSWORD={password}",
            "-e", f"POSTGRES_DB={db_name}",
            "-p", f"{port}:5432",
            "postgres:16",
            check=True,
        )
    elif status.stdout.strip() == "false":
        _docker("start", CONTAINER_NAME, check=True)

    _wait_for_postgres_ready(user)


def run_server():
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")


def wait_for_server():
    url = f"http://{HOST}:{PORT}/"
    for _ in range(50):
        try:
            urllib.request.urlopen(url, timeout=0.5)
            return
        except Exception:
            time.sleep(0.2)


if __name__ == "__main__":
    load_dotenv()
    ensure_postgres_container()
    from contact_app.main import app

    threading.Thread(target=run_server, daemon=True).start()
    wait_for_server()
    webview.create_window("연락처 관리 서비스", f"http://{HOST}:{PORT}/", width=1200, height=900)
    webview.start()
