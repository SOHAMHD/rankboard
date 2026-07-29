"""TWO-FACTOR HELPERS — single-use backup recovery codes.

Backup codes let a user who has lost their authenticator device still sign in.
They're shown ONCE at enrollment, then only their bcrypt hashes are stored
(exactly like passwords), and each is consumed on first use.

TOTP itself lives in totp.py; this module is just the recovery-code side.
"""
import secrets

import bcrypt

BACKUP_CODE_COUNT = 10

# Crockford-ish alphabet: no 0/O/1/I/L so codes are easy to read and type.
_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _normalize(code: str) -> bytes:
    """Codes are compared case-insensitively and ignoring the dash/spaces, so
    'abcd-efgh', 'ABCDEFGH' and 'abcd efgh' all match the same stored hash."""
    return "".join(str(code).split()).replace("-", "").strip().upper().encode()


def generate_backup_codes(n: int = BACKUP_CODE_COUNT) -> list[str]:
    """`n` fresh human-readable codes like 'ABCD-EFGH' (shown once to the user)."""
    codes = []
    for _ in range(n):
        raw = "".join(secrets.choice(_ALPHABET) for _ in range(8))
        codes.append(f"{raw[:4]}-{raw[4:]}")
    return codes


def hash_code(code: str) -> str:
    """bcrypt hash of a normalized code, for storage."""
    return bcrypt.hashpw(_normalize(code), bcrypt.gensalt()).decode()


def check_code(code: str, code_hash: str) -> bool:
    """Constant-time check of a submitted code against one stored hash."""
    try:
        return bcrypt.checkpw(_normalize(code), code_hash.encode())
    except (ValueError, TypeError):
        return False
