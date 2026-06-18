"""USER ROUTES — the admin panel's API, gated by the permission
matrix. The dependency runs before every handler in this file:
unauthorized callers never reach the function bodies at all.
"""
import secrets
import sqlite3

import bcrypt
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..db import get_db
from ..permissions import ROLES
from ..security import require_permission
from ..services.email_service import send_invite_email

router = APIRouter(dependencies=[Depends(require_permission("manageUsers"))])

# Temp passwords skip lookalike characters (0/O, 1/l/I) — people type
# these from an email. secrets.choice is cryptographically random,
# unlike random.choice which is guessable.
_CHARS = "ABCDEFGHJKMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz23456789"


def generate_temp_password() -> str:
    return "".join(secrets.choice(_CHARS) for _ in range(10))


def row_to_user(u: sqlite3.Row) -> dict:
    return {
        "id": u["id"],
        "name": u["name"],
        "email": u["email"],
        "role": u["role"],
        "status": u["status"],
        "createdAt": u["created_at"],
    }


@router.get("")
def list_users(db: sqlite3.Connection = Depends(get_db)):
    rows = db.execute(
        "SELECT id, name, email, role, status, created_at FROM users ORDER BY created_at, id"
    ).fetchall()
    return {"users": [row_to_user(r) for r in rows]}


class OnboardIn(BaseModel):
    name: str
    email: str
    role: str


@router.post("", status_code=201)
def onboard_user(body: OnboardIn, db: sqlite3.Connection = Depends(get_db)):
    name = body.name.strip()
    email = body.email.strip().lower()

    if not name:
        raise HTTPException(400, "Name is required.")
    if "@" not in email or "." not in email.split("@")[-1]:
        raise HTTPException(400, "A valid email is required.")
    if body.role not in ROLES:
        raise HTTPException(400, "Unknown role.")

    temp_password = generate_temp_password()
    pw_hash = bcrypt.hashpw(temp_password.encode(), bcrypt.gensalt()).decode()

    try:
        cur = db.execute(
            "INSERT INTO users (name, email, role, password_hash, must_change_password, status)"
            " VALUES (?, ?, ?, ?, 1, 'invited')",
            (name, email, body.role, pw_hash),
        )
    except sqlite3.IntegrityError:
        # The UNIQUE constraint on email — the DB is the final guard
        # against duplicates, even under race conditions.
        raise HTTPException(409, "Someone with this email already exists.")

    email_record = send_invite_email(db, name=name, email=email, role=body.role, temp_password=temp_password)
    user = db.execute(
        "SELECT id, name, email, role, status, created_at FROM users WHERE id = ?", (cur.lastrowid,)
    ).fetchone()

    # The ONLY time the temp password leaves the server in plain text —
    # after hashing it cannot be read back.
    return {"user": row_to_user(user), "email": email_record}


@router.post("/{user_id}/resend-invite")
def resend_invite(user_id: int, db: sqlite3.Connection = Depends(get_db)):
    user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if user is None:
        raise HTTPException(404, "User not found.")
    if user["status"] != "invited":
        raise HTTPException(400, "This person has already activated their account.")

    # Can't re-show the old temp password — only its hash exists. So
    # "resend" = generate a NEW one, overwrite the hash, email again.
    temp_password = generate_temp_password()
    db.execute(
        "UPDATE users SET password_hash = ? WHERE id = ?",
        (bcrypt.hashpw(temp_password.encode(), bcrypt.gensalt()).decode(), user_id),
    )
    email_record = send_invite_email(
        db, name=user["name"], email=user["email"], role=user["role"], temp_password=temp_password
    )
    return {"email": email_record}


class RoleIn(BaseModel):
    role: str


@router.patch("/{user_id}")
def change_role(
    user_id: int,
    body: RoleIn,
    me: sqlite3.Row = Depends(require_permission("manageUsers")),
    db: sqlite3.Connection = Depends(get_db),
):
    if body.role not in ROLES:
        raise HTTPException(400, "Unknown role.")
    if user_id == me["id"]:
        raise HTTPException(400, "You can't change your own role.")  # no lockouts

    cur = db.execute("UPDATE users SET role = ? WHERE id = ?", (body.role, user_id))
    if cur.rowcount == 0:
        raise HTTPException(404, "User not found.")
    return {"ok": True}


@router.delete("/{user_id}")
def remove_user(
    user_id: int,
    me: sqlite3.Row = Depends(require_permission("manageUsers")),
    db: sqlite3.Connection = Depends(get_db),
):
    if user_id == me["id"]:
        raise HTTPException(400, "You can't remove yourself.")  # no lockouts

    cur = db.execute("DELETE FROM users WHERE id = ?", (user_id,))
    if cur.rowcount == 0:
        raise HTTPException(404, "User not found.")
    return {"ok": True}
