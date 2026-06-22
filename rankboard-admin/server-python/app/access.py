"""PROJECT ACCESS — the ONE place that answers "which projects may this
user touch?" Both the list filter (GET /api/projects) and the per-route
guard (require_project_access) call these helpers, so the two can never
drift apart: change the rule here and both follow.

The rule today: the three staff roles (Super Admin / Admin / Team) see
every project; a Client sees only the projects linked to them in the
user_projects join table. Unknown roles fall through to the Client path
(default-deny: no links → no access).
"""
import sqlite3

# Roles that bypass per-project scoping entirely (they see all projects).
STAFF_ROLES = frozenset({"Super Admin", "Admin", "Team"})


def accessible_project_ids(user: sqlite3.Row, db: sqlite3.Connection) -> set[int] | None:
    """Return None for staff (= every project, no filtering needed), or the
    set of project_ids a Client is assigned to. Used by the list endpoint to
    decide what to return."""
    if user["role"] in STAFF_ROLES:
        return None
    rows = db.execute(
        "SELECT project_id FROM user_projects WHERE user_id = ?", (user["id"],)
    ).fetchall()
    return {r["project_id"] for r in rows}


def user_can_access_project(user: sqlite3.Row, project_id: int, db: sqlite3.Connection) -> bool:
    """True if this user may touch this single project. Staff always may; a
    Client may only if a user_projects row links them to it. Used by the
    per-route guard."""
    if user["role"] in STAFF_ROLES:
        return True
    row = db.execute(
        "SELECT 1 FROM user_projects WHERE user_id = ? AND project_id = ?",
        (user["id"], project_id),
    ).fetchone()
    return row is not None
