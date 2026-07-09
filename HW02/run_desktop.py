import socket
import threading
import time
import urllib.request

import uvicorn
import webview

from contact_app.main import app

HOST = "127.0.0.1"


def find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((HOST, 0))
        return s.getsockname()[1]


PORT = find_free_port()


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
    threading.Thread(target=run_server, daemon=True).start()
    wait_for_server()
    webview.create_window("연락처 관리 서비스", f"http://{HOST}:{PORT}/", width=1200, height=900)
    webview.start()
