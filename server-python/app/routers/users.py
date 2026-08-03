import secrets
import sqlite3

import bcrypt
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..db import INTEGRITY_ERRORS, get_db
from ..permissions import ADMIN_ROLE, ROLES, SCOPED_ROLES, can
from ..security import require_active_user, require_permission
from ..services.email_service import send_invite_email

def require_user_admin(user: sqlite3.Row = Depends(require_active_user)) -> sqlite3.Row:
    if can(user["role"], "manageUsers") or can(user["role"], "assignProjects"):
        return user
    raise HTTPException(403, "You don't have permission to do that.")


router = APIRouter(dependencies=[Depends(require_user_admin)])

_CHARS = "ABCDEFGHJKMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz23456789"


def generate_temp_password() -> str:
    return "".join(secrets.choice(_CHARS) for _ in range(10))


def row_to_user(u: sqlite3.Row, project_ids: list[int] | None = None) -> dict:
    return {
        "id": u["id"],
        "name": u["name"],
        "email": u["email"],
        "role": u["role"],
        "status": u["status"],
        "createdAt": u["created_at"],
        "projectIds": project_ids or [],
    }


def missing_project_ids(db: sqlite3.Connection, project_ids: list[int]) -> list[int]:
    if not project_ids:
        return []
    placeholders = ",".join("?" * len(project_ids))
    rows = db.execute(
        f"SELECT id FROM projects WHERE id IN ({placeholders})", tuple(project_ids)
    ).fetchall()
    existing = {r["id"] for r in rows}
    seen, bad = set(), []
    for pid in project_ids:
        if pid not in existing and pid not in seen:
            bad.append(pid)
        seen.add(pid)
    return bad


@router.get("")
def list_users(db: sqlite3.Connection = Depends(get_db)):
    rows = db.execute(
        "SELECT id, name, email, role, status, created_at FROM users ORDER BY created_at, id"
    ).fetchall()
    assignments: dict[int, list[int]] = {}
    for r in db.execute(
        "SELECT user_id, project_id FROM user_projects ORDER BY project_id"
    ).fetchall():
        assignments.setdefault(r["user_id"], []).append(r["project_id"])
    return {"users": [row_to_user(r, assignments.get(r["id"])) for r in rows]}


class OnboardIn(BaseModel):
    name: str
    email: str
    role: str
    project_ids: list[int] = []


@router.post("", status_code=201, dependencies=[Depends(require_permission("manageUsers"))])
def onboard_user(body: OnboardIn, db: sqlite3.Connection = Depends(get_db)):
    name = body.name.strip()
    email = body.email.strip().lower()

    if not name:
        raise HTTPException(400, "Name is required.")
    if "@" not in email or "." not in email.split("@")[-1]:
        raise HTTPException(400, "A valid email is required.")
    if body.role not in ROLES:
        raise HTTPException(400, "Unknown role.")

    assign_ids = list(dict.fromkeys(body.project_ids)) if body.role in SCOPED_ROLES else []
    bad = missing_project_ids(db, assign_ids)
    if bad:
        raise HTTPException(400, f"These projects don't exist: {', '.join(map(str, bad))}.")

    temp_password = generate_temp_password()
    pw_hash = bcrypt.hashpw(temp_password.encode(), bcrypt.gensalt()).decode()

    try:
        cur = db.execute(
            "INSERT INTO users (name, email, role, password_hash, must_change_password, status)"
            " VALUES (?, ?, ?, ?, 1, 'invited')",
            (name, email, body.role, pw_hash),
        )
    except INTEGRITY_ERRORS:
        raise HTTPException(409, "Someone with this email already exists.")

    for pid in assign_ids:
        db.execute(
            "INSERT OR IGNORE INTO user_projects (user_id, project_id) VALUES (?, ?)",
            (cur.lastrowid, pid),
        )

    email_record = send_invite_email(db, name=name, email=email, role=body.role, temp_password=temp_password)
    user = db.execute(
        "SELECT id, name, email, role, status, created_at FROM users WHERE id = ?", (cur.lastrowid,)
    ).fetchone()

    return {"user": row_to_user(user, assign_ids), "email": email_record}


@router.post("/{user_id}/resend-invite", dependencies=[Depends(require_permission("manageUsers"))])
def resend_invite(user_id: int, db: sqlite3.Connection = Depends(get_db)):
    user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if user is None:
        raise HTTPException(404, "User not found.")

    temp_password = generate_temp_password()
    db.execute(
        "UPDATE users SET password_hash = ?, must_change_password = 1 WHERE id = ?",
        (bcrypt.hashpw(temp_password.encode(), bcrypt.gensalt()).decode(), user_id),
    )
    email_record = send_invite_email(
        db, name=user["name"], email=user["email"], role=user["role"], temp_password=temp_password
    )
    return {"email": email_record}


class UpdateUserIn(BaseModel):
    role: str | None = None
    project_ids: list[int] | None = None


@router.patch("/{user_id}")
def update_user(
    user_id: int,
    body: UpdateUserIn,
    me: sqlite3.Row = Depends(require_user_admin),
    db: sqlite3.Connection = Depends(get_db),
):
    user = db.execute("SELECT id, role FROM users WHERE id = ?", (user_id,)).fetchone()
    if user is None:
        raise HTTPException(404, "User not found.")

    if body.role is not None:
        if not can(me["role"], "manageUsers"):
            raise HTTPException(403, "Only a Super Admin can change roles.")
        if body.role not in ROLES:
            raise HTTPException(400, "Unknown role.")
        if user_id == me["id"]:
            raise HTTPException(400, "You can't change your own role.")
        if user["role"] == ADMIN_ROLE and body.role != ADMIN_ROLE:
            (admin_count,) = db.execute(
                "SELECT COUNT(*) FROM users WHERE role = ?", (ADMIN_ROLE,)
            ).fetchone()
            if admin_count <= 1:
                raise HTTPException(400, f"Can't demote the last {ADMIN_ROLE} — promote someone else first.")
        db.execute("UPDATE users SET role = ? WHERE id = ?", (body.role, user_id))

    if body.project_ids is not None:
        new_ids = list(dict.fromkeys(body.project_ids))
        bad = missing_project_ids(db, new_ids)
        if bad:
            raise HTTPException(400, f"These projects don't exist: {', '.join(map(str, bad))}.")
        db.execute("BEGIN")
        try:
            db.execute("DELETE FROM user_projects WHERE user_id = ?", (user_id,))
            for pid in new_ids:
                db.execute(
                    "INSERT OR IGNORE INTO user_projects (user_id, project_id) VALUES (?, ?)",
                    (user_id, pid),
                )
            db.execute("COMMIT")
        except Exception:
            db.execute("ROLLBACK")
            raise

    return {"ok": True}


@router.delete("/{user_id}")
def remove_user(
    user_id: int,
    me: sqlite3.Row = Depends(require_permission("manageUsers")),
    db: sqlite3.Connection = Depends(get_db),
):
    if user_id == me["id"]:
        raise HTTPException(400, "You can't remove yourself.")

    cur = db.execute("DELETE FROM users WHERE id = ?", (user_id,))
    if cur.rowcount == 0:
        raise HTTPException(404, "User not found.")
    return {"ok": True}
