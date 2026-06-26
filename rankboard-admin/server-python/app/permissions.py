"""PERMISSIONS — the single source of truth for roles, same matrix as the
Node server. Components in the React app never see this file; they receive
a copy of their role's row via /api/auth/me. Enforcement happens in
security.require_permission / security.require_roles on every request.

ROLE MODEL (the report workflow maps onto these existing four values, so
there is exactly ONE role vocabulary — the strings stored in users.role):

  Super Admin  → "admin"        — everything
  Admin        → "manager"      — all projects; authors reports; reviews; the
                                  only role that may SEND to clients (later slice)
  Team         → "team_member"  — all projects; authors reports; CANNOT send
  Client       → "user"         — scoped to assigned projects (user_projects)

"Team" used to be read-only; it is now a WRITE-CAPABLE report author. The
matrix below still grants it none of the project/keyword/user write rights
(those stay Admin+ only); its report-authoring capability is granted by
require_roles(*AUTHOR_ROLES) on the report endpoints (later slices), NOT by
this matrix. READ_ONLY_ROLES is now empty (see below).
"""

PERMISSIONS = {
    #                manageUsers  addProject  toggleProject  deleteProject  addKeyword  deleteKeyword
    "Super Admin": {"manageUsers": True,  "addProject": True,  "toggleProject": True,  "deleteProject": True,  "addKeyword": True,  "deleteKeyword": True},
    "Admin":       {"manageUsers": False, "addProject": True,  "toggleProject": True,  "deleteProject": True,  "addKeyword": True,  "deleteKeyword": True},   # a.k.a. Manager
    "Team":        {"manageUsers": False, "addProject": False, "toggleProject": False, "deleteProject": False, "addKeyword": False, "deleteKeyword": False},  # team member: authors reports (write-capable via require_roles), but no project/keyword writes
    "Client":      {"manageUsers": False, "addProject": False, "toggleProject": False, "deleteProject": False, "addKeyword": False, "deleteKeyword": False},  # ← provisional: read-only
}

ROLES = list(PERMISSIONS.keys())

# ── Role groups for the report workflow ─────────────────────────────────
# The ONE place that says which roles may author / send a report. Later
# slices gate their endpoints with require_roles(*AUTHOR_ROLES) (authoring)
# and require_roles(*SENDER_ROLES) (sending). Adding a role to either set is
# the single-line change to grant that capability — no endpoint edits.
ADMIN_ROLE = "Super Admin"                                   # the "everything" role (spec's `admin`)
AUTHOR_ROLES = frozenset({"Super Admin", "Admin", "Team"})   # may author reports (Team can't send)
SENDER_ROLES = frozenset({"Super Admin", "Admin"})           # may send a report to a client
DELETER_ROLES = frozenset({"Super Admin", "Admin"})          # may HARD-delete a report version, any status (super admin + manager); Team/Client cannot

# Roles that may READ everything but must never WRITE. The read-only
# middleware (app.main) returns 403 for any POST/PUT/PATCH/DELETE made by a
# user in this set. Now EMPTY: "Team" became a write-capable report author, so
# nothing is method-blocked. The machinery stays in place for any future
# read-only role; every existing write route is independently gated by
# require_permission (Team's matrix row is all-False), so dropping Team here
# grants it no existing write power.
READ_ONLY_ROLES = frozenset()


def can(role: str, action: str) -> bool:
    """Default-deny: unknown role or unknown action -> False."""
    return PERMISSIONS.get(role, {}).get(action, False)
