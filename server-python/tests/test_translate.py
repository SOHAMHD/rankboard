"""db._translate — the SQLite-flavoured SQL to Postgres rewriter.

The highest-value thing in this codebase to have tests for. Every query in the
application passes through it, it is a pure string function needing no database,
and its rules are not obvious:

* `?` becomes `%s`, everywhere, unconditionally.
* `INSERT OR IGNORE` becomes `INSERT … ON CONFLICT DO NOTHING`.
* A plain `INSERT` has `RETURNING id` appended — unless the table is in
  NO_ID_TABLES, or the statement already returns something, or the caller asked
  for returning=False (which `executemany` does).
* Three SQLite date functions are rewritten to `to_char(now() …)`.

A mistake in any of those is silent data corruption rather than a crash: a
missing `RETURNING id` gives `lastrowid = None`, an extra one makes an insert
fail against a table with no `id`, and a mangled placeholder shifts every
parameter by one.
"""

import pytest

from app.db import NO_ID_TABLES, _translate


# ── placeholders ──────────────────────────────────────────────────────

def test_question_marks_become_postgres_placeholders():
    out = _translate("SELECT * FROM users WHERE id = ? AND email = ?")
    assert out == "SELECT * FROM users WHERE id = %s AND email = %s"


def test_a_statement_with_no_placeholders_is_untouched():
    assert _translate("SELECT COUNT(*) FROM users") == "SELECT COUNT(*) FROM users"


def test_every_placeholder_is_converted():
    sql = "INSERT INTO locations (a, b, c, d, e) VALUES (?, ?, ?, ?, ?)"
    assert _translate(sql).count("%s") == 5
    assert "?" not in _translate(sql)


# ── date helpers ──────────────────────────────────────────────────────

@pytest.mark.parametrize("sqlite_fn,expected_fragment", [
    ("strftime('%Y-%m','now')", "'YYYY-MM'"),
    ("datetime('now')", "'YYYY-MM-DD HH24:MI:SS'"),
    ("date('now')", "'YYYY-MM-DD'"),
])
def test_date_functions_are_rewritten_to_utc(sqlite_fn, expected_fragment):
    out = _translate(f"SELECT {sqlite_fn}")
    assert "to_char" in out
    assert "AT TIME ZONE 'UTC'" in out
    assert expected_fragment in out
    assert sqlite_fn not in out


def test_a_date_function_inside_a_larger_statement_is_rewritten():
    # keyword_rank_service's upsert relies on this: datetime('now') appears in the
    # middle of an ON CONFLICT clause, not as the whole statement.
    out = _translate(
        "INSERT INTO keyword_ranks (keyword_id, month, rank) VALUES (?, ?, ?)"
        " ON CONFLICT (keyword_id, month) DO UPDATE"
        " SET rank = EXCLUDED.rank, updated_at = datetime('now')",
        returning=False,
    )
    assert "datetime('now')" not in out
    assert "to_char" in out
    assert out.count("%s") == 3


# ── RETURNING id ──────────────────────────────────────────────────────

def test_a_plain_insert_gets_returning_id():
    # _PgCursor consumes this into lastrowid; without it every caller that reads
    # cur.lastrowid silently gets None.
    out = _translate("INSERT INTO keywords (project_id, term) VALUES (?, ?)")
    assert out.rstrip().endswith("RETURNING id")


def test_returning_false_suppresses_it():
    # executemany passes returning=False — a multi-row insert with RETURNING would
    # change the statement's shape.
    out = _translate("INSERT INTO keywords (project_id, term) VALUES (?, ?)", returning=False)
    assert "RETURNING" not in out


@pytest.mark.parametrize("table", sorted(NO_ID_TABLES))
def test_tables_without_an_id_column_never_get_returning_id(table):
    # These have no `id`, so appending RETURNING id makes every insert fail.
    out = _translate(f"INSERT INTO {table} (a, b) VALUES (?, ?)")
    assert "RETURNING" not in out, f"{table} is in NO_ID_TABLES but got RETURNING id"


def test_an_explicit_returning_clause_is_not_duplicated():
    out = _translate("INSERT INTO keywords (project_id, term) VALUES (?, ?) RETURNING term")
    assert out.count("RETURNING") == 1
    assert "RETURNING term" in out


def test_a_trailing_semicolon_does_not_break_the_appended_clause():
    out = _translate("INSERT INTO keywords (project_id, term) VALUES (?, ?);")
    assert out.rstrip().endswith("RETURNING id")
    # "…VALUES (%s, %s); RETURNING id" would be a syntax error.
    assert ";" not in out.split("RETURNING")[0].rstrip()[-1:]


def test_returning_id_survives_an_on_conflict_clause():
    # Valid Postgres: INSERT … ON CONFLICT … DO UPDATE … RETURNING id.
    out = _translate(
        "INSERT INTO keyword_ranks (keyword_id, month, rank) VALUES (?, ?, ?)"
        " ON CONFLICT (keyword_id, month) DO UPDATE SET rank = EXCLUDED.rank"
    )
    assert out.rstrip().endswith("RETURNING id")


def test_select_update_and_delete_never_get_returning_id():
    for sql in ["SELECT * FROM keywords WHERE id = ?",
                "UPDATE keywords SET term = ? WHERE id = ?",
                "DELETE FROM keywords WHERE id = ?"]:
        assert "RETURNING" not in _translate(sql)


def test_leading_whitespace_does_not_hide_the_insert():
    # Several statements in this codebase are triple-quoted and start with a
    # newline; the INSERT detection has to look past that.
    out = _translate("\n   INSERT INTO keywords (project_id, term) VALUES (?, ?)")
    assert out.rstrip().endswith("RETURNING id")


# ── INSERT OR IGNORE ──────────────────────────────────────────────────

def test_insert_or_ignore_becomes_on_conflict_do_nothing():
    out = _translate("INSERT OR IGNORE INTO user_projects (user_id, project_id) VALUES (?, ?)")
    assert "INSERT OR IGNORE" not in out
    assert out.startswith("INSERT INTO user_projects")
    assert out.rstrip().endswith("ON CONFLICT DO NOTHING")


def test_insert_or_ignore_does_not_also_get_returning_id():
    # user_projects has no id column; both rules firing would produce
    # "… ON CONFLICT DO NOTHING RETURNING id" against a table that has none.
    out = _translate("INSERT OR IGNORE INTO user_projects (user_id, project_id) VALUES (?, ?)")
    assert "RETURNING" not in out


def test_an_existing_on_conflict_is_not_given_a_second_one():
    out = _translate(
        "INSERT OR IGNORE INTO email_events (message_id) VALUES (?)"
        " ON CONFLICT (message_id) DO NOTHING"
    )
    assert out.upper().count("ON CONFLICT") == 1


# ── caching ───────────────────────────────────────────────────────────

def test_the_cache_returns_consistent_results():
    # _translate is lru_cached on (sql, returning). The two must not collide —
    # a cache keyed on sql alone would serve an executemany the RETURNING variant.
    sql = "INSERT INTO keywords (project_id, term) VALUES (?, ?)"
    with_ret = _translate(sql, returning=True)
    without = _translate(sql, returning=False)
    assert "RETURNING id" in with_ret
    assert "RETURNING" not in without
    # And again, now that both are cached.
    assert _translate(sql, returning=True) == with_ret
    assert _translate(sql, returning=False) == without
