
PERMISSIONS = {
    "Super Admin": {"manageUsers": True,  "addProject": True,  "toggleProject": True,  "deleteProject": True,  "addKeyword": True,  "recordRank": True,  "deleteKeyword": True,  "assignProjects": True},
    "Admin":       {"manageUsers": False, "addProject": True,  "toggleProject": True,  "deleteProject": True,  "addKeyword": True,  "recordRank": True,  "deleteKeyword": True,  "assignProjects": True},
    "Team":        {"manageUsers": False, "addProject": False, "toggleProject": False, "deleteProject": False, "addKeyword": True,  "recordRank": True,  "deleteKeyword": False, "assignProjects": False},
    "Client":      {"manageUsers": False, "addProject": False, "toggleProject": False, "deleteProject": False, "addKeyword": False, "recordRank": False, "deleteKeyword": False, "assignProjects": False},
}

ROLES = list(PERMISSIONS.keys())

ADMIN_ROLE = "Super Admin"
SCOPED_ROLES = frozenset({"Team", "Client"})
AUTHOR_ROLES = frozenset({"Super Admin", "Admin", "Team"})
SENDER_ROLES = frozenset({"Super Admin", "Admin"})
DELETER_ROLES = frozenset({"Super Admin", "Admin"})

EMAIL_2FA_ROLES = frozenset()

READ_ONLY_ROLES = frozenset()


def can(role: str, action: str) -> bool:
    return PERMISSIONS.get(role, {}).get(action, False)
