"""PERMISSIONS — the single source of truth, same matrix as the Node
server. Components in the React app never see this file; they receive
a copy of their role's row via /api/auth/me. Enforcement happens in
security.require_permission on every request.

"Team" is the read-only "team member" role: it sees every project's data
(it's a staff role in access.STAFF_ROLES, so it bypasses the per-Client
user_projects scoping for reads) but cannot perform ANY mutation — every
write right below is False, and READ_ONLY_ROLES blocks writes at the
middleware level too (see app.main), so no write route can be missed.
"""

PERMISSIONS = {
    #                manageUsers  addProject  toggleProject  deleteProject  addKeyword  deleteKeyword
    "Super Admin": {"manageUsers": True,  "addProject": True,  "toggleProject": True,  "deleteProject": True,  "addKeyword": True,  "deleteKeyword": True},
    "Admin":       {"manageUsers": False, "addProject": True,  "toggleProject": True,  "deleteProject": True,  "addKeyword": True,  "deleteKeyword": True},   # a.k.a. Manager
    "Team":        {"manageUsers": False, "addProject": False, "toggleProject": False, "deleteProject": False, "addKeyword": False, "deleteKeyword": False},  # read-only team member
    "Client":      {"manageUsers": False, "addProject": False, "toggleProject": False, "deleteProject": False, "addKeyword": False, "deleteKeyword": False},  # ← provisional: read-only
}

ROLES = list(PERMISSIONS.keys())

# Roles that may READ everything but must never WRITE. The read-only
# middleware (app.main) returns 403 for any POST/PUT/PATCH/DELETE made by a
# user in this set (except the explicit session/read exemptions there). This
# is enforced by HTTP method, not per-route, so adding a new write route can
# never accidentally leave these roles able to mutate.
READ_ONLY_ROLES = frozenset({"Team"})


def can(role: str, action: str) -> bool:
    """Default-deny: unknown role or unknown action -> False."""
    return PERMISSIONS.get(role, {}).get(action, False)
