import secrets
import sqlite3
from datetime import datetime, timedelta

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from ..db import get_db
from ..permissions import PERMISSIONS
from ..services import throttle
from ..security import (
    create_pending_token,
    create_token,
    require_active_user,
    require_auth,
    token_claims,
)
from ..services import totp, twofa
# send_login_code_email is no longer imported: its only caller was the email-2FA
# code issuer, removed with that flow. The sender itself stays in email_service
# in case an email second factor is ever wanted again.
from ..services.email_service import send_password_code_email

router = APIRouter()

ISSUER = "SEO Dashboard"

EMAIL_CODE_TTL_MINUTES = 10
EMAIL_CODE_MAX_ATTEMPTS = 5

PASSWORD_OTP_ENABLED = True

_DUMMY_PW_HASH = bcrypt.hashpw(b"timing-equaliser-not-a-real-password", bcrypt.gensalt()).decode()


def _mask_email(email: str) -> str:
    name, _, domain = email.partition("@")
    shown = name[:2] if len(name) > 2 else name[:1]
    return f"{shown}***@{domain}" if domain else email


def _token_version(db: sqlite3.Connection, user_id: int) -> int:
    """The user's current token_version, read fresh.

    Every token must carry this. A token minted with a stale value is refused by
    require_auth, so reading it at mint time is what keeps a password change from
    locking out the very session that performed it.
    """
    row = db.execute("SELECT token_version FROM users WHERE id = ?", (user_id,)).fetchone()
    return int((row["token_version"] if row is not None else 0) or 0)


def _reissue(db: sqlite3.Connection, user: sqlite3.Row, tfa: str = "verified") -> str:
    """A replacement token for the caller, after their token_version was bumped.

    `tfa` defaults to "verified" because most callers sit behind
    require_active_user, which already refused anything else. Callers reachable
    with a pending token must pass the caller's own claim through, or the
    replacement quietly promotes a half-authenticated session.
    """
    return create_token(user["id"], user["role"], tfa,
                        token_version=_token_version(db, user["id"]))


def _advance(user: sqlite3.Row, db: sqlite3.Connection, extra: dict | None = None) -> dict:
    """Issue a fully verified session token.

    There was a second branch here for an email-code step gated on
    EMAIL_2FA_ROLES, which was an empty frozenset — so it could never run. It has
    been removed along with the /2fa/verify-email and /2fa/resend-email endpoints
    and the email_otp table. TOTP two-factor is unaffected and still enforced.
    """
    extra = extra or {}
    return {
        "token": create_token(user["id"], user["role"], "verified",
                              token_version=_token_version(db, user["id"])),
        "user": public_user(user),
        "stage": "done",
        **extra,
    }


def public_user(u: sqlite3.Row) -> dict:
    return {
        "id": u["id"],
        "name": u["name"],
        "email": u["email"],
        "role": u["role"],
        "status": u["status"],
        "mustChangePassword": bool(u["must_change_password"]),
        "permissions": PERMISSIONS.get(u["role"], {}),
    }


def twofa_state(user: sqlite3.Row, claims: dict | None = None) -> dict:
    return {
        "required": True,
        "enrolled": bool(user["totp_enabled"]),
        "verified": (claims or {}).get("tfa") in (None, "verified"),
    }


class LoginIn(BaseModel):
    email: str
    password: str


@router.post("/login")
def login(body: LoginIn, request: Request, db: sqlite3.Connection = Depends(get_db)):
    email = body.email.strip().lower()
    ip = request.client.host if request.client else "?"
    key = f"{ip}|{email}"
    wait = throttle.login_retry_after(key)
    if wait:
        raise HTTPException(429, f"Too many attempts. Try again in about {wait} seconds.")

    user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()

    hashed = user["password_hash"] if user is not None else _DUMMY_PW_HASH
    # bcrypt 5 raises on inputs past 72 bytes rather than truncating, so an
    # over-long password would have come back as a 500 instead of a failed
    # sign-in. No password we store can be longer than this, so it is simply
    # wrong — treated as such, with the same generic message and the same
    # throttle hit so it isn't a free probe.
    if len(body.password.encode()) > 72:
        throttle.login_failed(key)
        raise HTTPException(401, "No account matches that email and password.")
    password_ok = bcrypt.checkpw(body.password.encode(), hashed.encode())
    if user is None or not password_ok:
        throttle.login_failed(key)
        raise HTTPException(401, "No account matches that email and password.")

    throttle.login_ok(key)
    token = create_pending_token(user["id"], user["role"],
                                 token_version=_token_version(db, user["id"]))
    return {
        "token": token,
        "user": public_user(user),
        "twofa": {"required": True, "enrolled": bool(user["totp_enabled"]), "verified": False},
    }


@router.get("/me")
def me(user: sqlite3.Row = Depends(require_auth), claims: dict = Depends(token_claims)):
    return {"user": public_user(user), "twofa": twofa_state(user, claims)}


class SetPasswordIn(BaseModel):
    newPassword: str


@router.post("/set-password")
def set_password(
    body: SetPasswordIn,
    user: sqlite3.Row = Depends(require_auth),
    claims: dict = Depends(token_claims),
    db: sqlite3.Connection = Depends(get_db),
):
    if len(body.newPassword) < 8:
        raise HTTPException(400, "Password needs at least 8 characters.")
    # bcrypt raises past 72 bytes rather than truncating, so this is a real limit
    # rather than a policy one.
    if len(body.newPassword.encode()) > 72:
        raise HTTPException(400, "Password is too long (72 bytes max).")

    tfa = (claims or {}).get("tfa") or "verified"
    # This endpoint is the invite bootstrap and nothing else. A brand-new user has
    # no TOTP enrolled yet, so the temporary password from the invite email is the
    # only credential they have and it must be enough to set a permanent one. That
    # is a deliberate trade-off — the invite email is a complete credential until
    # first sign-in — and is why invites are throttled and the temporary password
    # is redacted from the email log.
    #
    # Outside that bootstrap there is nothing to allow: an established user goes
    # through /password/change, which asks for an emailed code. So `must_change_password`
    # is required either way, and the pending case gets the more specific message.
    if not user["must_change_password"]:
        if tfa == "pending":
            raise HTTPException(403, "Finish two-step verification before changing your password.")
        raise HTTPException(403, "Use the change-password flow instead.")

    new_hash = bcrypt.hashpw(body.newPassword.encode(), bcrypt.gensalt()).decode()
    db.execute(
        "UPDATE users SET password_hash = ?, must_change_password = 0, status = 'active',"
        "       token_version = token_version + 1 WHERE id = ?",
        (new_hash, user["id"]),
    )
    # The bump above invalidated every token for this user, this request's
    # included. Hand back a replacement so the caller stays signed in while
    # everyone else is signed out — carrying the caller's own 2FA state, not a
    # fresh "verified". Setting a password is not a second factor: a pending user
    # stays pending and still has to complete TOTP.
    return {"ok": True, "token": _reissue(db, user, tfa)}


class CodeIn(BaseModel):
    code: str


@router.post("/2fa/enroll")
def twofa_enroll(user: sqlite3.Row = Depends(require_auth), db: sqlite3.Connection = Depends(get_db)):
    row = db.execute("SELECT totp_enabled FROM users WHERE id = ?", (user["id"],)).fetchone()
    if row and row["totp_enabled"]:
        raise HTTPException(400, "Two-step verification is already set up.")
    secret = totp.generate_secret()
    db.execute("UPDATE users SET totp_secret = ? WHERE id = ?", (secret, user["id"]))
    return {"secret": secret, "otpauthUri": totp.provisioning_uri(secret, user["email"], ISSUER)}


@router.post("/2fa/enroll/confirm")
def twofa_enroll_confirm(
    body: CodeIn,
    user: sqlite3.Row = Depends(require_auth),
    db: sqlite3.Connection = Depends(get_db),
):
    row = db.execute(
        "SELECT totp_secret, totp_enabled FROM users WHERE id = ?", (user["id"],)
    ).fetchone()
    if row is None or not row["totp_secret"]:
        raise HTTPException(400, "Start two-step setup first.")
    if row["totp_enabled"]:
        raise HTTPException(400, "Two-step verification is already set up.")
    if not totp.verify(row["totp_secret"], body.code):
        raise HTTPException(400, "That code didn't match — check the app and try again.")

    db.execute("UPDATE users SET totp_enabled = 1 WHERE id = ?", (user["id"],))
    db.execute("DELETE FROM twofa_backup_codes WHERE user_id = ?", (user["id"],))
    codes = twofa.generate_backup_codes()
    db.executemany(
        "INSERT INTO twofa_backup_codes (user_id, code_hash) VALUES (?, ?)",
        [(user["id"], twofa.hash_code(c)) for c in codes],
    )
    return _advance(user, db, extra={"backupCodes": codes})


@router.post("/2fa/verify")
def twofa_verify(
    body: CodeIn,
    user: sqlite3.Row = Depends(require_auth),
    db: sqlite3.Connection = Depends(get_db),
):
    wait = throttle.twofa_retry_after(user["id"])
    if wait:
        raise HTTPException(429, f"Too many attempts. Try again in about {wait} seconds.")
    row = db.execute(
        "SELECT totp_secret, totp_enabled FROM users WHERE id = ?", (user["id"],)
    ).fetchone()
    if row is None or not row["totp_enabled"] or not row["totp_secret"]:
        raise HTTPException(400, "Set up two-step verification first.")
    if throttle.code_replayed(user["id"], body.code):
        raise HTTPException(401, "That code was already used — wait for a new one.")
    if not totp.verify(row["totp_secret"], body.code):
        throttle.twofa_failed(user["id"])
        raise HTTPException(401, "That code isn't right. Try again.")
    throttle.mark_code_consumed(user["id"], body.code)
    throttle.twofa_ok(user["id"])
    return _advance(user, db)


@router.post("/2fa/verify-backup")
def twofa_verify_backup(
    body: CodeIn,
    user: sqlite3.Row = Depends(require_auth),
    db: sqlite3.Connection = Depends(get_db),
):
    wait = throttle.twofa_retry_after(user["id"])
    if wait:
        raise HTTPException(429, f"Too many attempts. Try again in about {wait} seconds.")
    rows = db.execute(
        "SELECT id, code_hash FROM twofa_backup_codes WHERE user_id = ? AND used_at IS NULL",
        (user["id"],),
    ).fetchall()
    for r in rows:
        if twofa.check_code(body.code, r["code_hash"]):
            db.execute(
                "UPDATE twofa_backup_codes SET used_at = datetime('now') WHERE id = ?", (r["id"],)
            )
            throttle.twofa_ok(user["id"])
            return _advance(user, db, extra={"backupRemaining": len(rows) - 1})
    throttle.twofa_failed(user["id"])
    raise HTTPException(401, "That backup code isn't valid.")


@router.get("/config")
def auth_config():
    return {"passwordOtpRequired": PASSWORD_OTP_ENABLED}


def _issue_password_code(user: sqlite3.Row, db: sqlite3.Connection) -> None:
    code = f"{secrets.randbelow(1000000):06d}"
    expires = (datetime.utcnow() + timedelta(minutes=EMAIL_CODE_TTL_MINUTES)).strftime("%Y-%m-%d %H:%M:%S")
    db.execute("DELETE FROM password_otp WHERE user_id = ?", (user["id"],))
    db.execute(
        "INSERT INTO password_otp (user_id, code_hash, expires_at, attempts) VALUES (?, ?, ?, 0)",
        (user["id"], twofa.hash_code(code), expires),
    )
    send_password_code_email(db, name=user["name"], email=user["email"], code=code)


@router.post("/password/request-code")
def password_request_code(
    user: sqlite3.Row = Depends(require_active_user),
    db: sqlite3.Connection = Depends(get_db),
):
    if not PASSWORD_OTP_ENABLED:
        return {"ok": True, "otpRequired": False}
    wait = throttle.reset_retry_after(f"pwchange:{user['id']}")
    if wait:
        raise HTTPException(429, f"Too many code requests. Try again in about {wait} seconds.")
    throttle.reset_requested(f"pwchange:{user['id']}")
    _issue_password_code(user, db)
    return {"ok": True, "otpRequired": True, "emailSentTo": _mask_email(user["email"])}


class PasswordChangeIn(BaseModel):
    code: str = ""
    newPassword: str


@router.post("/password/change")
def password_change(
    body: PasswordChangeIn,
    user: sqlite3.Row = Depends(require_active_user),
    db: sqlite3.Connection = Depends(get_db),
):
    if len(body.newPassword) < 8:
        raise HTTPException(400, "Password needs at least 8 characters.")
    if len(body.newPassword.encode()) > 72:
        raise HTTPException(400, "Password is too long (72 bytes max).")
    if PASSWORD_OTP_ENABLED:
        row = db.execute(
            "SELECT code_hash, expires_at, attempts FROM password_otp WHERE user_id = ?", (user["id"],)
        ).fetchone()
        if row is None:
            raise HTTPException(400, "Request a code first.")
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        if now > row["expires_at"]:
            db.execute("DELETE FROM password_otp WHERE user_id = ?", (user["id"],))
            raise HTTPException(401, "That code has expired — request a new one.")
        if row["attempts"] >= EMAIL_CODE_MAX_ATTEMPTS:
            db.execute("DELETE FROM password_otp WHERE user_id = ?", (user["id"],))
            raise HTTPException(429, "Too many attempts — request a new code.")
        if not twofa.check_code(body.code, row["code_hash"]):
            db.execute("UPDATE password_otp SET attempts = attempts + 1 WHERE user_id = ?", (user["id"],))
            raise HTTPException(401, "That code isn't right. Try again.")
    new_hash = bcrypt.hashpw(body.newPassword.encode(), bcrypt.gensalt()).decode()
    db.execute(
        # token_version bump ends every other session: see security.create_token.
        "UPDATE users SET password_hash = ?, must_change_password = 0,"
        "       token_version = token_version + 1 WHERE id = ?",
        (new_hash, user["id"]),
    )
    fresh_token = _reissue(db, user)
    db.execute("DELETE FROM password_otp WHERE user_id = ?", (user["id"],))
    return {"ok": True, "token": fresh_token}


class ForgotRequestIn(BaseModel):
    email: str


@router.post("/forgot-password/request")
def forgot_password_request(
    body: ForgotRequestIn, request: Request, db: sqlite3.Connection = Depends(get_db)
):
    email = body.email.strip().lower()
    ip = request.client.host if request.client else "?"
    key = f"{ip}|{email}"
    if throttle.reset_retry_after(key):
        return {"ok": True}
    throttle.reset_requested(key)
    user = db.execute("SELECT id, name, email FROM users WHERE email = ?", (email,)).fetchone()
    if user is not None:
        _issue_password_code(user, db)
    return {"ok": True}


class ForgotResetIn(BaseModel):
    email: str
    code: str
    newPassword: str


@router.post("/forgot-password/reset")
def forgot_password_reset(body: ForgotResetIn, db: sqlite3.Connection = Depends(get_db)):
    if len(body.newPassword) < 8:
        raise HTTPException(400, "Password needs at least 8 characters.")
    if len(body.newPassword.encode()) > 72:
        raise HTTPException(400, "Password is too long (72 bytes max).")
    email = body.email.strip().lower()
    user = db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
    invalid = HTTPException(401, "That code isn't right or has expired.")
    if user is None:
        raise invalid
    row = db.execute(
        "SELECT code_hash, expires_at, attempts FROM password_otp WHERE user_id = ?", (user["id"],)
    ).fetchone()
    if row is None:
        raise invalid
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    if now > row["expires_at"]:
        db.execute("DELETE FROM password_otp WHERE user_id = ?", (user["id"],))
        raise invalid
    if row["attempts"] >= EMAIL_CODE_MAX_ATTEMPTS:
        db.execute("DELETE FROM password_otp WHERE user_id = ?", (user["id"],))
        raise HTTPException(429, "Too many attempts — request a new code.")
    if not twofa.check_code(body.code, row["code_hash"]):
        db.execute("UPDATE password_otp SET attempts = attempts + 1 WHERE user_id = ?", (user["id"],))
        raise invalid
    new_hash = bcrypt.hashpw(body.newPassword.encode(), bcrypt.gensalt()).decode()
    db.execute(
        # token_version bump ends every other session: see security.create_token.
        "UPDATE users SET password_hash = ?, must_change_password = 0,"
        "       token_version = token_version + 1 WHERE id = ?",
        (new_hash, user["id"]),
    )
    db.execute("DELETE FROM password_otp WHERE user_id = ?", (user["id"],))
    # No replacement token. This route is unauthenticated — an emailed code is
    # the only thing proving anything — so handing one back would let a reset
    # skip both sign-in and the second factor. The frontend already discarded it.
    return {"ok": True}
