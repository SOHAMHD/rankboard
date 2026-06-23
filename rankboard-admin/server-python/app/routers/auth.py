"""AUTH ROUTES — login, session check, first-time password change.

Pydantic models (LoginIn, SetPasswordIn) replace the manual `req.body`
checks from Express: FastAPI validates the shape BEFORE the handler
runs, and the interactive docs at /docs are generated from them.
"""
import sqlite3

import bcrypt
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..db import get_db
from ..permissions import PERMISSIONS
from ..security import create_token, require_auth

router = APIRouter()


def public_user(u: sqlite3.Row) -> dict:
    """Shape exposed to the client. NEVER includes password_hash —
    what the API doesn't return can't leak. The permissions row is
    included so the UI knows which buttons to draw; the server still
    re-checks every request."""
    return {
        "id": u["id"],
        "name": u["name"],
        "email": u["email"],
        "role": u["role"],
        "status": u["status"],
        "mustChangePassword": bool(u["must_change_password"]),
        "permissions": PERMISSIONS.get(u["role"], {}),
    }


class LoginIn(BaseModel):
    email: str
    password: str


@router.post("/login")
def login(body: LoginIn, db: sqlite3.Connection = Depends(get_db)):
    user = db.execute(
        "SELECT * FROM users WHERE email = ?", (body.email.strip().lower(),)
    ).fetchone()

    # Same generic message whether the email or the password is wrong —
    # no account enumeration.
    if user is None or not bcrypt.checkpw(body.password.encode(), user["password_hash"].encode()):
        raise HTTPException(401, "No account matches that email and password.")

    return {"token": create_token(user["id"], user["role"]), "user": public_user(user)}


@router.get("/me")
def me(user: sqlite3.Row = Depends(require_auth)):
    return {"user": public_user(user)}


class SetPasswordIn(BaseModel):
    newPassword: str


@router.post("/set-password")
def set_password(
    body: SetPasswordIn,
    user: sqlite3.Row = Depends(require_auth),
    db: sqlite3.Connection = Depends(get_db),
):
    if len(body.newPassword) < 8:
        raise HTTPException(400, "Password needs at least 8 characters.")

    new_hash = bcrypt.hashpw(body.newPassword.encode(), bcrypt.gensalt()).decode()
    db.execute(
        "UPDATE users SET password_hash = ?, must_change_password = 0, status = 'active' WHERE id = ?",
        (new_hash, user["id"]),
    )
    return {"ok": True}
