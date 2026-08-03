import sqlite3

STAFF_ROLES = frozenset({"Super Admin", "Admin"})


def accessible_project_ids(user: sqlite3.Row, db: sqlite3.Connection) -> set[int] | None:
    if user["role"] in STAFF_ROLES:
        return None
    rows = db.execute(
        "SELECT project_id FROM user_projects WHERE user_id = ?", (user["id"],)
    ).fetchall()
    return {r["project_id"] for r in rows}


def user_can_access_project(user: sqlite3.Row, project_id: int, db: sqlite3.Connection) -> bool:
    if user["role"] in STAFF_ROLES:
        return True
    row = db.execute(
        "SELECT 1 FROM user_projects WHERE user_id = ? AND project_id = ?",
        (user["id"], project_id),
    ).fetchone()
    return row is not None
