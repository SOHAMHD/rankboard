"""Drop the retired location columns and the `locations` table.

    python -m scripts.drop_location_columns            # dry run
    python -m scripts.drop_location_columns --commit

Run this only once the code that stopped reading them is deployed everywhere.
Nothing breaks if you never run it — five unused integer columns and one unread
table are cheap, and keeping them means a rollback to the previous release still
works.

This is a separate script rather than part of the boot schema on purpose. The boot
script runs on every start against whichever database the process points at, and
one Supabase instance serves both development and production here: a local
`uvicorn --reload` applying a DROP COLUMN took production down once already.
"""

import sys

from app.db import get_connection

COLUMNS = ["location_code", "country_code", "region_code", "city_code", "location_label"]


def main() -> int:
    commit = "--commit" in sys.argv
    conn = get_connection()
    try:
        present = {
            r["column_name"]
            for r in conn.execute(
                "SELECT column_name FROM information_schema.columns"
                " WHERE table_name = 'projects'"
            ).fetchall()
        }
        doomed = [c for c in COLUMNS if c in present]

        has_table = conn.execute(
            "SELECT 1 AS ok FROM information_schema.tables WHERE table_name = 'locations'"
        ).fetchone() is not None

        if not doomed and not has_table:
            print("Already clean — nothing to drop.")
            return 0

        # Guard against running this while code that still reads the columns is
        # live. A cheap check, but it catches the ordering mistake that matters.
        print("Before you commit, confirm every deployed copy of the app is on a")
        print("release where row_to_project no longer reads these columns.\n")

        for c in doomed:
            print(f"  projects.{c}")
        if has_table:
            (n,) = conn.execute("SELECT COUNT(*) AS n FROM locations").fetchone()
            print(f"  table locations ({n:,} rows)")

        if not commit:
            print("\nDry run — re-run with --commit to apply.")
            return 0

        for c in doomed:
            conn.execute(f"ALTER TABLE projects DROP COLUMN IF EXISTS {c}")
            print(f"dropped projects.{c}")
        if has_table:
            conn.execute("DROP TABLE IF EXISTS locations")
            print("dropped table locations")
        print("\nDone. This is not reversible without a restore.")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
