import sqlite3
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, Header, HTTPException

from .access import user_can_access_project
from .config import JWT_SECRET
from .db import get_db
from .permissions import can


def create_token(user_id: int, role: str, tfa: str,
                 minutes: int | None = None, token_version: int = 0) -> str:
    """Mint a session token.

    `tfa` has no default on purpose. It used to default to "verified", so any
    caller that forgot to think about the second factor minted a fully verified
    session — the safe-looking call was the unsafe one. Every caller now has to
    say which it means.

    `token_version` is the user's current `users.token_version`, and require_auth
    rejects any token whose value is behind it. That is what makes changing a
    password actually end other sessions: tokens are stateless and last 8 hours,
    so before this the one action a compromised user takes — change my password —
    left the attacker's token working for the rest of its life.
    """
    exp = datetime.now(timezone.utc) + (
        timedelta(minutes=minutes) if minutes else timedelta(hours=8)
    )
    payload = {"sub": str(user_id), "role": role, "tfa": tfa, "exp": exp,
               "tv": int(token_version or 0)}
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def create_pending_token(user_id: int, role: str, token_version: int = 0) -> str:
    return create_token(user_id, role, tfa="pending", minutes=15,
                        token_version=token_version)


def token_claims(authorization: str | None = Header(default=None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Sign in required.")
    try:
        return jwt.decode(authorization[7:], JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(401, "Session expired. Please sign in again.")


def require_auth(
    authorization: str | None = Header(default=None),
    db: sqlite3.Connection = Depends(get_db),
) -> sqlite3.Row:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Sign in required.")
    token = authorization[7:]
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(401, "Session expired. Please sign in again.")

    user = db.execute(
        "SELECT id, name, email, role, must_change_password, status, totp_enabled,"
        "       token_version"
        "  FROM users WHERE id = ?",
        (int(payload["sub"]),),
    ).fetchone()
    if user is None:
        raise HTTPException(401, "This account no longer exists.")

    # Tokens issued before the last password change are refused. Tokens minted
    # before this claim existed carry no "tv"; they're treated as version 0, so
    # they keep working until their natural expiry unless a password has since
    # been changed — which is the behaviour you want during a deploy.
    if int(payload.get("tv") or 0) < int(user["token_version"] or 0):
        raise HTTPException(401, "Your password changed. Please sign in again.")
    return user


def require_active_user(
    user: sqlite3.Row = Depends(require_auth),
    claims: dict = Depends(token_claims),
) -> sqlite3.Row:
    if claims.get("tfa") not in (None, "verified"):
        raise HTTPException(403, "Complete two-step verification to continue.")
    if user["status"] != "active":
        raise HTTPException(403, "Your account isn't active yet — set your password to continue.")
    if user["must_change_password"]:
        raise HTTPException(403, "You must set a new password before continuing.")
    return user


def require_permission(action: str):
    def checker(user: sqlite3.Row = Depends(require_active_user)) -> sqlite3.Row:
        if not can(user["role"], action):
            raise HTTPException(403, "You don't have permission to do that.")
        return user
    return checker


def require_roles(*allowed: str):
    allowed_set = frozenset(allowed)

    def checker(user: sqlite3.Row = Depends(require_active_user)) -> sqlite3.Row:
        if user["role"] not in allowed_set:
            raise HTTPException(403, "You don't have permission to do that.")
        return user

    return checker


def require_project_access(
    project_id: int,
    user: sqlite3.Row = Depends(require_active_user),
    db: sqlite3.Connection = Depends(get_db),
) -> sqlite3.Row:
    if not user_can_access_project(user, project_id, db):
        raise HTTPException(403, "You don't have access to this project.")
    return user


def require_open_project(
    project_id: int,
    user: sqlite3.Row = Depends(require_project_access),
    db: sqlite3.Connection = Depends(get_db),
) -> sqlite3.Row:
    """Access, plus the project not being archived.

    `projects.active` used to be decorative: it was stored and shown as a pill,
    and nothing anywhere read it. An "inactive" project could still be opened,
    have ranks recorded, and have a report generated and emailed to a client you
    had stopped working for.

    Deliberately NOT folded into require_project_access, which guards all ~33
    project-scoped routes — including the PATCH that flips this flag back on and
    the DELETE that removes the project. Those have to keep working on an archived
    project, or it could never be reactivated or cleaned up.

    409 rather than 403: the caller has permission, the project is just in the
    wrong state, and the client distinguishes the two.
    """
    row = db.execute("SELECT active FROM projects WHERE id = ?", (project_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "Project not found.")
    if not row["active"]:
        raise HTTPException(
            409,
            "This project is inactive. Reactivate it from the projects list to open it.",
        )
    return user
