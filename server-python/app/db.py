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
import re
import sqlite3
import secrets
from pathlib import Path

# Tables whose primary key is NOT a column named `id` (so the Postgres bridge
# must not append "RETURNING id" to their INSERTs). email_otp keys on user_id;
# user_projects has no surrogate key (it inserts via INSERT OR IGNORE anyway);
# locations keys on location_code (DataForSEO's own id).
NO_ID_TABLES = {"email_otp", "password_otp", "user_projects", "locations"}

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
  totp_secret          TEXT,                                 -- base32 TOTP secret (NULL until enrolled)
  totp_enabled         INTEGER NOT NULL DEFAULT 0,           -- 1 once the authenticator is confirmed
  created_at           TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS emails (
  id       INTEGER PRIMARY KEY AUTOINCREMENT,
  to_email TEXT NOT NULL,
  subject  TEXT NOT NULL,
  body     TEXT NOT NULL,
  sent_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- GEO TARGETS — our own copy of DataForSEO's location list, so the picker's
-- type-ahead is a local indexed query (never a DataForSEO round-trip) and a
-- submitted code can be validated server-side against real data.
--   location_code  DataForSEO's own id; exactly what the rank checker sends.
--   kind           'country' | 'region' | 'city' — one per picker input.
--   country_code   the country this row belongs to (a country points at itself).
--   region_code    the region a city sits in; NULL when the source has none.
--   full_name      "Perth, Western Australia, Australia" (display + search).
--   alt            extra search-only strings ("UK", "USA"); never displayed.
-- Seeded with all 249 countries at first boot; run
-- `python -m scripts.import_locations` to load every region + city.
--   name_key       lower(name) — the prefix match runs against this, so no
--                  per-row LOWER() and the index is usable.
--   search_key     " perth western australia australia " — full_name with its
--                  commas turned into spaces, plus alt, lowercased and padded
--                  with a space at each end. ONE column to LIKE against instead
--                  of three ORs, and the padding lets '% perth%' mean
--                  "a word starts with perth".
CREATE TABLE IF NOT EXISTS locations (
  location_code INTEGER PRIMARY KEY,
  name          TEXT NOT NULL,
  full_name     TEXT NOT NULL,
  kind          TEXT NOT NULL CHECK (kind IN ('country','region','city')),
  country_code  INTEGER,
  region_code   INTEGER,
  country_iso   TEXT,
  location_type TEXT,
  alt           TEXT NOT NULL DEFAULT '',
  name_key      TEXT,
  search_key    TEXT
);
-- NOTE: the locations indexes are NOT declared here. They index name_key, which
-- an older database only gains from the ALTER in _init_sqlite() — and this whole
-- script runs BEFORE those ALTERs, so a CREATE INDEX on name_key would fail with
-- "no such column". _init_sqlite() creates them right after the ALTERs instead.

CREATE TABLE IF NOT EXISTS projects (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  name            TEXT NOT NULL,
  domain          TEXT,
  location_code   INTEGER,
  country_code    INTEGER,
  region_code     INTEGER,
  city_code       INTEGER,
  location_label  TEXT,
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

-- The Rank Ledger reads a project's keywords on nearly every dashboard load and
-- on every snapshot/report build, always as
--   WHERE project_id = ? ORDER BY created_at, id
-- and there was NO index on this table at all, so each of those was a full scan.
-- Indexing (project_id, created_at, id) matches both the filter and the sort, so
-- the rows come back in order with no separate sort step.
CREATE INDEX IF NOT EXISTS idx_keywords_project_created
  ON keywords (project_id, created_at, id);

-- MANUAL MONTHLY RANKS. One row per keyword per month, typed in by the team on
-- the Keywords page — there is no live rank checking. Replaces the
-- snapshots/snapshot_ranks pair, which existed to FREEZE the result of an
-- automated check; when a human enters the number for a month, the month itself
-- is the freeze and a separate snapshot adds nothing.
--
-- month is "YYYY-MM", the SAME key format reports/backlinks/posts use, so the
-- report's three-month keyword table is three reads from this one table.
-- UNIQUE(keyword_id, month) makes the grid's save an upsert rather than a
-- delete-and-reinsert. rank is NULLABLE: a blank cell means "not recorded",
-- which is different from "not ranking".
CREATE TABLE IF NOT EXISTS keyword_ranks (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  keyword_id INTEGER NOT NULL REFERENCES keywords(id) ON DELETE CASCADE,
  month      TEXT NOT NULL,
  rank       INTEGER CHECK (rank IS NULL OR rank >= 1),
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(keyword_id, month)
);

-- The grid reads a project's whole matrix at once and the report reads three
-- specific months; both filter by month after joining through keywords.
CREATE INDEX IF NOT EXISTS idx_keyword_ranks_month
  ON keyword_ranks (month, keyword_id);

-- Per-project content links the SEO team publishes: blog posts and LinkedIn
-- posts. `kind` splits the two; url required, title optional. Shown in the
-- dashboard Posts section and in the report.
CREATE TABLE IF NOT EXISTS posts (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id  INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  kind        TEXT NOT NULL CHECK (kind IN ('blog','linkedin')),
  url         TEXT NOT NULL,
  title       TEXT,
  month       TEXT,                             -- "YYYY-MM"; NULL falls back to created_at's month
  created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_posts_project_kind ON posts (project_id, kind);

-- Hot read paths: snapshot rank rows are always fetched by snapshot_id; the
-- snapshot list/pick queries by (project_id, period_key); the newest Moz row is
-- picked by (project_id, fetched_at). Without these, each is a full scan.
CREATE INDEX IF NOT EXISTS idx_snapshot_ranks_snapshot
  ON snapshot_ranks (snapshot_id);
CREATE INDEX IF NOT EXISTS idx_snapshots_project_period
  ON snapshots (project_id, period_key);
CREATE INDEX IF NOT EXISTS idx_moz_metrics_project_fetched
  ON moz_metrics (project_id, fetched_at);

-- ── Two-factor auth (TOTP) ────────────────────────────────────────────────
-- Single-use recovery codes (bcrypt-hashed); used_at set when consumed so a
-- code can never be replayed.
CREATE TABLE IF NOT EXISTS twofa_backup_codes (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  code_hash  TEXT NOT NULL,
  used_at    TEXT
);
CREATE INDEX IF NOT EXISTS idx_twofa_backup_user ON twofa_backup_codes (user_id);

-- Super Admin's email one-time code (the 3rd step). One active code per user,
-- bcrypt-hashed, with an expiry and attempt counter to throttle guessing.
CREATE TABLE IF NOT EXISTS email_otp (
  user_id     INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  code_hash   TEXT NOT NULL,
  expires_at  TEXT NOT NULL,
  attempts    INTEGER NOT NULL DEFAULT 0
);

-- Change-password email code: a signed-in user requests it, then must enter it
-- to set a new password. One active code per user, bcrypt-hashed, with an
-- expiry and attempt throttle (same shape as email_otp).
CREATE TABLE IF NOT EXISTS password_otp (
  user_id     INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  code_hash   TEXT NOT NULL,
  expires_at  TEXT NOT NULL,
  attempts    INTEGER NOT NULL DEFAULT 0
);

-- ── Rank-check audit + rate limit ─────────────────────────────────────────
-- One row per successful "Check rankings" run. Powers the quota: a user may
-- run at most N checks per project in a rolling window (see rank_provider /
-- the check-ranks route). Kept as an append-only log so we can also show "last
-- checked by" and when the quota resets. Cascades away with the user/project.
CREATE TABLE IF NOT EXISTS rank_check_log (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  project_id  INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_rank_check_log_user_project
  ON rank_check_log (user_id, project_id, created_at);
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
  totp_secret          TEXT,
  totp_enabled         INTEGER NOT NULL DEFAULT 0,
  created_at           TEXT NOT NULL DEFAULT to_char((now() AT TIME ZONE 'UTC'), 'YYYY-MM-DD HH24:MI:SS')
);

CREATE TABLE IF NOT EXISTS emails (
  id       INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
  to_email TEXT NOT NULL,
  subject  TEXT NOT NULL,
  body     TEXT NOT NULL,
  sent_at  TEXT NOT NULL DEFAULT to_char((now() AT TIME ZONE 'UTC'), 'YYYY-MM-DD HH24:MI:SS')
);

-- GEO TARGETS — see the SQLite block above for the full rationale.
CREATE TABLE IF NOT EXISTS locations (
  location_code INTEGER PRIMARY KEY,
  name          TEXT NOT NULL,
  full_name     TEXT NOT NULL,
  kind          TEXT NOT NULL CHECK (kind IN ('country','region','city')),
  country_code  INTEGER,
  region_code   INTEGER,
  country_iso   TEXT,
  location_type TEXT,
  alt           TEXT NOT NULL DEFAULT '',
  name_key      TEXT,
  search_key    TEXT
);
-- Databases loaded before the search keys existed (the 119k-row import) get them
-- added here; _backfill_location_keys() then fills them in one UPDATE.
ALTER TABLE locations ADD COLUMN IF NOT EXISTS name_key   TEXT;
ALTER TABLE locations ADD COLUMN IF NOT EXISTS search_key TEXT;

-- The first cut indexed `name`; these index name_key instead. NEW NAMES on
-- purpose — CREATE INDEX IF NOT EXISTS is a no-op when the name already exists,
-- so reusing them would silently keep the old, useless definition. The originals
-- are dropped by name (idempotent).
DROP INDEX IF EXISTS idx_locations_kind_name;
DROP INDEX IF EXISTS idx_locations_kind_country;
DROP INDEX IF EXISTS idx_locations_kind_region;

-- text_pattern_ops is REQUIRED for Postgres to use these with LIKE 'perth%'.
-- Under a locale collation (en_US.UTF-8 on Supabase) a default btree index is
-- unusable for prefix matching, and the planner silently falls back to scanning
-- all 119k rows on every keystroke.
CREATE INDEX IF NOT EXISTS idx_locations_key
  ON locations (kind, name_key text_pattern_ops);
CREATE INDEX IF NOT EXISTS idx_locations_country_key
  ON locations (kind, country_code, name_key text_pattern_ops);
CREATE INDEX IF NOT EXISTS idx_locations_region_key
  ON locations (kind, region_code, name_key text_pattern_ops);

CREATE TABLE IF NOT EXISTS projects (
  id              INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
  name            TEXT NOT NULL,
  domain          TEXT,
  location_code   INTEGER,
  country_code    INTEGER,
  region_code     INTEGER,
  city_code       INTEGER,
  location_label  TEXT,
  ga_property_id  TEXT,
  gsc_site_url    TEXT,
  active          INTEGER NOT NULL DEFAULT 1,
  created_at      TEXT NOT NULL DEFAULT to_char((now() AT TIME ZONE 'UTC'), 'YYYY-MM-DD HH24:MI:SS')
);
-- Older Postgres databases predate the split country/region/city columns
-- (CREATE TABLE IF NOT EXISTS above won't alter an existing table).
ALTER TABLE projects ADD COLUMN IF NOT EXISTS country_code   INTEGER;
ALTER TABLE projects ADD COLUMN IF NOT EXISTS region_code    INTEGER;
ALTER TABLE projects ADD COLUMN IF NOT EXISTS city_code      INTEGER;
ALTER TABLE projects ADD COLUMN IF NOT EXISTS location_label TEXT;

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

-- The Rank Ledger reads a project's keywords on nearly every dashboard load and
-- on every snapshot/report build, always as
--   WHERE project_id = ? ORDER BY created_at, id
-- and there was NO index on this table at all, so each of those was a full scan.
-- Indexing (project_id, created_at, id) matches both the filter and the sort, so
-- the rows come back in order with no separate sort step.
CREATE INDEX IF NOT EXISTS idx_keywords_project_created
  ON keywords (project_id, created_at, id);

-- MANUAL MONTHLY RANKS — see the SQLite block above for the full rationale.
CREATE TABLE IF NOT EXISTS keyword_ranks (
  id         INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
  keyword_id INTEGER NOT NULL REFERENCES keywords(id) ON DELETE CASCADE,
  month      TEXT NOT NULL,
  rank       INTEGER CHECK (rank IS NULL OR rank >= 1),
  updated_at TEXT NOT NULL DEFAULT to_char((now() AT TIME ZONE 'UTC'), 'YYYY-MM-DD HH24:MI:SS'),
  UNIQUE(keyword_id, month)
);

CREATE INDEX IF NOT EXISTS idx_keyword_ranks_month
  ON keyword_ranks (month, keyword_id);

CREATE TABLE IF NOT EXISTS posts (
  id          INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
  project_id  INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  kind        TEXT NOT NULL CHECK (kind IN ('blog','linkedin')),
  url         TEXT NOT NULL,
  title       TEXT,
  month       TEXT,
  created_at  TEXT NOT NULL DEFAULT to_char((now() AT TIME ZONE 'UTC'), 'YYYY-MM-DD HH24:MI:SS')
);
CREATE INDEX IF NOT EXISTS idx_posts_project_kind ON posts (project_id, kind);
-- Older Postgres databases created before `month` existed: add it in place
-- (CREATE TABLE IF NOT EXISTS above won't alter an existing table).
ALTER TABLE posts ADD COLUMN IF NOT EXISTS month TEXT;

CREATE INDEX IF NOT EXISTS idx_snapshot_ranks_snapshot
  ON snapshot_ranks (snapshot_id);
CREATE INDEX IF NOT EXISTS idx_snapshots_project_period
  ON snapshots (project_id, period_key);
CREATE INDEX IF NOT EXISTS idx_moz_metrics_project_fetched
  ON moz_metrics (project_id, fetched_at);

-- ── Two-factor auth (TOTP) ────────────────────────────────────────────────
ALTER TABLE users ADD COLUMN IF NOT EXISTS totp_secret TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS totp_enabled INTEGER NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS twofa_backup_codes (
  id         INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
  user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  code_hash  TEXT NOT NULL,
  used_at    TEXT
);
CREATE INDEX IF NOT EXISTS idx_twofa_backup_user ON twofa_backup_codes (user_id);

CREATE TABLE IF NOT EXISTS email_otp (
  user_id     INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  code_hash   TEXT NOT NULL,
  expires_at  TEXT NOT NULL,
  attempts    INTEGER NOT NULL DEFAULT 0
);

-- Change-password email code: a signed-in user requests it, then must enter it
-- to set a new password. One active code per user, bcrypt-hashed, with an
-- expiry and attempt throttle (same shape as email_otp).
CREATE TABLE IF NOT EXISTS password_otp (
  user_id     INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  code_hash   TEXT NOT NULL,
  expires_at  TEXT NOT NULL,
  attempts    INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS rank_check_log (
  id          INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
  user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  project_id  INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  created_at  TEXT NOT NULL DEFAULT to_char(now(), 'YYYY-MM-DD HH24:MI:SS')
);
CREATE INDEX IF NOT EXISTS idx_rank_check_log_user_project
  ON rank_check_log (user_id, project_id, created_at);
"""


# ── Postgres dialect bridge (active only when IS_POSTGRES) ────────────────────
def _translate(sql: str, returning: bool = True) -> str:
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
    elif returning and head.startswith("INSERT") and "RETURNING" not in s.upper():
        # Postgres has no cursor.lastrowid; RETURNING id surfaces the new key,
        # which _PgCursor exposes as cur.lastrowid. Skipped for executemany (bulk)
        # inserts, and for tables whose primary key ISN'T a column named `id`
        # (e.g. email_otp keys on user_id) — those have no `id` to return.
        m = re.search(r"insert\s+into\s+\"?([a-zA-Z_]\w*)\"?", s, re.IGNORECASE)
        table = m.group(1).lower() if m else ""
        if table not in NO_ID_TABLES:
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

    def executemany(self, sql, seq_of_params):
        # Bulk insert/update in one round-trip. No RETURNING (nothing reads a
        # generated key here), so lastrowid stays None — matching sqlite3's
        # executemany, which also doesn't populate lastrowid usefully.
        translated = _translate(sql, returning=False)
        rows = list(seq_of_params)
        cur = self._conn.cursor()
        if rows:
            cur.executemany(translated, rows)
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


def _seed_locations(conn) -> None:
    """Populate the geo-target table so the picker works on a brand-new database:
    all 249 countries plus the verified metro cities (app/locations.py explains
    where those come from). Only fires while the table is empty, so it never
    fights `python -m scripts.import_locations` — once that has loaded the full
    worldwide set, this is a no-op forever.

    """
    (have,) = conn.execute("SELECT COUNT(*) FROM locations").fetchone()
    if have == 0:
        from .locations import seed_rows

        rows = seed_rows()
        conn.executemany(
            "INSERT INTO locations (location_code, name, full_name, kind,"
            " country_code, region_code, country_iso, location_type, alt,"
            " name_key, search_key)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        print(f"Seeded {len(rows)} locations (countries + verified metro cities)")

    _backfill_location_keys(conn)


def _backfill_location_keys(conn) -> None:
    """Fill name_key / search_key on rows that predate them — i.e. everything a
    previous `import_locations` run loaded. Done as ONE UPDATE in SQL rather than
    reading 119k rows into Python and writing them back.

    search_key gets a space at each end and commas turned into spaces, so
    LIKE '% perth%' means "some word starts with perth". Guarded on
    name_key IS NULL, so it runs once and then costs a single indexed check."""
    (stale,) = conn.execute("SELECT COUNT(*) FROM locations WHERE name_key IS NULL").fetchone()
    if not stale:
        return
    conn.execute(
        "UPDATE locations SET"
        "  name_key = LOWER(name),"
        "  search_key = ' ' || LOWER(REPLACE(REPLACE(REPLACE(full_name, ',', ' '), '  ', ' '), '  ', ' '))"
        "               || ' ' || LOWER(alt) || ' '"
        " WHERE name_key IS NULL"
    )
    print(f"Back-filled search keys on {stale:,} locations")


def _backfill_project_locations(conn) -> None:
    """Projects created before the country/region/city split stored ONE
    location_code — a country or a metro city. Its row in `locations` says which,
    so derive the split columns and the display label from it. Guarded on
    country_code IS NULL, so each project is touched once and hand-picked
    region/city choices are never overwritten."""
    conn.execute(
        "UPDATE projects SET"
        "  country_code = (SELECT l.country_code FROM locations l"
        "                  WHERE l.location_code = projects.location_code),"
        "  city_code = (SELECT CASE WHEN l.kind = 'city' THEN l.location_code END"
        "               FROM locations l WHERE l.location_code = projects.location_code),"
        "  location_label = (SELECT l.full_name FROM locations l"
        "                    WHERE l.location_code = projects.location_code)"
        " WHERE location_code IS NOT NULL AND country_code IS NULL"
    )


def _seed(conn) -> None:
    """Shared first-boot seed, written in SQLite SQL (the Postgres path runs it
    through the _translate bridge). Idempotent: each block only fires when its
    table is empty, so it's safe on every boot and on a host that resets the DB.

    NOTE: does NOT port existing SQLite rows — this is a fresh seed only.
    """
    _seed_locations(conn)

    (count,) = conn.execute("SELECT COUNT(*) FROM users").fetchone()
    if count == 0:
        # The seed password comes ONLY from the environment (SEED_ADMIN_PASSWORD).
        # We never auto-generate-and-print a password: printing a working Super
        # Admin credential to stdout leaks it into log aggregation forever. If the
        # env var is unset we SKIP the seed (no default credential ever ships).
        # The seeded account is forced to rotate its password on first sign-in.
        env_pw = os.environ.get("SEED_ADMIN_PASSWORD", "").strip()
        if not env_pw:
            print(
                "No users found and SEED_ADMIN_PASSWORD is unset — skipping the "
                "Super Admin seed. Set SEED_ADMIN_PASSWORD and restart to create it."
            )
        else:
            pw_hash = bcrypt.hashpw(env_pw.encode(), bcrypt.gensalt()).decode()
            conn.execute(
                "INSERT INTO users (name, email, role, password_hash, must_change_password, status)"
                " VALUES (?, ?, ?, ?, 1, 'active')",
                ("Soham Dhokiya", "soham@infyappdevelopment.com", "Super Admin", pw_hash),
            )
            print(
                "Seeded first Super Admin (soham@infyappdevelopment.com) — must change "
                "password on first sign-in. Only the bcrypt hash is stored; the "
                "password is never printed."
            )

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

    # Last: every project row (seeded or pre-existing) gets its split
    # country/region/city columns derived from its single location_code.
    _backfill_project_locations(conn)


def _init_pg() -> None:
    """Postgres: create the schema additively (CREATE TABLE IF NOT EXISTS) and
    seed. No destructive SQL; runs against the empty Supabase database on first
    boot. The seed reuses _seed() via the dialect bridge."""
    conn = get_connection()
    try:
        # Run each statement separately on the raw psycopg connection (psycopg's
        # extended protocol executes one statement per call). We STRIP SQL line
        # comments first, then split on ';' — otherwise a ';' inside a `-- ...`
        # comment would break a comment into invalid fragments. (The schema has
        # no string literals containing '--' or ';', so this is safe.)
        raw = conn._conn  # the underlying psycopg connection
        schema_sql = re.sub(r"--[^\n]*", "", _PG_SCHEMA)
        for statement in schema_sql.split(";"):
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

    # The country/region/city split behind the new three-input picker.
    # `location_code` stays the single EFFECTIVE code the rank checker sends
    # (the most specific of the three); these record what was actually picked
    # so the edit form can show it back, plus a ready-made display label.
    for column, decl in (
        ("country_code", "INTEGER"),
        ("region_code", "INTEGER"),
        ("city_code", "INTEGER"),
        ("location_label", "TEXT"),
    ):
        try:
            conn.execute(f"ALTER TABLE projects ADD COLUMN {column} {decl}")
        except sqlite3.OperationalError:
            pass  # column already exists

    # (Existing rows are back-filled from the locations table in _seed(), which
    # runs after that table has been populated.)

    # Search keys on a locations table that predates them, plus the now-unused
    # indexes on `name` that they replace. _backfill_location_keys() fills them.
    for column in ("name_key", "search_key"):
        try:
            conn.execute(f"ALTER TABLE locations ADD COLUMN {column} TEXT")
        except sqlite3.OperationalError:
            pass  # column already exists
    for index in ("idx_locations_kind_name", "idx_locations_kind_country", "idx_locations_kind_region"):
        conn.execute(f"DROP INDEX IF EXISTS {index}")

    # Safe to create only now that name_key is guaranteed to exist (see the note
    # where the locations table is declared in SCHEMA).
    conn.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_locations_key         ON locations (kind, name_key);
        CREATE INDEX IF NOT EXISTS idx_locations_country_key ON locations (kind, country_code, name_key);
        CREATE INDEX IF NOT EXISTS idx_locations_region_key  ON locations (kind, region_code, name_key);
        """
    )

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

    # Two-factor auth columns (older DBs predate them). Same poor-man's
    # migration as the project columns above.
    try:
        conn.execute("ALTER TABLE users ADD COLUMN totp_secret TEXT")
    except sqlite3.OperationalError:
        pass  # column already exists
    try:
        conn.execute("ALTER TABLE users ADD COLUMN totp_enabled INTEGER NOT NULL DEFAULT 0")
    except sqlite3.OperationalError:
        pass  # column already exists

    # Posts gained a month tag ("YYYY-MM") after older DBs were created; the
    # Posts routes read/write/filter it, so add it in place. Same poor-man's
    # migration as the columns above.
    try:
        conn.execute("ALTER TABLE posts ADD COLUMN month TEXT")
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
    # constraint in place, so rebuild the snapshots table — but only when the
    # OLD shape is still present. Idempotent: on a fresh DB (the schema created
    # by SCHEMA above has no UNIQUE and already has created_at) this is skipped,
    # so it never fires on the current schema.
    snap_row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'snapshots'"
    ).fetchone()
    snap_sql = (snap_row[0] if snap_row else "") or ""
    snap_cols = {c[1] for c in conn.execute("PRAGMA table_info(snapshots)").fetchall()}
    needs_snapshot_rebuild = bool(snap_cols) and (
        "created_at" not in snap_cols
        or ("UNIQUE" in snap_sql.upper() and "PERIOD_KEY" in snap_sql.upper())
    )
    if needs_snapshot_rebuild:
        # Copy every row forward, defaulting any column the OLD table lacked.
        # Column names come from PRAGMA (trusted schema); fallbacks are literals.
        label_col = "label" if "label" in snap_cols else "''"
        captured_col = "captured_at" if "captured_at" in snap_cols else "date('now')"
        created_col = "created_at" if "created_at" in snap_cols else "datetime('now')"
        source_col = "source" if "source" in snap_cols else "'manual'"
        locked_col = "locked" if "locked" in snap_cols else "0"
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
            """
        )
        conn.execute(
            "INSERT INTO snapshots_rebuild "
            "(id, project_id, period_key, label, captured_at, created_at, source, locked) "
            "SELECT id, project_id, period_key, "
            + label_col + ", " + captured_col + ", " + created_col + ", "
            + source_col + ", " + locked_col + " FROM snapshots"
        )
        conn.executescript(
            """
            DROP TABLE snapshots;
            ALTER TABLE snapshots_rebuild RENAME TO snapshots;
            CREATE INDEX IF NOT EXISTS idx_snapshots_project_period
              ON snapshots (project_id, period_key);
            """
        )
        print("Migrated snapshots table: dropped one-per-month UNIQUE, added created_at")

    # First-boot seed, then persist and close (mirrors the Postgres path).
    _seed(conn)
    conn.commit()
    conn.close()