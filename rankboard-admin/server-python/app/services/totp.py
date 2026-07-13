"""TIME-BASED ONE-TIME PASSWORDS (TOTP) — RFC 6238, standard library only.

Google Authenticator (and Authy, 1Password, etc.) implement TOTP with SHA-1,
6 digits, a 30-second step. This module speaks exactly that dialect, so a
secret we generate here provisions cleanly into any of those apps.

No third-party dependency: HMAC-SHA1 (RFC 4226 HOTP) evaluated at the current
time-step (RFC 6238). `verify` accepts a small drift window so a code entered a
few seconds before/after the boundary still passes.

Nothing here touches the database or the network — it's pure crypto helpers the
auth router composes. Verified against the official RFC 6238 test vectors (see
the repo test at the bottom of this file's history / scripts).
"""
import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

# Google Authenticator's fixed parameters. Kept as constants (not options) so we
# never accidentally provision a secret the app can't read back.
DIGITS = 6
PERIOD = 30           # seconds per code
ALGORITHM = "SHA1"    # the GA default; matches hashlib.sha1 below


def generate_secret(num_bytes: int = 20) -> str:
    """A fresh random base32 secret (default 160-bit, the RFC-recommended size
    for SHA-1). Base32, no padding — the format Authenticator apps expect."""
    return base64.b32encode(secrets.token_bytes(num_bytes)).decode("ascii").rstrip("=")


def _b32decode(secret_b32: str) -> bytes:
    """Decode a (possibly unpadded, mixed-case) base32 secret to bytes."""
    s = secret_b32.strip().replace(" ", "").upper()
    pad = "=" * ((8 - len(s) % 8) % 8)   # base32 decodes in 8-char blocks
    return base64.b32decode(s + pad)


def _hotp(secret_b32: str, counter: int, digits: int = DIGITS) -> str:
    """RFC 4226 HOTP: HMAC-SHA1(key, counter) → dynamically-truncated N digits."""
    key = _b32decode(secret_b32)
    msg = struct.pack(">Q", counter)                      # 8-byte big-endian counter
    digest = hmac.new(key, msg, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F                            # dynamic truncation offset
    binary = (
        (digest[offset] & 0x7F) << 24
        | (digest[offset + 1] & 0xFF) << 16
        | (digest[offset + 2] & 0xFF) << 8
        | (digest[offset + 3] & 0xFF)
    )
    return str(binary % (10 ** digits)).zfill(digits)


def code_at(secret_b32: str, at: float | None = None, digits: int = DIGITS,
            period: int = PERIOD) -> str:
    """The current TOTP for a secret (mainly for tests / debugging)."""
    now = int(at if at is not None else time.time())
    return _hotp(secret_b32, now // period, digits)


def verify(secret_b32: str, code: str, at: float | None = None,
           window: int = 1, digits: int = DIGITS, period: int = PERIOD) -> bool:
    """True if `code` is valid for `secret_b32` right now (± `window` steps of
    clock drift). Constant-time comparison; rejects blanks/non-digits early."""
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
    """The otpauth:// URI encoded into the enrollment QR code. `account_name`
    is usually the user's email; `issuer` is the app name shown in the app."""
    label = quote(f"{issuer}:{account_name}")
    params = (
        f"secret={secret_b32}"
        f"&issuer={quote(issuer)}"
        f"&algorithm={ALGORITHM}"
        f"&digits={DIGITS}"
        f"&period={PERIOD}"
    )
    return f"otpauth://totp/{label}?{params}"
