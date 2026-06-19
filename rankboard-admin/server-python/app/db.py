"""DATABASE LAYER — SQLite via Python's standard library (sqlite3).

Same single-file database idea as the Node server (zero extra
dependencies), same schema, same seeds. One Python-specific pattern
worth learning: get_db() below is a FastAPI *dependency* that opens a
fresh connection per request and always closes it — Python's
equivalent of Express middleware that prepares something for the
handler.
"""
import sqlite3
import secrets
from pathlib import Path

import bcrypt

# Readable one-time seed password: cryptographically random (secrets, not
# random) and skips lookalike characters (0/O, 1/l/I).
_SEED_PW_CHARS = "ABCDEFGHJKMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz23456789"

DB_PATH = Path(__file__).resolve().parent.parent / "rankboard.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id                   INTEGER PRIMARY KEY AUTOINCREMENT,
  name                 TEXT NOT NULL,
  email                TEXT NOT NULL UNIQUE,
  role                 TEXT NOT NULL CHECK (role IN ('Super Admin','Admin','Team','Client')),
  password_hash        TEXT NOT NULL,
  must_change_password INTEGER NOT NULL DEFAULT 0,
  status               TEXT NOT NULL DEFAULT 'invited' CHECK (status IN ('invited','active')),
  created_at           TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS emails (
  id       INTEGER PRIMARY KEY AUTOINCREMENT,
  to_email TEXT NOT NULL,
  subject  TEXT NOT NULL,
  body     TEXT NOT NULL,
  sent_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS projects (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  name            TEXT NOT NULL,
  domain          TEXT,
  location_code   INTEGER,
  ga_property_id  TEXT,
  gsc_site_url    TEXT,
  active          INTEGER NOT NULL DEFAULT 1,
  created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS keywords (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id    INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  term          TEXT NOT NULL,
  current_rank  INTEGER  CHECK (current_rank >= 1),
  previous_rank INTEGER CHECK (previous_rank >= 1),
  last_checked  TEXT NOT NULL DEFAULT (date('now')),
  created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

-- A snapshot is a frozen, point-in-time copy of every keyword's rank
-- for a project, saved per month. UNIQUE(project_id, period_key) means
-- one snapshot per month per project (re-saving an unlocked month
-- refreshes it in place). The companion snapshot_ranks rows COPY each
-- keyword's term/rank in rather than referencing keywords live, so the
-- frozen values survive later edits or deletions of the keyword.
CREATE TABLE IF NOT EXISTS snapshots (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id  INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  period_key  TEXT NOT NULL,                       -- e.g. "2026-06"
  label       TEXT NOT NULL,                        -- e.g. "June 2026"
  captured_at TEXT NOT NULL DEFAULT (date('now')),
  source      TEXT NOT NULL DEFAULT 'manual',
  locked      INTEGER NOT NULL DEFAULT 0,
  UNIQUE(project_id, period_key)
);

CREATE TABLE IF NOT EXISTS snapshot_ranks (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  snapshot_id  INTEGER NOT NULL REFERENCES snapshots(id) ON DELETE CASCADE,
  keyword_id   INTEGER REFERENCES keywords(id) ON DELETE SET NULL,  -- nullable: term is copied below
  term         TEXT NOT NULL,                        -- copied in, not just referenced
  rank         INTEGER,                              -- nullable (never-checked keywords)
  last_checked TEXT                                  -- copied from the keyword
);

-- Moz domain Authority metrics, one row per refresh (history is kept; the
-- newest row by fetched_at is the one shown). Every metric is nullable because
-- Moz may omit any field, and raw_json keeps the full responses for debugging.
CREATE TABLE IF NOT EXISTS moz_metrics (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id       INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  domain           TEXT NOT NULL,                     -- the normalized root domain queried
  domain_authority INTEGER,
  linking_domains  INTEGER,
  inbound_links    INTEGER,
  ranking_keywords INTEGER,
  spam_score       REAL,
  raw_json         TEXT,                              -- full Moz responses, for debugging
  fetched_at       TEXT NOT NULL                      -- ISO timestamp
);
"""


def get_db():
    """One connection per request, in AUTOCOMMIT mode; always closed.

    Two hard-won details live in this function:

    1. isolation_level=None (autocommit). Without it, Python's sqlite3
       opens an implicit transaction and our commit ran in dependency
       teardown — which executes AFTER the response is sent. A client
       reacting instantly to "ok: true" could read the OLD data: a
       race we actually hit in testing. Autocommit makes every
       statement durable BEFORE the handler returns, matching how the
       Node driver behaves. Rule: never tell the client "done" before
       the database agrees.

    2. PRAGMA foreign_keys is PER-CONNECTION in SQLite, so it must be
       switched on for every new connection or ON DELETE CASCADE
       silently does nothing.
    """
    # check_same_thread=False: FastAPI may run async endpoints on a
    # different thread than the one that opened the connection. SQLite
    # forbids cross-thread use by default; this lifts that. Safe here
    # because each request gets its OWN connection (no sharing), so
    # there's no actual concurrent access to a single connection.
    conn = sqlite3.connect(DB_PATH, isolation_level=None, check_same_thread=False)  # autocommit
    conn.row_factory = sqlite3.Row  # rows behave like dicts: row["email"]
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()


def init_db() -> None:
    """Create schema + seed data on first boot (same seeds as Node)."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.executescript(SCHEMA)

    # Poor-man's migration: CREATE TABLE IF NOT EXISTS doesn't touch
    # existing tables, so databases created before the `domain` column
    # existed need an ALTER. Real apps use a migration tool (Alembic
    # for Python, Prisma/Knex for Node) — this is the idea in miniature.
    try:
        conn.execute("ALTER TABLE projects ADD COLUMN domain TEXT")
    except sqlite3.OperationalError:
        pass  # column already exists

    # Per-project DataForSEO location code (falls back to RANK_LOCATION_CODE
    # in config when NULL). Same poor-man's migration as `domain` above.
    try:
        conn.execute("ALTER TABLE projects ADD COLUMN location_code INTEGER")
    except sqlite3.OperationalError:
        pass  # column already exists

    # Per-project GA4 property ID (NULL until set; the GA4 traffic panel
    # is disabled for the project while it's empty). Same poor-man's
    # migration as `domain` / `location_code` above.
    try:
        conn.execute("ALTER TABLE projects ADD COLUMN ga_property_id TEXT")
    except sqlite3.OperationalError:
        pass  # column already exists

    # Per-project Google Search Console site URL (NULL until set; the Search
    # Console panel is disabled for the project while it's empty). A URL-prefix
    # property like "https://www.example.com/" or a domain property like
    # "sc-domain:example.com". Same poor-man's migration as `ga_property_id`.
    try:
        conn.execute("ALTER TABLE projects ADD COLUMN gsc_site_url TEXT")
    except sqlite3.OperationalError:
        pass  # column already exists

    # One-time migration: older databases created current_rank as NOT
    # NULL. SQLite can't drop a column constraint in place, so rebuild
    # the keywords table — but only if the constraint is still present
    # (idempotent: skips itself once migrated, never fires on a fresh DB).
    cols = conn.execute("PRAGMA table_info(keywords)").fetchall()
    current_rank_required = any(c[1] == "current_rank" and c[3] == 1 for c in cols)
    if current_rank_required:
        conn.executescript(
            """
            CREATE TABLE keywords_rebuild (
              id            INTEGER PRIMARY KEY AUTOINCREMENT,
              project_id    INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
              term          TEXT NOT NULL,
              current_rank  INTEGER CHECK (current_rank >= 1),
              previous_rank INTEGER CHECK (previous_rank >= 1),
              last_checked  TEXT NOT NULL DEFAULT (date('now')),
              created_at    TEXT NOT NULL DEFAULT (datetime('now'))
            );
            INSERT INTO keywords_rebuild
              SELECT id, project_id, term, current_rank, previous_rank, last_checked, created_at FROM keywords;
            DROP TABLE keywords;
            ALTER TABLE keywords_rebuild RENAME TO keywords;
            """
        )
        print("Migrated keywords table: current_rank is now optional")

    (count,) = conn.execute("SELECT COUNT(*) FROM users").fetchone()
    if count == 0:
        # Fixed, known seed credential so the Super Admin can always sign in on
        # a fresh database — essential on hosts (e.g. Render) that reset the DB
        # on every deploy. The password is a known value by design; it is still
        # bcrypt-hashed, never stored in plain text. Created active with no
        # forced change so `admin123` logs straight in after each redeploy.
        temp_password = "admin123"
        pw_hash = bcrypt.hashpw(temp_password.encode(), bcrypt.gensalt()).decode()
        conn.execute(
            "INSERT INTO users (name, email, role, password_hash, must_change_password, status)"
            " VALUES (?, ?, ?, ?, 0, 'active')",
            ("Soham Dhokiya", "soham@infyappdevelopment.com", "Super Admin", pw_hash),
        )
        print("=" * 64)
        print("Seeded first Super Admin:")
        print("  email:    soham@infyappdevelopment.com")
        print(f"  password: {temp_password}")
        print("  ^ stored as a bcrypt hash, not in plain text.")
        print("=" * 64)

    (pcount,) = conn.execute("SELECT COUNT(*) FROM projects").fetchone()
    if pcount == 0:
        # location_code 2356 = India for all seeded demo projects (.in / India sites).
        cur = conn.execute("INSERT INTO projects (name, domain, location_code, active) VALUES (?, ?, ?, 1)", ("Sattva Connect", "sattvaconnect.com", 2356))
        sattva = cur.lastrowid
        kws = [
            (sattva, "online yoga classes", 4, 9, "2026-06-10"),
            (sattva, "yoga teacher training online", 12, 8, "2026-06-10"),
            (sattva, "meditation app for beginners", 21, 21, "2026-06-10"),
            (sattva, "pranayama breathing course", 3, None, "2026-06-11"),
        ]
        conn.executemany(
            "INSERT INTO keywords (project_id, term, current_rank, previous_rank, last_checked)"
            " VALUES (?, ?, ?, ?, ?)",
            kws,
        )
        cur = conn.execute("INSERT INTO projects (name, domain, location_code, active) VALUES (?, ?, ?, 1)", ("Urban Bloom Florists", "urbanbloomflorists.in", 2356))
        conn.execute(
            "INSERT INTO keywords (project_id, term, current_rank, previous_rank, last_checked)"
            " VALUES (?, ?, ?, ?, ?)",
            (cur.lastrowid, "same day flower delivery mumbai", 7, 11, "2026-06-09"),
        )
        conn.execute("INSERT INTO projects (name, domain, location_code, active) VALUES (?, ?, ?, 0)", ("Peak Performance Gym", "peakperformancegym.in", 2356))
        print("Seeded demo projects + keywords")

    conn.commit()
    conn.close()
