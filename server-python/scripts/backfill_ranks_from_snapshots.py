"""Backfill the monthly keyword-rank grid from historical snapshots.

Background
----------
Ranks have lived in three different places in this app:

  1. keywords.current_rank / previous_rank
        Written when you add a keyword with a rank, or PATCH one via
        /projects/{id}/keywords/{kid}. A single "latest" value per keyword —
        no month attached, overwritten every time.

  2. snapshot_ranks  (via POST /projects/{id}/snapshots)
        create_snapshot() copies every keyword's current_rank into
        snapshot_ranks and tags the parent snapshot row with a period_key
        ("YYYY-MM"). This is where month-by-month history actually ended up.

  3. keyword_ranks   (the Keywords grid, keyword_rank_service.py)
        (keyword_id, month, rank). THIS is what report_service.py reads when
        it builds a report — it pulls period, period-1 and period-2 from here.

Data entered through path 1 + 2 never reaches path 3, so reports come out
blank even though the numbers are in the database. This script copies
snapshot history into keyword_ranks so it shows up in the grid and in every
future report.

Safe to re-run: existing keyword_ranks cells are never overwritten unless you
pass --overwrite.

Usage
-----
    cd server-python
    python -m scripts.backfill_ranks_from_snapshots               # dry run
    python -m scripts.backfill_ranks_from_snapshots --commit
    python -m scripts.backfill_ranks_from_snapshots --commit --project 3
    python -m scripts.backfill_ranks_from_snapshots --commit --overwrite
"""

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import db  # noqa: E402

MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def fetch_snapshot_ranks(conn, project_id: int | None):
    """Every usable (project, month, keyword, rank) row held in snapshots.

    Ordered oldest snapshot first so that when two snapshots cover the same
    month, the newer one wins (it overwrites the earlier entry in the dict).
    """
    sql = (
        "SELECT s.project_id, s.period_key, s.id AS snapshot_id, s.captured_at,"
        "       sr.keyword_id, sr.term, sr.rank"
        "  FROM snapshot_ranks sr"
        "  JOIN snapshots s ON s.id = sr.snapshot_id"
        " WHERE sr.rank IS NOT NULL"
        "   AND sr.keyword_id IS NOT NULL"
    )
    params: list = []
    if project_id is not None:
        sql += " AND s.project_id = ?"
        params.append(project_id)
    sql += " ORDER BY s.period_key, s.captured_at, s.id"
    return conn.execute(sql, tuple(params)).fetchall()


def fetch_existing_cells(conn, project_id: int | None) -> set:
    sql = (
        "SELECT r.keyword_id, r.month FROM keyword_ranks r"
        "  JOIN keywords k ON k.id = r.keyword_id"
    )
    params: list = []
    if project_id is not None:
        sql += " WHERE k.project_id = ?"
        params.append(project_id)
    rows = conn.execute(sql, tuple(params)).fetchall()
    return {(r["keyword_id"], r["month"]) for r in rows}


def fetch_live_keyword_ids(conn) -> set:
    rows = conn.execute("SELECT id FROM keywords").fetchall()
    return {r["id"] for r in rows}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--commit", action="store_true", help="Actually write. Without this, nothing is changed.")
    ap.add_argument("--project", type=int, default=None, help="Limit to one project id")
    ap.add_argument("--overwrite", action="store_true", help="Replace grid cells that already have a value")
    args = ap.parse_args()

    conn = db.get_connection()
    try:
        rows = fetch_snapshot_ranks(conn, args.project)
        if not rows:
            print("No snapshot ranks found — nothing to backfill.")
            return

        existing = fetch_existing_cells(conn, args.project)
        live_kw = fetch_live_keyword_ids(conn)

        # (keyword_id, month) -> rank. Later snapshots overwrite earlier ones.
        planned: dict[tuple[int, str], int] = {}
        per_project = defaultdict(set)
        skipped_month, skipped_dead = 0, 0

        for r in rows:
            month = (r["period_key"] or "").strip()
            if not MONTH_RE.match(month):
                skipped_month += 1
                continue
            if r["keyword_id"] not in live_kw:
                skipped_dead += 1
                continue
            planned[(r["keyword_id"], month)] = r["rank"]
            per_project[r["project_id"]].add(month)

        to_insert = {k: v for k, v in planned.items() if k not in existing}
        to_update = {k: v for k, v in planned.items() if k in existing} if args.overwrite else {}
        already = len(planned) - len(to_insert)

        print(f"Snapshot rank rows read : {len(rows):,}")
        if skipped_month:
            print(f"  skipped (bad period_key) : {skipped_month:,}")
        if skipped_dead:
            print(f"  skipped (keyword deleted): {skipped_dead:,}")
        print(f"Distinct cells in snapshots: {len(planned):,}")
        print(f"  new cells to insert      : {len(to_insert):,}")
        print(f"  already in the grid      : {already:,}"
              + (f" (will overwrite {len(to_update):,})" if args.overwrite else " (left alone)"))
        print()
        for pid in sorted(per_project):
            months = sorted(per_project[pid])
            print(f"  project {pid}: {len(months)} month(s) — {', '.join(months)}")

        if not args.commit:
            print("\nDry run — nothing written. Re-run with --commit to apply.")
            return

        written = 0
        for (kw_id, month), rank in to_insert.items():
            conn.execute(
                "INSERT INTO keyword_ranks (keyword_id, month, rank) VALUES (?, ?, ?)"
                " ON CONFLICT (keyword_id, month) DO NOTHING",
                (kw_id, month, rank),
            )
            written += 1
        for (kw_id, month), rank in to_update.items():
            conn.execute(
                "UPDATE keyword_ranks SET rank = ? WHERE keyword_id = ? AND month = ?",
                (rank, kw_id, month),
            )

        print(f"\nInserted {written:,} cells" + (f", overwrote {len(to_update):,}." if to_update else "."))
        print("Open the Keywords tab (widen the window to 6 or 12 months) to confirm.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
