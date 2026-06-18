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
    """Proves WHO is calling, then loads them fresh from the DB so role
    changes and deletions apply immediately (never trust stale token data)."""
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


def require_permission(action: str):
    """Proves the caller is ALLOWED, by asking the matrix."""
    def checker(user: sqlite3.Row = Depends(require_auth)) -> sqlite3.Row:
        if not can(user["role"], action):
            raise HTTPException(403, "You don't have permission to do that.")
        return user
    return checker
