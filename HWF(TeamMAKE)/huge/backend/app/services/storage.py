"""파일 저장소 (S3 호환 RustFS). 모든 객체는 앱에서 AES-256-GCM 으로 암호화해 넣는다 (TRD 4-2).

키 규칙 (기술 아키텍처 8-1): resumes/ · answers/ · recordings/ · questions/
"""

import os

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from ..crypto import NONCE_BYTES, loadKey

BUCKET = "huge"
_aead = AESGCM(loadKey())
_client = None


def client():
    global _client
    if _client is None:
        _client = boto3.client(
            "s3",
            endpoint_url=os.environ.get("S3_ENDPOINT", "http://localhost:9000"),
            aws_access_key_id=os.environ.get("S3_ACCESS_KEY", ""),
            aws_secret_access_key=os.environ.get("S3_SECRET_KEY", ""),
            region_name="us-east-1",
            config=Config(s3={"addressing_style": "path"}, retries={"max_attempts": 3}),
        )
    return _client


def ensureBucket() -> None:
    try:
        client().head_bucket(Bucket=BUCKET)
    except ClientError:
        client().create_bucket(Bucket=BUCKET)


def putObject(key: str, data: bytes, contentType: str = "application/octet-stream") -> None:
    nonce = os.urandom(NONCE_BYTES)
    sealed = nonce + _aead.encrypt(nonce, data, key.encode())  # 키를 AAD 로 묶어 객체 바꿔치기를 막는다
    client().put_object(Bucket=BUCKET, Key=key, Body=sealed, ContentType="application/octet-stream", Metadata={"ct": contentType})


def getObject(key: str) -> tuple[bytes, str]:
    try:
        obj = client().get_object(Bucket=BUCKET, Key=key)
    except ClientError as exc:
        raise FileNotFoundError(key) from exc
    sealed = obj["Body"].read()
    data = _aead.decrypt(sealed[:NONCE_BYTES], sealed[NONCE_BYTES:], key.encode())
    return data, obj.get("Metadata", {}).get("ct", "application/octet-stream")


def listKeys(prefix: str) -> list[str]:
    keys = []
    for page in client().get_paginator("list_objects_v2").paginate(Bucket=BUCKET, Prefix=prefix):
        keys += [o["Key"] for o in page.get("Contents", [])]
    return sorted(keys)


def deletePrefix(prefix: str) -> int:
    count = 0
    paginator = client().get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=BUCKET, Prefix=prefix):
        keys = [{"Key": o["Key"]} for o in page.get("Contents", [])]
        if keys:
            client().delete_objects(Bucket=BUCKET, Delete={"Objects": keys})
            count += len(keys)
    return count
