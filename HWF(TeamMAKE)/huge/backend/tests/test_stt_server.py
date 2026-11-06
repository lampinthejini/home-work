"""STT 서버: 변환이 도는 동안에도 /health 가 답해야 한다 (논의사항 E2)."""

import asyncio
import importlib.util
import sys
import threading
import types
from pathlib import Path

import httpx
import pytest

SERVER_PATH = Path(__file__).resolve().parents[2] / "ai" / "stt" / "server.py"


class SlowModel:
    """변환을 시작했다고 알리고, 풀어 줄 때까지 붙잡고 있는 가짜 모델."""

    def __init__(self):
        self.started = threading.Event()
        self.finish = threading.Event()

    def transcribe(self, audio, **options):
        self.started.set()
        assert self.finish.wait(timeout=10), "변환이 풀리지 않았습니다"
        return [], None


class FakeSamples:
    """pcmToFloat 가 쓰는 만큼만 흉내 낸다. 소리 내용은 이 테스트와 무관하다."""

    def __init__(self, count):
        self.count = count

    def astype(self, dtype):
        return self

    def __truediv__(self, other):
        return self

    def __len__(self):
        return self.count


@pytest.fixture
def sttServer(monkeypatch):
    """GPU·모델·Redis·numpy 없이 server.py 를 불러온다 (백엔드 테스트 환경에는 없다)."""
    model = SlowModel()
    monkeypatch.setitem(sys.modules, "numpy", types.SimpleNamespace(
        ndarray=object, int16=None, float32=None, frombuffer=lambda pcm, dtype: FakeSamples(len(pcm) // 2)))
    monkeypatch.setitem(sys.modules, "faster_whisper", types.SimpleNamespace(WhisperModel=lambda *a, **k: model))
    monkeypatch.setitem(sys.modules, "redis", types.SimpleNamespace(
        Redis=types.SimpleNamespace(from_url=lambda url: types.SimpleNamespace()), RedisError=Exception))
    spec = importlib.util.spec_from_file_location("stt_server_under_test", SERVER_PATH)
    module = importlib.util.module_from_spec(spec)
    # 임시 자막 루프는 끝나지 않는 스레드라 띄우지 않는다. 스레드 풀도 start 를 쓰므로 불러올 때만 막는다
    with monkeypatch.context() as loading:
        loading.setattr(threading.Thread, "start", lambda self: None)
        spec.loader.exec_module(module)
    yield module, model
    model.finish.set()


def testHotwordsAreGivenForFinalAndCaption(sttServer):
    module, _ = sttServer
    seen = []

    class RecordingModel:
        def transcribe(self, audio, **options):
            seen.append(options)
            return [], None

    module.model = RecordingModel()
    module.runTranscribe(None, withWords=True)
    module.runTranscribe(None, withWords=False)
    assert all("니즈" in options["hotwords"] and "결측치" in options["hotwords"] for options in seen)
    assert len(seen) == 2


def testHealthAnswersWhileTranscribing(sttServer):
    module, model = sttServer

    async def scenario():
        transport = httpx.ASGITransport(app=module.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://stt") as client:
            job = asyncio.create_task(client.post("/transcribe", content=b"\x00\x00" * 16000))
            # 사건 루프를 막으면 이 대기와 /health 가 함께 멈춘다. 시간 제한으로 그것을 잡는다
            await asyncio.wait_for(asyncio.to_thread(model.started.wait, 5), timeout=5)
            health = await asyncio.wait_for(client.get("/health"), timeout=3)
            assert health.status_code == 200
            assert not job.done()
            model.finish.set()
            result = await asyncio.wait_for(job, timeout=5)
            assert result.status_code == 200
            assert result.json()["audio_sec"] == 1.0

    # 사건 루프가 막혀 있으면 wait_for 도 돌지 못하므로, 풀어 주는 장치를 밖에 둔다
    threading.Timer(8, model.finish.set).start()
    asyncio.run(scenario())
