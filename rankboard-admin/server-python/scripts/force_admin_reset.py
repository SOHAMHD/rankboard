"""ONE-OFF: force an existing ACTIVE admin to reset their password on next
login. This is a single-row UPDATE (must_change_password = 1) — it does NOT
reset the database, touch any other row, or change the password itself.

Why: the older seed created the first Super Admin as active with
must_change_password = 0. This flips that one account so the next login is
forced through the set-password screen (then you set a real password before
deploying).

Usage (from server-python/, with the venv active):
    python scripts/force_admin_reset.py                      # the seeded Super Admin
    python scripts/force_admin_reset.py someone@example.com  # a specific admin

Safe to re-run: if the account is already flagged it reports "no change".
Exit code 0 on success / already-done, 1 if it refused to act.
"""
import sqlite3
import sys
from pathlib import Path

# Same database file app/db.py uses (scripts/ -> server-python/rankboard.db).
DB_PATH = Path(__file__).resolve().parent.parent / "rankboard.db"

DEFAULT_EMAIL = "soham@infyappdevelopment.com"
# Only ever flip an admin account — never a Client/Team row.
ADMIN_ROLES = {"Super Admin", "Admin"}


def main() -> int:
    email = (sys.argv[1] if len(sys.argv) > 1 else DEFAULT_EMAIL).strip().lower()

    if not DB_PATH.exists():
        print(f"Database not found at {DB_PATH} — nothing to do.")
        return 1

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
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
        conn.commit()
        print(f"Done: {email} will be forced to set a new password on next login.")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
