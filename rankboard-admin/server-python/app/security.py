"""AUTH DEPENDENCIES — FastAPI's equivalent of Express middleware.

In Express we wrote:   router.use(requireAuth, requireRole(...))
In FastAPI we write:   user = Depends(require_auth)
                       user = Depends(require_permission("addProject"))

Same two questions, same answers:
  401 = we don't know who you are
  403 = we know exactly who you are, and the answer is no
"""
import sqlite3
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, Header, HTTPException

from .config import JWT_SECRET
from .db import get_db
from .permissions import can


def create_token(user_id: int) -> str:
    payload = {"sub": str(user_id), "exp": datetime.now(timezone.utc) + timedelta(hours=8)}
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def require_auth(
    authorization: str | None = Header(default=None),
    db: sqlite3.Connection = Depends(get_db),
) -> sqlite3.Row:
    """Base authentication: proves WHO is calling and loads them fresh from the
    DB so role changes and deletions apply immediately (never trust stale token
    data). Does NOT enforce account standing — used directly only by /me and
    /set-password, the two endpoints a must-change / not-yet-active user must
    still reach. Everything else depends on require_active_user below."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Sign in required.")
    token = authorization[7:]
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(401, "Session expired. Please sign in again.")

    user = db.execute(
        "SELECT id, name, email, role, must_change_password, status FROM users WHERE id = ?",
        (int(payload["sub"]),),
    ).fetchone()
    if user is None:
        raise HTTPException(401, "This account no longer exists.")
    return user


def require_active_user(user: sqlite3.Row = Depends(require_auth)) -> sqlite3.Row:
    """Strict gate for every data/action endpoint: the caller must be ACTIVE
    and must not owe a password reset. A must-change / invited user is blocked
    here (403) but can still log in, load /me, and POST /set-password (which use
    the base require_auth) to get themselves into good standing."""
    if user["status"] != "active":
        raise HTTPException(403, "Your account isn't active yet — set your password to continue.")
    if user["must_change_password"]:
        raise HTTPException(403, "You must set a new password before continuing.")
    return user


def require_permission(action: str):
    """Proves the caller is ALLOWED, by asking the matrix."""
    def checker(user: sqlite3.Row = Depends(require_active_user)) -> sqlite3.Row:
        if not can(user["role"], action):
            raise HTTPException(403, "You don't have permission to do that.")
        return user
    return checker
