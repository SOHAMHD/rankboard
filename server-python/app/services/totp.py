import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

DIGITS = 6
PERIOD = 30
ALGORITHM = "SHA1"


def generate_secret(num_bytes: int = 20) -> str:
    return base64.b32encode(secrets.token_bytes(num_bytes)).decode("ascii").rstrip("=")


def _b32decode(secret_b32: str) -> bytes:
    s = secret_b32.strip().replace(" ", "").upper()
    pad = "=" * ((8 - len(s) % 8) % 8)
    return base64.b32decode(s + pad)


def _hotp(secret_b32: str, counter: int, digits: int = DIGITS) -> str:
    key = _b32decode(secret_b32)
    msg = struct.pack(">Q", counter)
    digest = hmac.new(key, msg, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    binary = (
        (digest[offset] & 0x7F) << 24
        | (digest[offset + 1] & 0xFF) << 16
        | (digest[offset + 2] & 0xFF) << 8
        | (digest[offset + 3] & 0xFF)
    )
    return str(binary % (10 ** digits)).zfill(digits)


def code_at(secret_b32: str, at: float | None = None, digits: int = DIGITS,
            period: int = PERIOD) -> str:
    now = int(at if at is not None else time.time())
    return _hotp(secret_b32, now // period, digits)


def verify(secret_b32: str, code: str, at: float | None = None,
           window: int = 1, digits: int = DIGITS, period: int = PERIOD) -> bool:
    if not secret_b32 or not code:
        return False
    cleaned = str(code).strip().replace(" ", "")
    if not cleaned.isdigit():
        return False
    cleaned = cleaned.zfill(digits)
    now = int(at if at is not None else time.time())
    counter = now // period
    for drift in range(-window, window + 1):
        candidate = _hotp(secret_b32, counter + drift, digits)
        if hmac.compare_digest(candidate, cleaned):
            return True
    return False


def provisioning_uri(secret_b32: str, account_name: str, issuer: str) -> str:
    label = quote(f"{issuer}:{account_name}")
    params = (
        f"secret={secret_b32}"
        f"&issuer={quote(issuer)}"
        f"&algorithm={ALGORITHM}"
        f"&digits={DIGITS}"
        f"&period={PERIOD}"
    )
    return f"otpauth://totp/{label}?{params}"
