"""DATABASE LAYER — SQLite by default, Supabase Postgres when configured.

The whole app is written ONCE in SQLite dialect with raw SQL (no ORM). To run
it on Postgres without rewriting every router, this module does two things:

  • Connection: get_db() opens a fresh per-request connection and closes it.
    With DATABASE_URL set to a Postgres URL it connects via psycopg 3; otherwise
    it falls back to the local SQLite file (so local dev needs no env var).

  • Dialect bridge: when on Postgres, a tiny facade (_PgConnection / _PgCursor /
    _Row) gives psycopg the exact sqlite3 surface the routers use — db.execute(
    sql, params).fetchone()/.fetchall()/.lastrowid/.rowcount, rows indexable by
    name AND position — and _translate() rewrites the handful of SQLite-isms in
    the SQL (date helpers, INSERT OR IGNORE, ? placeholders, lastrowid). Nothing
    in the routers/services had to change.

The SQLite path below is byte-for-byte the original behavior; it is the
documented fallback and is left intact.
"""
import os
import sqlite3
import secrets
from pathlib import Path

import bcrypt

# Loading config first runs its .env loader, so DATABASE_URL (and friends) set
# in server-python/.env are present in os.environ before we read them below.
from . import config  # noqa: F401  (imported for the .env side effect)

# Readable one-time seed password: cryptographically random (secrets, not
# random) and skips lookalike characters (0/O, 1/l/I).
_SEED_PW_CHARS = "ABCDEFGHJKMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz23456789"

DB_PATH = Path(__file__).resolve().parent.parent / "rankboard.db"


# ── Connection target: env-driven, SQLite by default ─────────────────────────
def _looks_like_postgres(url: str) -> bool:
    return url.startswith((
        "postgresql://", "postgresql+psycopg://", "postgresql+psycopg2://", "postgres://",
    ))


def _normalize_pg_url(url: str) -> str:
    """psycopg speaks plain libpq URLs (postgresql://…). Supabase hands out a
    postgresql:// URL; other tooling sometimes hands out the SQLAlchemy dialect
    form (postgresql+psycopg://) or the legacy postgres:// scheme. Normalize all
    of them to the libpq form. Idempotent: a clean postgresql:// URL is returned
    unchanged.

    NOTE: the migration brief asked to rewrite TO postgresql+psycopg://, but that
    "+psycopg" suffix is a SQLAlchemy *dialect* tag — this app talks to psycopg
    directly with no SQLAlchemy, so the bare libpq scheme is what's required.
    """
    for prefix in ("postgresql+psycopg://", "postgresql+psycopg2://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql://" + url[len(prefix):]
    return url


# Read once at import. DATABASE_URL set + looks like Postgres -> use Postgres;
# anything else (unset, or a non-PG value) -> local SQLite file.
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
IS_POSTGRES = bool(DATABASE_URL) and _looks_like_postgres(DATABASE_URL)
_PG_URL = _normalize_pg_url(DATABASE_URL) if IS_POSTGRES else None

# psycopg is imported ONLY when Postgres is selected, so the SQLite fallback
# keeps working on a machine that doesn't have psycopg installed.
psycopg = None
if IS_POSTGRES:
    import psycopg  # approved dependency for this slice

# Both SQLite and Postgres raise an IntegrityError subtype on a UNIQUE/CHECK
# violation, but the classes differ; callers catch this tuple so the same
# `except` works on either backend (psycopg.IntegrityError covers UniqueViolation).
INTEGRITY_ERRORS = (sqlite3.IntegrityError,) + ((psycopg.IntegrityError,) if IS_POSTGRES else ())


# ── Schemas ──────────────────────────────────────────────────────────────────
# SQLite schema (unchanged original). Used only on the SQLite path.
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

-- A snapshot is a frozen, point-in-time copy of every keyword's rank for
-- a project. Snapshots are NO LONGER one-per-month: every "Save this
-- month" inserts a fresh, immutable row, distinguished by created_at (a
-- full timestamp). period_key/label still group them by month for the UI.
-- The companion snapshot_ranks rows COPY each keyword's term/rank in
-- rather than referencing keywords live, so the frozen values survive
-- later edits or deletions of the keyword.
CREATE TABLE IF NOT EXISTS snapshots (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id  INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  period_key  TEXT NOT NULL,                       -- e.g. "2026-06"
  label       TEXT NOT NULL,                        -- e.g. "June 2026"
  captured_at TEXT NOT NULL DEFAULT (date('now')), -- the calendar day frozen
  created_at  TEXT NOT NULL DEFAULT (datetime('now')), -- full timestamp; distinguishes same-month saves
  source      TEXT NOT NULL DEFAULT 'manual',
  locked      INTEGER NOT NULL DEFAULT 0
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

-- Per-client project scoping: which Client users may see which projects.
-- Staff roles (Super Admin / Admin / Team) ignore this table and see all
-- projects; a Client sees only the projects they're linked to here. Both
-- FKs cascade, so removing a user or a project cleans up its links. The
-- UNIQUE(user_id, project_id) makes an assignment idempotent (re-assigning
-- the same pair is a no-op rather than a duplicate row).
CREATE TABLE IF NOT EXISTS user_projects (
  user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(user_id, project_id)
);

-- One row per GENERATED VERSION of a report. data_json is the FROZEN data blob
-- (ranks/moz/keywords + month-over-month deltas, assembled by the report
-- pipeline); content_json is the EDITABLE layer (empty here, filled by a later
-- editor slice). Versioning means MULTIPLE rows per (project_id, period_key) are
-- legal — a fresh generate has parent_version_id NULL; a "changes" fork sets it
-- to the version it copied. The "one active non-sent version" rule is enforced
-- in code (report_service.generate), NOT by a DB constraint, for now.
CREATE TABLE IF NOT EXISTS report_version (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id        INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  period_key        TEXT NOT NULL,                          -- report month, e.g. "2026-06"
  status            TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','in_review','sent')),
  parent_version_id INTEGER REFERENCES report_version(id) ON DELETE SET NULL,  -- forked-from lineage; NULL for a fresh generate
  data_json         TEXT NOT NULL,                          -- FROZEN data blob
  content_json      TEXT NOT NULL DEFAULT '{}',             -- EDITABLE content layer (empty here)
  rank_snapshot_id  INTEGER REFERENCES snapshots(id) ON DELETE SET NULL,       -- which snapshot's ranks were frozen in
  created_by        INTEGER REFERENCES users(id) ON DELETE SET NULL,
  created_at        TEXT NOT NULL DEFAULT (datetime('now')),
  frozen_at         TEXT                                    -- set when the data was frozen
);

CREATE INDEX IF NOT EXISTS idx_report_version_project_period
  ON report_version (project_id, period_key);

-- Per-project backlinks, maintained MONTH-WISE by the SEO team (they paste a
-- month's batch of URLs). `month` is "YYYY-MM" — the SAME key format snapshots/
-- reports use, so the report's backlinks section filters by it. De-dupe is done
-- in CODE per (project_id, month); the UNIQUE below backs that up so a racing
-- duplicate paste fails gracefully (caught as an integrity error) instead of
-- 500ing. The SAME url MAY repeat under a DIFFERENT month.
CREATE TABLE IF NOT EXISTS backlinks (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id  INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  url         TEXT NOT NULL,
  month       TEXT NOT NULL,                       -- "YYYY-MM"
  created_at  TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(project_id, month, url)
);

CREATE INDEX IF NOT EXISTS idx_backlinks_project_month
  ON backlinks (project_id, month);
"""

# Postgres schema — same tables/columns/constraints as SQLite, retargeted:
#   • INTEGER PRIMARY KEY AUTOINCREMENT  -> INTEGER GENERATED BY DEFAULT AS IDENTITY
#   • The booleans stay INTEGER 0/1 (projects.active, users.must_change_password,
#     snapshots.locked) exactly as on SQLite — the app reads them with bool(...)
#     and writes literal 0/1, so keeping them integer changes nothing and avoids
#     a needless rewrite of those writes.
#   • created_at/captured_at/last_checked stay TEXT, defaulted via to_char(...) in
#     the SAME string formats SQLite produced, so API responses are unchanged.
#   • The role CHECK and every other CHECK/UNIQUE/REFERENCES carry over verbatim.
# Postgres enforces foreign keys unconditionally (no PER-connection PRAGMA), and
# this is only ever run against an empty database, so the SQLite "poor-man's
# migration" rebuilds below are not needed here.
_PG_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id                   INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
  name                 TEXT NOT NULL,
  email                TEXT NOT NULL UNIQUE,
  role                 TEXT NOT NULL CHECK (role IN ('Super Admin','Admin','Team','Client')),
  password_hash        TEXT NOT NULL,
  must_change_password INTEGER NOT NULL DEFAULT 0,
  status               TEXT NOT NULL DEFAULT 'invited' CHECK (status IN ('invited','active')),
  created_at           TEXT NOT NULL DEFAULT to_char((now() AT TIME ZONE 'UTC'), 'YYYY-MM-DD HH24:MI:SS')
);

CREATE TABLE IF NOT EXISTS emails (
  id       INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
  to_email TEXT NOT NULL,
  subject  TEXT NOT NULL,
  body     TEXT NOT NULL,
  sent_at  TEXT NOT NULL DEFAULT to_char((now() AT TIME ZONE 'UTC'), 'YYYY-MM-DD HH24:MI:SS')
);

CREATE TABLE IF NOT EXISTS projects (
  id              INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
  name            TEXT NOT NULL,
  domain          TEXT,
  location_code   INTEGER,
  ga_property_id  TEXT,
  gsc_site_url    TEXT,
  active          INTEGER NOT NULL DEFAULT 1,
  created_at      TEXT NOT NULL DEFAULT to_char((now() AT TIME ZONE 'UTC'), 'YYYY-MM-DD HH24:MI:SS')
);

CREATE TABLE IF NOT EXISTS keywords (
  id            INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
  project_id    INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  term          TEXT NOT NULL,
  current_rank  INTEGER CHECK (current_rank >= 1),
  previous_rank INTEGER CHECK (previous_rank >= 1),
  last_checked  TEXT NOT NULL DEFAULT to_char((now() AT TIME ZONE 'UTC'), 'YYYY-MM-DD'),
  created_at    TEXT NOT NULL DEFAULT to_char((now() AT TIME ZONE 'UTC'), 'YYYY-MM-DD HH24:MI:SS')
);

CREATE TABLE IF NOT EXISTS snapshots (
  id          INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
  project_id  INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  period_key  TEXT NOT NULL,
  label       TEXT NOT NULL,
  captured_at TEXT NOT NULL DEFAULT to_char((now() AT TIME ZONE 'UTC'), 'YYYY-MM-DD'),
  created_at  TEXT NOT NULL DEFAULT to_char((now() AT TIME ZONE 'UTC'), 'YYYY-MM-DD HH24:MI:SS'),
  source      TEXT NOT NULL DEFAULT 'manual',
  locked      INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS snapshot_ranks (
  id           INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
  snapshot_id  INTEGER NOT NULL REFERENCES snapshots(id) ON DELETE CASCADE,
  keyword_id   INTEGER REFERENCES keywords(id) ON DELETE SET NULL,
  term         TEXT NOT NULL,
  rank         INTEGER,
  last_checked TEXT
);

CREATE TABLE IF NOT EXISTS moz_metrics (
  id               INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
  project_id       INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  domain           TEXT NOT NULL,
  domain_authority INTEGER,
  linking_domains  INTEGER,
  inbound_links    INTEGER,
  ranking_keywords INTEGER,
  spam_score       REAL,
  raw_json         TEXT,
  fetched_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS user_projects (
  user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  created_at TEXT NOT NULL DEFAULT to_char((now() AT TIME ZONE 'UTC'), 'YYYY-MM-DD HH24:MI:SS'),
  UNIQUE(user_id, project_id)
);

CREATE TABLE IF NOT EXISTS report_version (
  id                INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
  project_id        INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  period_key        TEXT NOT NULL,
  status            TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','in_review','sent')),
  parent_version_id INTEGER REFERENCES report_version(id) ON DELETE SET NULL,
  data_json         TEXT NOT NULL,
  content_json      TEXT NOT NULL DEFAULT '{}',
  rank_snapshot_id  INTEGER REFERENCES snapshots(id) ON DELETE SET NULL,
  created_by        INTEGER REFERENCES users(id) ON DELETE SET NULL,
  created_at        TEXT NOT NULL DEFAULT to_char((now() AT TIME ZONE 'UTC'), 'YYYY-MM-DD HH24:MI:SS'),
  frozen_at         TEXT
);

CREATE INDEX IF NOT EXISTS idx_report_version_project_period
  ON report_version (project_id, period_key);

CREATE TABLE IF NOT EXISTS backlinks (
  id          INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
  project_id  INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  url         TEXT NOT NULL,
  month       TEXT NOT NULL,
  created_at  TEXT NOT NULL DEFAULT to_char((now() AT TIME ZONE 'UTC'), 'YYYY-MM-DD HH24:MI:SS'),
  UNIQUE(project_id, month, url)
);

CREATE INDEX IF NOT EXISTS idx_backlinks_project_month
  ON backlinks (project_id, month);
"""


# ── Postgres dialect bridge (active only when IS_POSTGRES) ────────────────────
def _translate(sql: str) -> str:
    """Rewrite the app's SQLite-flavored SQL into the Postgres equivalent.

    This is the ONE place that bridges the dialect gaps, so the routers/services
    keep their SQLite SQL untouched:
      • date/time helpers  -> to_char(...) producing the IDENTICAL text formats
      • INSERT OR IGNORE   -> INSERT ... ON CONFLICT DO NOTHING
      • lastrowid          -> append RETURNING id (read back by _PgCursor)
      • ? placeholders     -> %s (psycopg's paramstyle)

    Order matters: the date/time rewrites run first because strftime('%Y-%m',…)
    is the only query holding a literal '%', and replacing it removes that '%'
    before the final ? -> %s pass, so nothing is mistaken for a placeholder.
    """
    s = sql
    # 1) Date/time helpers → text in the exact formats SQLite emitted, so the
    #    values the API returns (createdAt / capturedAt / lastChecked / period
    #    keys) look identical on either backend.
    s = s.replace("strftime('%Y-%m','now')", "to_char((now() AT TIME ZONE 'UTC'), 'YYYY-MM')")
    s = s.replace("datetime('now')", "to_char((now() AT TIME ZONE 'UTC'), 'YYYY-MM-DD HH24:MI:SS')")
    s = s.replace("date('now')", "to_char((now() AT TIME ZONE 'UTC'), 'YYYY-MM-DD')")

    # 2) INSERT variants.
    head = s.lstrip()[:24].upper()
    if head.startswith("INSERT OR IGNORE"):
        # The only table inserted this way (user_projects) has no `id` column
        # and its result is never read, so deliberately NO RETURNING is added.
        i = s.upper().index("INSERT OR IGNORE")
        s = s[:i] + "INSERT" + s[i + len("INSERT OR IGNORE"):]
        if "ON CONFLICT" not in s.upper():
            s = s.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"
    elif head.startswith("INSERT") and "RETURNING" not in s.upper():
        # Postgres has no cursor.lastrowid; RETURNING id surfaces the new key,
        # which _PgCursor exposes as cur.lastrowid. Every table inserted this
        # way has an `id` column.
        s = s.rstrip().rstrip(";") + " RETURNING id"

    # 3) Parameter placeholders (last — see the docstring note about '%').
    s = s.replace("?", "%s")
    return s


class _Row:
    """A Postgres row that behaves like sqlite3.Row: indexable by name AND
    position, iterates over VALUES (so `(count,) = row` unpacks the value), and
    converts via dict(row) (so `{**dict(row)}` works). This lets the routers
    keep their sqlite3.Row access patterns unchanged on Postgres."""

    __slots__ = ("_names", "_vals", "_index")

    def __init__(self, names, values):
        self._names = names
        self._vals = values
        self._index = None  # built lazily on first name lookup

    def __getitem__(self, key):
        if isinstance(key, str):
            if self._index is None:
                self._index = {n: i for i, n in enumerate(self._names)}
            return self._vals[self._index[key]]
        return self._vals[key]  # int or slice

    def __iter__(self):
        return iter(self._vals)

    def __len__(self):
        return len(self._vals)

    def keys(self):
        return list(self._names)

    def get(self, key, default=None):
        try:
            return self[key]
        except (KeyError, IndexError):
            return default


def _pg_row_factory(cursor):
    """psycopg row factory producing _Row objects. Called once per execute after
    the cursor description is known (the standard psycopg 3 pattern)."""
    cols = cursor.description
    names = [c.name for c in cols] if cols else []

    def make_row(values):
        return _Row(names, values)

    return make_row


class _PgCursor:
    """Gives a psycopg cursor the small sqlite3 surface the app relies on:
    fetchone/fetchall, rowcount, and lastrowid (filled from RETURNING id)."""

    __slots__ = ("_cur", "lastrowid")

    def __init__(self, cur, translated_sql):
        self._cur = cur
        self.lastrowid = None
        if translated_sql.lstrip()[:6].upper() == "INSERT" and "RETURNING" in translated_sql.upper():
            row = cur.fetchone()
            self.lastrowid = row[0] if row is not None else None

    @property
    def rowcount(self):
        return self._cur.rowcount

    def fetchone(self):
        return self._cur.fetchone()

    def fetchall(self):
        return self._cur.fetchall()

    def fetchmany(self, size=None):
        return self._cur.fetchmany() if size is None else self._cur.fetchmany(size)


class _PgConnection:
    """A sqlite3.Connection-compatible facade over a psycopg connection: the
    routers call db.execute(sql, params).fetch*()/.lastrowid/.rowcount exactly as
    they do on SQLite. Each execute uses a fresh cursor; SQL is bridged across
    dialects by _translate(). The connection is autocommit (see get_connection),
    so explicit BEGIN/COMMIT/ROLLBACK statements (used in one place for an atomic
    replace) pass straight through as their own transaction."""

    __slots__ = ("_conn",)

    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql, params=()):
        translated = _translate(sql)
        cur = self._conn.cursor()
        # params or None: a query with no placeholders gets None so psycopg does
        # no parameter processing (a non-empty params tuple is always truthy).
        cur.execute(translated, params or None)
        return _PgCursor(cur, translated)

    def close(self):
        self._conn.close()


# ── Connections ──────────────────────────────────────────────────────────────
def get_connection():
    """Open ONE fresh connection. The caller must close it (get_db does, in a
    finally). Postgres when DATABASE_URL points at it, else the SQLite file."""
    if IS_POSTGRES:
        # ── Tied to the Supabase Session pooler (host *.pooler.supabase.com,
        # port 5432) ────────────────────────────────────────────────────────
        # We open a fresh connection per request and close it — no app-side
        # pool — because the Session pooler does the pooling server-side and
        # free-tier connection limits are low. autocommit=True makes every
        # statement durable before the handler returns (the same reasoning as
        # the SQLite isolation_level=None below). connect_timeout keeps a
        # momentarily-unreachable pooler from hanging a request.
        #   When self-hosting Postgres later, an app-side pool with pre-ping +
        #   a small pool_size/max_overflow would belong here — that needs the
        #   separate psycopg_pool package (not installed for this slice).
        conn = psycopg.connect(
            _PG_URL,
            autocommit=True,
            row_factory=_pg_row_factory,
            connect_timeout=10,
        )
        return _PgConnection(conn)

    # ── SQLite (unchanged) ──────────────────────────────────────────────────
    # check_same_thread=False: FastAPI may run async endpoints on a different
    # thread than the one that opened the connection. Safe here because each
    # request gets its OWN connection (no sharing). isolation_level=None gives
    # autocommit; PRAGMA foreign_keys is per-connection so it's set every time.
    conn = sqlite3.connect(DB_PATH, isolation_level=None, check_same_thread=False)  # autocommit
    conn.row_factory = sqlite3.Row  # rows behave like dicts: row["email"]
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get_db():
    """One connection per request; always closed. A FastAPI dependency —
    Python's equivalent of Express middleware that prepares the DB handle.

    Autocommit is deliberate on both backends: a commit deferred to dependency
    teardown runs AFTER the response is sent, so a client reacting instantly to
    "ok: true" could read stale data — a race we actually hit. Autocommit makes
    every statement durable BEFORE the handler returns."""
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()


# ── Schema creation + first-boot seed ────────────────────────────────────────
def init_db() -> None:
    """Create the schema and seed first-boot data. Dispatches by backend; both
    seeds are idempotent (guarded by COUNT(*) == 0), so re-running is a no-op."""
    if IS_POSTGRES:
        _init_pg()
    else:
        _init_sqlite()


def _seed(conn) -> None:
    """Shared first-boot seed, written in SQLite SQL (the Postgres path runs it
    through the _translate bridge). Idempotent: each block only fires when its
    table is empty, so it's safe on every boot and on a host that resets the DB.

    NOTE: does NOT port existing SQLite rows — this is a fresh seed only.
    """
    (count,) = conn.execute("SELECT COUNT(*) FROM users").fetchone()
    if count == 0:
        # Fixed, known seed credential so the Super Admin can always sign in on
        # a fresh database — essential on hosts (e.g. Render) that reset the DB
        # on every deploy. Still bcrypt-hashed, never stored in plain text.
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
        cur = conn.execute(
            "INSERT INTO projects (name, domain, location_code, active) VALUES (?, ?, ?, 1)",
            ("Sattva Connect", "sattvaconnect.com", 2356),
        )
        sattva = cur.lastrowid
        kws = [
            (sattva, "online yoga classes", 4, 9, "2026-06-10"),
            (sattva, "yoga teacher training online", 12, 8, "2026-06-10"),
            (sattva, "meditation app for beginners", 21, 21, "2026-06-10"),
            (sattva, "pranayama breathing course", 3, None, "2026-06-11"),
        ]
        for kw in kws:
            conn.execute(
                "INSERT INTO keywords (project_id, term, current_rank, previous_rank, last_checked)"
                " VALUES (?, ?, ?, ?, ?)",
                kw,
            )
        cur = conn.execute(
            "INSERT INTO projects (name, domain, location_code, active) VALUES (?, ?, ?, 1)",
            ("Urban Bloom Florists", "urbanbloomflorists.in", 2356),
        )
        conn.execute(
            "INSERT INTO keywords (project_id, term, current_rank, previous_rank, last_checked)"
            " VALUES (?, ?, ?, ?, ?)",
            (cur.lastrowid, "same day flower delivery mumbai", 7, 11, "2026-06-09"),
        )
        conn.execute(
            "INSERT INTO projects (name, domain, location_code, active) VALUES (?, ?, ?, 0)",
            ("Peak Performance Gym", "peakperformancegym.in", 2356),
        )
        print("Seeded demo projects + keywords")


def _init_pg() -> None:
    """Postgres: create the schema additively (CREATE TABLE IF NOT EXISTS) and
    seed. No destructive SQL; runs against the empty Supabase database on first
    boot. The seed reuses _seed() via the dialect bridge."""
    conn = get_connection()
    try:
        # Run each CREATE TABLE separately on the raw psycopg connection
        # (psycopg's extended protocol executes one statement per call). The DDL
        # has no '?'/INSERTs and no embedded semicolons, so splitting on ';' is
        # safe and bypasses the _translate bridge it doesn't need.
        raw = conn._conn  # the underlying psycopg connection
        for statement in _PG_SCHEMA.split(";"):
            statement = statement.strip()
            if statement:
                raw.execute(statement)
        _seed(conn)
    finally:
        conn.close()


def _init_sqlite() -> None:
    """Create schema + seed data on first boot (original SQLite path, unchanged
    — including the poor-man's migrations that evolve older local databases)."""
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

    # One-time migration: the one-snapshot-per-month limit was a DB-level
    # UNIQUE(project_id, period_key) constraint, and older snapshots tables
    # lack the full-timestamp created_at column. SQLite can't drop a
    # constraint or add a non-constant default in place, so rebuild the table
    # — preserving every row and id. Fires only when the old shape is still
    # present (idempotent; never on a fresh DB built from SCHEMA above).
    #
    # SAFE because foreign_keys defaults OFF on this connection (we never set
    # it ON here): DROPping snapshots does NOT cascade-delete the
    # snapshot_ranks rows that reference these ids, and the ids are preserved
    # by the rebuild, so those references stay valid.
    snap_row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='snapshots'"
    ).fetchone()
    snap_cols = [c[1] for c in conn.execute("PRAGMA table_info(snapshots)").fetchall()]
    needs_snap_rebuild = bool(snap_row) and (
        "UNIQUE" in snap_row[0].upper() or "created_at" not in snap_cols
    )
    if needs_snap_rebuild:
        conn.executescript(
            """
            CREATE TABLE snapshots_rebuild (
              id          INTEGER PRIMARY KEY AUTOINCREMENT,
              project_id  INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
              period_key  TEXT NOT NULL,
              label       TEXT NOT NULL,
              captured_at TEXT NOT NULL DEFAULT (date('now')),
              created_at  TEXT NOT NULL DEFAULT (datetime('now')),
              source      TEXT NOT NULL DEFAULT 'manual',
              locked      INTEGER NOT NULL DEFAULT 0
            );
            -- Existing rows predate created_at: seed it from captured_at (the
            -- best timestamp we have) so their ordering/labels stay sensible.
            INSERT INTO snapshots_rebuild (id, project_id, period_key, label, captured_at, created_at, source, locked)
              SELECT id, project_id, period_key, label, captured_at, captured_at, source, locked FROM snapshots;
            DROP TABLE snapshots;
            ALTER TABLE snapshots_rebuild RENAME TO snapshots;
            """
        )
        print("Migrated snapshots table: dropped one-per-month UNIQUE, added created_at")

    _seed(conn)

    conn.commit()
    conn.close()
