"""AI 상자는 밖으로 나가는 망에 붙지 않고, Redis 는 비밀번호 없이 받지 않는다 (논의사항 P3, AC-19)."""

from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

HUGE = Path(__file__).resolve().parents[2]


def services(name: str) -> dict:
    return yaml.safe_load((HUGE / name).read_text(encoding="utf-8"))["services"]


def test_aiContainersStayOnInternalNetworkOnly():
    for name, service in services("compose.ai.yml").items():
        assert service["networks"] == ["internal"], name


def test_modelsAreNeverDownloadedAtRuntime():
    ai = services("compose.ai.yml")
    assert ai["stt"]["environment"]["HF_HUB_OFFLINE"] == "1"
    assert ai["embed"]["environment"]["HF_HUB_OFFLINE"] == "1"
    assert ai["tts"]["environment"]["SUPERTONIC_CACHE_DIR"].startswith("/hf/")  # 지워지지 않는 볼륨에 둔다


def test_fetchFileOpensNetworkOnlyForModelBoxes():
    fetch = services("compose.ai.fetch.yml")
    assert set(fetch) == {"stt", "embed", "tts", "ocr"}
    assert all(service["networks"] == ["front"] for service in fetch.values())


def test_redisRequiresPassword():
    redis = services("compose.infra.yml")["redis"]
    assert "--requirepass" in redis["command"]
    assert any("REDISCLI_AUTH" in item for item in redis["environment"])
    assert "${REDIS_PASSWORD" in services("compose.ai.yml")["stt"]["environment"]["REDIS_URL"]
    appEnv = (HUGE / "compose.app.yml").read_text(encoding="utf-8")
    assert "redis://redis:" not in appEnv and "${REDIS_PASSWORD" in appEnv
