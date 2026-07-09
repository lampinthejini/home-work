from pwdlib import PasswordHash

password_hash = PasswordHash.recommended()


def hash_password(raw: str) -> str:
    return password_hash.hash(raw)


def verify_password(raw: str, hashed: str) -> bool:
    return password_hash.verify(raw, hashed)
