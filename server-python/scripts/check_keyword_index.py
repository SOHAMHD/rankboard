"""Report whether the keywords unique index exists, and why if it doesn't.

    python -m scripts.check_keyword_index

idx_keywords_project_term is optional DDL: a database that already holds two
keywords with the same term in the same project rejects it, and the app logs a
warning and boots anyway. Read-only — this script changes nothing.
"""

import sys

from app.db import db_session


def main() -> int:
    with db_session() as db:
        index = db.execute(
            "SELECT indexname FROM pg_indexes"
            " WHERE tablename = 'keywords' AND indexname = 'idx_keywords_project_term'"
        ).fetchone()

        dups = db.execute(
            "SELECT project_id, term, COUNT(*) AS n FROM keywords"
            " GROUP BY project_id, term HAVING COUNT(*) > 1"
            " ORDER BY n DESC, term LIMIT 25"
        ).fetchall()

        total = db.execute("SELECT COUNT(*) AS n FROM keywords").fetchone()["n"]

    print(f"keywords rows: {total}")
    print(f"idx_keywords_project_term: {'present' if index else 'MISSING'}")

    if dups:
        print(f"\nduplicate (project_id, term) groups: {len(dups)} (showing up to 25)")
        for r in dups:
            print(f"  project {r['project_id']}: {r['term']!r} x{r['n']}")
        print("\nMerge them, then restart so the index can be created:")
        print("  python -m scripts.dedupe_keywords            # dry run")
        print("  python -m scripts.dedupe_keywords --commit")
        return 1

    if not index:
        print(
            "\nNo duplicates, but the index is missing — it should be created on the"
            "\nnext restart. If it isn't, check the startup log for a line beginning"
            "\n'Optional DDL skipped'."
        )
        return 1

    print("\nNothing to do.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
