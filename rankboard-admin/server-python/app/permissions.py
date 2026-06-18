"""PERMISSIONS — the single source of truth, same matrix as the Node
server. Components in the React app never see this file; they receive
a copy of their role's row via /api/auth/me. Enforcement happens in
security.require_permission on every request.

← provisional rows: Team and Client rules are placeholders until
decided. Flip booleans here and both API enforcement and the UI follow.
"""

PERMISSIONS = {
    #                manageUsers  addProject  toggleProject  deleteProject  addKeyword  deleteKeyword
    "Super Admin": {"manageUsers": True,  "addProject": True,  "toggleProject": True,  "deleteProject": True,  "addKeyword": True,  "deleteKeyword": True},
    "Admin":       {"manageUsers": False, "addProject": True,  "toggleProject": True,  "deleteProject": True,  "addKeyword": True,  "deleteKeyword": True},   # a.k.a. Manager
    "Team":        {"manageUsers": False, "addProject": False, "toggleProject": False, "deleteProject": False, "addKeyword": True,  "deleteKeyword": True},   # ← provisional
    "Client":      {"manageUsers": False, "addProject": False, "toggleProject": False, "deleteProject": False, "addKeyword": False, "deleteKeyword": False},  # ← provisional: read-only
}

ROLES = list(PERMISSIONS.keys())


def can(role: str, action: str) -> bool:
    """Default-deny: unknown role or unknown action -> False."""
    return PERMISSIONS.get(role, {}).get(action, False)
