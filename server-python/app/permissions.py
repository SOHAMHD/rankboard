
# viewEmailLog is deliberately the *only* True-for-Super-Admin-alone entry
# besides manageUsers. The email log contains every message the system has ever
# sent, including sign-in and password-reset codes — see routers/email_log.py
# for why the code bodies are redacted even for the one role that can read it.
PERMISSIONS = {
    "Super Admin": {"manageUsers": True,  "addProject": True,  "toggleProject": True,  "deleteProject": True,  "addKeyword": True,  "recordRank": True,  "deleteKeyword": True,  "assignProjects": True,  "viewEmailLog": True},
    "Admin":       {"manageUsers": False, "addProject": True,  "toggleProject": True,  "deleteProject": True,  "addKeyword": True,  "recordRank": True,  "deleteKeyword": True,  "assignProjects": True,  "viewEmailLog": False},
    "Team":        {"manageUsers": False, "addProject": False, "toggleProject": False, "deleteProject": False, "addKeyword": True,  "recordRank": True,  "deleteKeyword": False, "assignProjects": False, "viewEmailLog": False},
    "Client":      {"manageUsers": False, "addProject": False, "toggleProject": False, "deleteProject": False, "addKeyword": False, "recordRank": False, "deleteKeyword": False, "assignProjects": False, "viewEmailLog": False},
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
