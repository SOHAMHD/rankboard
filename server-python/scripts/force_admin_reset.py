import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import get_connection  # noqa: E402  (path set up above)

DEFAULT_EMAIL = "soham@infyappdevelopment.com"
ADMIN_ROLES = {"Super Admin", "Admin"}


def main() -> int:
    email = (sys.argv[1] if len(sys.argv) > 1 else DEFAULT_EMAIL).strip().lower()

    conn = get_connection()
    try:
        user = conn.execute(
            "SELECT id, email, role, status, must_change_password FROM users WHERE email = ?",
            (email,),
        ).fetchone()

        if user is None:
            print(f"No user with email {email!r}. No change made.")
            return 1
        if user["role"] not in ADMIN_ROLES:
            print(f"{email} is {user['role']!r}, not an admin. Refusing to change. No change made.")
            return 1
        if user["status"] != "active":
            print(f"{email} is not active (status={user['status']!r}). No change made.")
            return 1
        if user["must_change_password"]:
            print(f"{email} is already flagged to reset on next login. No change needed.")
            return 0

        conn.execute("UPDATE users SET must_change_password = 1 WHERE id = ?", (user["id"],))
        print(f"Done: {email} will be forced to set a new password on next login.")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
