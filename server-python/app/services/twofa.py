import secrets

import bcrypt

BACKUP_CODE_COUNT = 10

_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _normalize(code: str) -> bytes:
    return "".join(str(code).split()).replace("-", "").strip().upper().encode()


def generate_backup_codes(n: int = BACKUP_CODE_COUNT) -> list[str]:
    codes = []
    for _ in range(n):
        raw = "".join(secrets.choice(_ALPHABET) for _ in range(8))
        codes.append(f"{raw[:4]}-{raw[4:]}")
    return codes


def hash_code(code: str) -> str:
    return bcrypt.hashpw(_normalize(code), bcrypt.gensalt()).decode()


def check_code(code: str, code_hash: str) -> bool:
    try:
        return bcrypt.checkpw(_normalize(code), code_hash.encode())
    except (ValueError, TypeError):
        return False
