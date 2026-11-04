"""암호화 키가 없거나 틀리면 개발 환경에서도 켜지지 않는다 (논의사항 P4)."""

import base64
from dataclasses import replace

import pytest

from app import crypto


def withKey(monkeypatch, value, profile="dev"):
    monkeypatch.setattr(crypto, "ENV", replace(crypto.ENV, encryptionKey=value, profile=profile))


@pytest.mark.parametrize("profile", ["dev", "prod"])
def test_missingKeyIsRefused(monkeypatch, profile):
    withKey(monkeypatch, "", profile)
    with pytest.raises(RuntimeError, match="APP_ENCRYPTION_KEY"):
        crypto.loadKey()


def test_wrongLengthIsRefused(monkeypatch):
    withKey(monkeypatch, base64.b64encode(b"x" * 16).decode())
    with pytest.raises(RuntimeError, match="32 bytes"):
        crypto.loadKey()


def test_validKeyIsUsed(monkeypatch):
    withKey(monkeypatch, base64.b64encode(b"k" * 32).decode())
    assert crypto.loadKey() == b"k" * 32
