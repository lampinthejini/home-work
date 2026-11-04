"""DB 민감 칸 암호화 (AES-256-GCM, 앱 레벨) — TRD 4-2 · 11장, 기술 아키텍처 8-3."""

import base64
import hashlib
import hmac
import json
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy.types import Text, TypeDecorator

from .config import ENV

NONCE_BYTES = 12


def subjectHash(email: str) -> str:
    """동의 기록의 동의자 표시 (테이블 정의서 4-9). 이메일 목록 대입으로 되돌리지 못하게 서버 키로 HMAC."""
    key = hashlib.sha256(b"huge-consent-subject" + loadKey()).digest()  # 암호화 키를 그대로 쓰지 않고 용도별로 나눈다
    return hmac.new(key, email.strip().lower().encode(), hashlib.sha256).hexdigest()


def ipHash(ip: str) -> str:
    """로그인 차단 표의 IP 표시. IPv4 는 경우의 수가 적어 일반 해시로는 되돌릴 수 있으므로 키를 섞는다."""
    key = hashlib.sha256(b"huge-login-ip" + loadKey()).digest()
    return hmac.new(key, ip.encode(), hashlib.sha256).hexdigest()


def loadKey() -> bytes:
    if not ENV.encryptionKey:  # 개발 환경도 같다. 고정 키로 조용히 켜지면 암호화가 형식만 남는다
        raise RuntimeError("APP_ENCRYPTION_KEY is required")
    key = base64.b64decode(ENV.encryptionKey)
    if len(key) != 32:
        raise RuntimeError("APP_ENCRYPTION_KEY must be 32 bytes (base64)")
    return key


AEAD = AESGCM(loadKey())


def encryptText(plain: str) -> str:
    nonce = os.urandom(NONCE_BYTES)
    return base64.b64encode(nonce + AEAD.encrypt(nonce, plain.encode(), None)).decode()


def decryptText(token: str) -> str:
    raw = base64.b64decode(token)
    return AEAD.decrypt(raw[:NONCE_BYTES], raw[NONCE_BYTES:], None).decode()


class EncryptedText(TypeDecorator):
    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return None if value is None else encryptText(value)

    def process_result_value(self, value, dialect):
        return None if value is None else decryptText(value)


class EncryptedJson(TypeDecorator):
    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return None if value is None else encryptText(json.dumps(value, ensure_ascii=False))

    def process_result_value(self, value, dialect):
        return None if value is None else json.loads(decryptText(value))
