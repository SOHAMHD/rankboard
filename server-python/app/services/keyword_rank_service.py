"""The monthly keyword-rank grid — the single source of truth for ranks.

Ranks used to live in three places (keywords.current_rank, snapshot_ranks, and
this table). The other two never reached a report, so they were removed; see
scripts/backfill_ranks_from_snapshots.py if historical snapshot data still needs
migrating into keyword_ranks.

A rank is absent, not zero, when a keyword isn't ranking. Clearing a cell
deletes its row rather than storing a sentinel, which is what lets report_pdf
distinguish "wasn't ranking, now is" from "no change".
"""

import re

from fastapi import HTTPException

_MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")

#: Positions past the first few pages carry no reporting meaning, and the column
#: is a 4-byte INTEGER. Without a ceiling, a user leaning on a digit key sent a
#: value Postgres rejected with NumericValueOutOfRange — a DataError, which is a
#: sibling of IntegrityError and so slipped past the upsert's except clause and
#: surfaced as a 500.
MAX_RANK = 1000

#: The oldest month worth accepting. Guards against a typo like "0202-05"
#: silently creating a cell no UI will ever show again.
MIN_MONTH = "2000-01"

#: One project's full grid is keywords x months. The UI asks for at most 12
#: months, so this is generous; it exists so a hand-made request can't ask the
#: database to build an unbounded IN list or write an unbounded batch.
MAX_MONTHS = 24
MAX_CELLS = 5000


def _valid_month(month: str | None) -> bool:
    return bool(month and _MONTH_RE.match(month))


def _next_month(month: str) -> str:
    y, m = int(month[:4]), int(month[5:7])
    return f"{y + 1:04d}-01" if m == 12 else f"{y:04d}-{m + 1:02d}"


def latest_allowed_month(db) -> str:
    """The newest month a rank may be recorded against.

    One month past the current UTC month, deliberately. The grid builds its
    columns from the *browser's* local time (see recentMonths in Keywords.jsx),
    so from the 1st of the month until UTC catches up, a client anywhere east of
    UTC asks for a month the server hasn't reached — and since get_grid validates
    every requested month before returning anything, a strict UTC ceiling blanked
    the whole Keywords screen with a 400 for the first few hours of every month
    (05:30 on the 1st at IST, up to 14 hours further east). The tolerance costs
    nothing: MIN_MONTH still catches the typos this guard is for.
    """
    (month,) = db.execute("SELECT strftime('%Y-%m','now')").fetchone()
    return _next_month(month)


def _check_month(month: str | None, *, latest: str) -> str:
    """Validate a month's format and that it falls in a sensible window.

    `latest` comes from latest_allowed_month(), passed in rather than looked up so
    a batch of cells costs one query instead of one per cell.
    """
    if not _valid_month(month):
        raise HTTPException(400, f"Month must be in YYYY-MM format, got {month!r}.")
    if month < MIN_MONTH:
        raise HTTPException(400, f"Month {month} is before {MIN_MONTH}; check for a typo.")
    if month > latest:
        raise HTTPException(400, f"Month {month} is too far in the future — ranks can only be recorded up to {latest}.")
    return month


def _require_project(db, project_id: int) -> None:
    if db.execute("SELECT id FROM projects WHERE id = ?", (project_id,)).fetchone() is None:
        raise HTTPException(404, "Project not found.")


def _normalise_rank(value):
    """A rank as stored, or None for "not ranking". No upper bound applied."""
    if value is None or value == "":
        return None
    try:
        n = int(value)
    except (TypeError, ValueError):
        raise HTTPException(400, f"Rank must be a whole number, got {value!r}.")
    return n if n > 0 else None


def _clean_rank(value):
    """Normalise a rank the user is submitting, rejecting absurd values."""
    n = _normalise_rank(value)
    if n is not None and n > MAX_RANK:
        raise HTTPException(400, f"Rank must be {MAX_RANK} or lower, got {n}.")
    return n


def clean_months(raw: str | None) -> list[str]:
    """Parse and bound the ?months= query string, preserving order."""
    seen = set()
    wanted = []
    for part in (raw or "").split(","):
        month = part.strip()
        if not month or month in seen:
            continue
        seen.add(month)
        wanted.append(month)
    if not wanted:
        raise HTTPException(400, "Pass ?months=YYYY-MM,YYYY-MM,... — at least one month.")
    if len(wanted) > MAX_MONTHS:
        raise HTTPException(400, f"Too many months requested ({len(wanted)}); the maximum is {MAX_MONTHS}.")
    return wanted


def get_grid(db, project_id: int, months: list[str]) -> dict:
    _require_project(db, project_id)
    latest = latest_allowed_month(db)
    for m in months:
        _check_month(m, latest=latest)

    kws = db.execute(
        "SELECT id, term FROM keywords WHERE project_id = ? ORDER BY created_at, id",
        (project_id,),
    ).fetchall()

    # The month filter used to be applied in Python after fetching the project's
    # entire rank history. Pushing it into SQL keeps the payload proportional to
    # what was asked for and lets idx_keyword_ranks_month do some work.
    placeholders = ", ".join("?" for _ in months) or "NULL"
    rows = db.execute(
        "SELECT r.keyword_id, r.month, r.rank FROM keyword_ranks r"
        " JOIN keywords k ON k.id = r.keyword_id"
        f" WHERE k.project_id = ? AND r.month IN ({placeholders})",
        (project_id, *months),
    ).fetchall()

    by_kw: dict[int, dict] = {}
    for r in rows:
        by_kw.setdefault(r["keyword_id"], {})[r["month"]] = r["rank"]

    return {
        "months": months,
        "keywords": [
            {"id": k["id"], "term": k["term"], "ranks": by_kw.get(k["id"], {})}
            for k in kws
        ],
    }


def _current_values(db, pairs: list[tuple[int, str]]) -> dict[tuple[int, str], int]:
    """The stored rank for each (keyword_id, month) the caller is about to write."""
    if not pairs:
        return {}
    kw_ids = sorted({kw_id for kw_id, _ in pairs})
    months = sorted({month for _, month in pairs})
    kw_ph = ", ".join("?" for _ in kw_ids)
    m_ph = ", ".join("?" for _ in months)
    rows = db.execute(
        "SELECT keyword_id, month, rank FROM keyword_ranks"
        f" WHERE keyword_id IN ({kw_ph}) AND month IN ({m_ph})",
        (*kw_ids, *months),
    ).fetchall()
    return {(r["keyword_id"], r["month"]): r["rank"] for r in rows}


def save_cells(db, project_id: int, cells: list[dict]) -> dict:
    """Write a batch of grid cells atomically.

    Every cell is validated before anything is written. The previous version
    validated inside the write loop, and because connections run with
    autocommit=True that meant a bad cell halfway through a batch left the
    earlier cells committed while the caller was told the save had failed.
    """
    _require_project(db, project_id)

    cells = cells or []
    if len(cells) > MAX_CELLS:
        raise HTTPException(400, f"Too many cells in one save ({len(cells)}); the maximum is {MAX_CELLS}.")

    owned = {
        r["id"]
        for r in db.execute("SELECT id FROM keywords WHERE project_id = ?", (project_id,)).fetchall()
    }
    latest = latest_allowed_month(db)

    # ── Validate the whole batch ──────────────────────────────────────
    upserts: list[tuple[int, str, int]] = []
    deletes: list[tuple[int, str]] = []
    expectations: dict[tuple[int, str], object] = {}
    seen: set[tuple[int, str]] = set()

    for cell in cells:
        kw_id = cell.get("keywordId")
        month = cell.get("month")
        if kw_id not in owned:
            raise HTTPException(400, f"Keyword {kw_id!r} doesn't belong to this project.")
        _check_month(month, latest=latest)

        key = (kw_id, month)
        if key in seen:
            raise HTTPException(400, f"Cell for keyword {kw_id} / {month} was submitted twice.")
        seen.add(key)

        # `expected` is the value the client had on screen. Sending it turns a
        # blind overwrite into an optimistic check, so two people editing the
        # same month can't silently clobber each other. Omitting it keeps the
        # old last-write-wins behaviour.
        #
        # Normalised WITHOUT the MAX_RANK ceiling: this isn't something the user
        # typed, it's what the grid read back from the database. Rows written
        # before that ceiling existed can hold a larger number, and rejecting
        # them here made those cells permanently unsavable — with an error
        # blaming the user for a value they never entered.
        if "expected" in cell:
            expectations[key] = _normalise_rank(cell.get("expected"))

        rank = _clean_rank(cell.get("rank"))
        if rank is None:
            deletes.append(key)
        else:
            upserts.append((kw_id, month, rank))

    # ── Optimistic concurrency check ──────────────────────────────────
    if expectations:
        stored = _current_values(db, list(expectations.keys()))
        conflicts = [
            {"keywordId": kw_id, "month": month,
             "expected": expected, "actual": stored.get((kw_id, month))}
            for (kw_id, month), expected in expectations.items()
            if stored.get((kw_id, month)) != expected
        ]
        if conflicts:
            terms = {
                r["id"]: r["term"]
                for r in db.execute(
                    "SELECT id, term FROM keywords WHERE project_id = ?", (project_id,)
                ).fetchall()
            }
            names = sorted({terms.get(c["keywordId"], str(c["keywordId"])) for c in conflicts})
            shown = ", ".join(f"“{n}”" for n in names[:3])
            more = f" and {len(names) - 3} more" if len(names) > 3 else ""
            raise HTTPException(
                409,
                f"Someone else changed {shown}{more} while you were editing. "
                "Reload to see the current numbers, then re-enter your changes.",
            )

    # ── Write ─────────────────────────────────────────────────────────
    cleared = 0
    with db.transaction():
        if deletes:
            cur = db.executemany(
                "DELETE FROM keyword_ranks WHERE keyword_id = ? AND month = ?",
                deletes,
            )
            cleared = cur.rowcount or 0
        if upserts:
            # One statement per cell instead of the previous UPDATE, check
            # rowcount, INSERT, catch-integrity-error, UPDATE-again dance — and
            # unlike that version this one actually maintains updated_at.
            db.executemany(
                "INSERT INTO keyword_ranks (keyword_id, month, rank) VALUES (?, ?, ?)"
                " ON CONFLICT (keyword_id, month) DO UPDATE"
                " SET rank = EXCLUDED.rank, updated_at = datetime('now')",
                upserts,
            )

    return {"saved": len(upserts), "cleared": cleared}


def ambiguous_terms(db, project_id: int) -> set[str]:
    """Terms held by more than one keyword in this project.

    Should always be empty once idx_keywords_project_term is in place, but a
    database that predates it can still carry duplicates, and the term-based
    fallback in reports must not guess between them.
    """
    rows = db.execute(
        "SELECT term FROM keywords WHERE project_id = ?"
        " GROUP BY term HAVING COUNT(*) > 1",
        (project_id,),
    ).fetchall()
    return {r["term"] for r in rows}


def ranks_for_month(db, project_id: int, month: str, ambiguous: set[str] | None = None) -> dict:
    """Ranks for one month, keyed both by keyword id and by term.

    The term map is a fallback for reports: a keyword deleted and re-added under
    the same name keeps its history. Terms held by more than one keyword are left
    out of it — with two keywords called "yoga", one of which has no rank of its
    own, the fallback would otherwise hand it the other one's number and report
    it as its own. Pass `ambiguous` from ambiguous_terms() to share one lookup
    across several months.
    """
    if ambiguous is None:
        ambiguous = ambiguous_terms(db, project_id)

    rows = db.execute(
        "SELECT r.keyword_id, k.term, r.rank FROM keyword_ranks r"
        " JOIN keywords k ON k.id = r.keyword_id"
        " WHERE k.project_id = ? AND r.month = ?",
        (project_id, month),
    ).fetchall()

    by_kw = {r["keyword_id"]: r["rank"] for r in rows}
    by_term = {r["term"]: r["rank"] for r in rows if r["term"] not in ambiguous}

    return {"by_keyword_id": by_kw, "by_term": by_term, "count": len(rows)}
