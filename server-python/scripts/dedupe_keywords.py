"""Merge duplicate keyword terms within each project.

Why
---
`keywords` had no uniqueness on (project_id, term). Bulk import de-duplicated in
Python, but the single-add endpoint did not, so a project could end up with two
rows for the same term — most often from one line pasted twice, or from "Yoga"
and "yoga", which the API lowercases into the same term.

Duplicates are worse than an untidy list. report_service falls back to a
term-keyed map when a keyword has no rank of its own:

    if kw_id in maps["by_keyword_id"]:
        return maps["by_keyword_id"][kw_id]
    return maps["by_term"].get(term)          # ← the fallback

With two keywords called "yoga", one of which has never been given a rank, that
fallback handed it the other one's number and the report presented it as its own.

What this does
--------------
For every (project_id, term) holding more than one keyword:

  * keeps the OLDEST row (lowest created_at, then lowest id) as the survivor;
  * moves each duplicate's monthly ranks onto the survivor for any month the
    survivor has no value for — so no recorded rank is lost;
  * where both hold a rank for the same month, keeps the survivor's and reports
    the discarded one;
  * deletes the duplicate rows (their remaining keyword_ranks go with them via
    ON DELETE CASCADE).

Reports already generated are unaffected: they read their own frozen copy in
report_version.data_json.

Once this has run cleanly, the unique index in db.py's _OPTIONAL_DDL applies on
the next app start and the whole class of problem is gone.

Usage
-----
    cd server-python
    python -m scripts.dedupe_keywords                    # dry run, changes nothing
    python -m scripts.dedupe_keywords --commit
    python -m scripts.dedupe_keywords --commit --project 3
"""

import argparse
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import db  # noqa: E402


def fetch_duplicate_groups(conn, project_id: int | None) -> dict:
    """{(project_id, term): [keyword rows, oldest first]} for terms held twice or more."""
    sql = (
        "SELECT id, project_id, term, created_at FROM keywords"
        " WHERE (project_id, term) IN ("
        "   SELECT project_id, term FROM keywords"
        "   GROUP BY project_id, term HAVING COUNT(*) > 1"
        " )"
    )
    params: list = []
    if project_id is not None:
        sql += " AND project_id = ?"
        params.append(project_id)
    sql += " ORDER BY project_id, term, created_at, id"

    groups: dict = defaultdict(list)
    for r in conn.execute(sql, tuple(params)).fetchall():
        groups[(r["project_id"], r["term"])].append(r)
    return groups


def fetch_ranks(conn, keyword_ids: list) -> dict:
    """{keyword_id: {month: rank}} for the keywords involved."""
    if not keyword_ids:
        return {}
    placeholders = ", ".join("?" for _ in keyword_ids)
    rows = conn.execute(
        f"SELECT keyword_id, month, rank FROM keyword_ranks WHERE keyword_id IN ({placeholders})",
        tuple(keyword_ids),
    ).fetchall()
    out: dict = defaultdict(dict)
    for r in rows:
        out[r["keyword_id"]][r["month"]] = r["rank"]
    return out


def plan(groups: dict, ranks: dict) -> tuple[list, list, list]:
    """Work out the moves, the collisions, and the rows to delete."""
    moves = []       # (survivor_id, month, rank, from_keyword_id)
    collisions = []  # (project_id, term, month, kept, discarded)
    doomed = []      # keyword ids to delete

    for (project_id, term), rows in sorted(groups.items()):
        survivor = rows[0]
        survivor_months = dict(ranks.get(survivor["id"], {}))

        for dup in rows[1:]:
            doomed.append(dup["id"])
            for month, rank in sorted(ranks.get(dup["id"], {}).items()):
                if month in survivor_months and survivor_months[month] is not None:
                    if survivor_months[month] != rank:
                        collisions.append(
                            (project_id, term, month, survivor_months[month], rank)
                        )
                    continue
                moves.append((survivor["id"], month, rank, dup["id"]))
                survivor_months[month] = rank

    return moves, collisions, doomed


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--commit", action="store_true",
                    help="Actually write. Without this, nothing is changed.")
    ap.add_argument("--project", type=int, default=None, help="Limit to one project id")
    args = ap.parse_args()

    conn = db.get_connection()
    try:
        groups = fetch_duplicate_groups(conn, args.project)
        if not groups:
            print("No duplicate keyword terms found — nothing to do.")
            print("The unique index will apply on the next app start.")
            return

        all_ids = [row["id"] for rows in groups.values() for row in rows]
        ranks = fetch_ranks(conn, all_ids)
        moves, collisions, doomed = plan(groups, ranks)

        print(f"{len(groups)} duplicated term(s) across "
              f"{len({p for p, _ in groups})} project(s):\n")
        for (project_id, term), rows in sorted(groups.items()):
            survivor = rows[0]
            dups = rows[1:]
            print(f"  project {project_id}  “{term}”")
            print(f"    keep    id={survivor['id']} (created {survivor['created_at']}), "
                  f"{len(ranks.get(survivor['id'], {}))} month(s) recorded")
            for d in dups:
                print(f"    remove  id={d['id']} (created {d['created_at']}), "
                      f"{len(ranks.get(d['id'], {}))} month(s) recorded")

        if moves:
            print(f"\n{len(moves)} rank(s) will move to the surviving keyword:")
            for survivor_id, month, rank, from_id in moves:
                print(f"    {month}  #{rank}   keyword {from_id} → {survivor_id}")

        if collisions:
            print(f"\n{len(collisions)} month(s) hold different ranks on both rows. "
                  "The surviving keyword's value is kept:")
            for project_id, term, month, kept, discarded in collisions:
                print(f"    project {project_id}  “{term}”  {month}: "
                      f"keeping #{kept}, discarding #{discarded}")

        print(f"\n{len(doomed)} keyword row(s) will be deleted.")

        if not args.commit:
            print("\nDry run — nothing was changed. Re-run with --commit to apply.")
            return

        with conn.transaction():
            for survivor_id, month, rank, _from_id in moves:
                conn.execute(
                    "INSERT INTO keyword_ranks (keyword_id, month, rank) VALUES (?, ?, ?)"
                    " ON CONFLICT (keyword_id, month) DO UPDATE"
                    " SET rank = EXCLUDED.rank, updated_at = datetime('now')",
                    (survivor_id, month, rank),
                )
            placeholders = ", ".join("?" for _ in doomed)
            conn.execute(
                f"DELETE FROM keywords WHERE id IN ({placeholders})", tuple(doomed)
            )

        print(f"\nDone: moved {len(moves)} rank(s), deleted {len(doomed)} keyword row(s).")
        print("Restart the app to let the unique index apply.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
