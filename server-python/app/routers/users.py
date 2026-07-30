"""USER ROUTES — the admin panel's API, gated by the permission
matrix. The dependency runs before every handler in this file:
unauthorized callers never reach the function bodies at all.
"""
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
    """Access to the People API: full user managers (manageUsers) OR project
    assigners (assignProjects). Manage-only actions below (onboard, delete, role
    change) are further restricted to manageUsers."""
    if can(user["role"], "manageUsers") or can(user["role"], "assignProjects"):
        return user
    raise HTTPException(403, "You don't have permission to do that.")


router = APIRouter(dependencies=[Depends(require_user_admin)])

# Temp passwords skip lookalike characters (0/O, 1/l/I) — people type
# these from an email. secrets.choice is cryptographically random,
# unlike random.choice which is guessable.
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
        # Always present so the edit UI can pre-fill without a null check;
        # only Clients ever have rows in user_projects.
        "projectIds": project_ids or [],
    }


def missing_project_ids(db: sqlite3.Connection, project_ids: list[int]) -> list[int]:
    """Return the subset of project_ids that don't exist in projects (empty
    list = all valid). Used to 400 before touching the join table."""
    if not project_ids:
        return []
    placeholders = ",".join("?" * len(project_ids))
    rows = db.execute(
        f"SELECT id FROM projects WHERE id IN ({placeholders})", tuple(project_ids)
    ).fetchall()
    existing = {r["id"] for r in rows}
    # Preserve caller order, drop duplicates, keep only the truly missing ones.
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
    # One grouped query for every assignment, bucketed by user, so the list
    # stays a single round-trip regardless of how many users/projects exist.
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
    # Only honoured for Client onboarding; ignored for staff roles.
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

    # Validate any project assignments BEFORE creating the user, so a bad id
    # can't leave behind an orphan account. Only Clients get assignments.
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
        # The UNIQUE constraint on email — the DB is the final guard
        # against duplicates, even under race conditions. (INTEGRITY_ERRORS
        # covers both SQLite and Postgres so the guard works on either backend.)
        raise HTTPException(409, "Someone with this email already exists.")

    # Link the validated projects to the new Client. INSERT OR IGNORE leans on
    # the UNIQUE(user_id, project_id) constraint to stay idempotent.
    for pid in assign_ids:
        db.execute(
            "INSERT OR IGNORE INTO user_projects (user_id, project_id) VALUES (?, ?)",
            (cur.lastrowid, pid),
        )

    email_record = send_invite_email(db, name=name, email=email, role=body.role, temp_password=temp_password)
    user = db.execute(
        "SELECT id, name, email, role, status, created_at FROM users WHERE id = ?", (cur.lastrowid,)
    ).fetchone()

    # The ONLY time the temp password leaves the server in plain text —
    # after hashing it cannot be read back.
    return {"user": row_to_user(user, assign_ids), "email": email_record}


@router.post("/{user_id}/resend-invite", dependencies=[Depends(require_permission("manageUsers"))])
def resend_invite(user_id: int, db: sqlite3.Connection = Depends(get_db)):
    user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if user is None:
        raise HTTPException(404, "User not found.")

    # DESTRUCTIVE for an ACTIVE account. Only the temp password's HASH is stored,
    # so the original can never be re-shown — "resend" therefore means issue a NEW
    # temp password and overwrite the old hash. For someone who already set their
    # own password that password STOPS WORKING. Allowed deliberately (admins need
    # to re-send when an invite is lost), and the UI confirms before calling this
    # for an active user.
    #
    # must_change_password = 1 forces the set-password screen on next sign-in, so
    # the emailed temp password can't linger as their real one.
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
    # Both optional and independent: send role, project_ids, both, or neither.
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
            raise HTTPException(400, "You can't change your own role.")  # no lockouts
        # Lockout guard: never let the change leave ZERO admins (the
        # everything-role). If this user is the last ADMIN_ROLE and is being
        # moved off it, refuse — otherwise no one could ever manage users again.
        if user["role"] == ADMIN_ROLE and body.role != ADMIN_ROLE:
            (admin_count,) = db.execute(
                "SELECT COUNT(*) FROM users WHERE role = ?", (ADMIN_ROLE,)
            ).fetchone()
            if admin_count <= 1:
                raise HTTPException(400, f"Can't demote the last {ADMIN_ROLE} — promote someone else first.")
        db.execute("UPDATE users SET role = ? WHERE id = ?", (body.role, user_id))

    if body.project_ids is not None:
        # Validate up front so a bad id 400s before we delete anything.
        new_ids = list(dict.fromkeys(body.project_ids))
        bad = missing_project_ids(db, new_ids)
        if bad:
            raise HTTPException(400, f"These projects don't exist: {', '.join(map(str, bad))}.")
        # Replace the whole set in ONE transaction: delete-then-insert can't
        # leave a partial assignment behind if an insert fails mid-way. (The
        # connection is autocommit, so we open an explicit transaction here.)
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
        raise HTTPException(400, "You can't remove yourself.")  # no lockouts

    cur = db.execute("DELETE FROM users WHERE id = ?", (user_id,))
    if cur.rowcount == 0:
        raise HTTPException(404, "User not found.")
    return {"ok": True}
