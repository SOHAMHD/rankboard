"""A tiny in-memory stand-in for the connection wrapper in app/db.py.

The keyword services take a connection as an argument and issue a small, fixed
set of statements against it, so a fake that recognises those statements lets the
whole rank pipeline be tested without a Postgres instance — including the things
that actually went wrong in production: whether a failed batch leaves partial
writes behind, and how many statements a save costs.

It dispatches on distinctive fragments of each query rather than parsing SQL. If
a service grows a new statement the fake raises instead of quietly returning
nothing, so the test suite tells you it needs teaching rather than passing on a
false assumption.
"""


class Row(dict):
    """A dict that also indexes by position and iterates values, like _Row.

    Iterating VALUES rather than keys matters: callers unpack single-column
    results with `(x,) = cur.fetchone()`. A dict's own __iter__ yields keys, so
    without this override `_current_month` returned the string "month" and every
    month-window assertion downstream silently passed.
    """

    def __getitem__(self, key):
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)

    def __iter__(self):
        return iter(self.values())


class Result:
    def __init__(self, rows=None, rowcount=0):
        self._rows = list(rows or [])
        self.rowcount = rowcount
        self.lastrowid = None

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)


class _Transaction:
    """Mimics psycopg's transaction(): rolls the store back if the body raises."""

    def __init__(self, db):
        self.db = db

    def __enter__(self):
        self.db.transaction_depth += 1
        self.db.transactions_opened += 1
        self._snapshot = dict(self.db.ranks)
        return self

    def __exit__(self, exc_type, exc, tb):
        self.db.transaction_depth -= 1
        if exc_type is not None:
            self.db.ranks = self._snapshot
            self.db.rolled_back = True
        return False


class FakeDb:
    """
    project_id: the one project that exists (anything else is "not found")
    keywords:   {keyword_id: term}
    ranks:      {(keyword_id, "YYYY-MM"): rank}
    now_month:  what strftime('%Y-%m','now') returns
    """

    def __init__(self, project_id=1, keywords=None, ranks=None, now_month="2026-08",
                 fail_upsert_on=None):
        self.project_id = project_id
        self.keywords = dict(keywords or {})
        self.ranks = dict(ranks or {})
        self.now_month = now_month
        #: (keyword_id, month) whose upsert should blow up, to exercise the
        #: rollback path — a driver-level failure mid-write is the only thing
        #: db.transaction() exists to contain.
        self.fail_upsert_on = fail_upsert_on
        self.statements = []          # every (sql, params) in order
        self.transaction_depth = 0
        self.transactions_opened = 0
        self.rolled_back = False

    # ── helpers ───────────────────────────────────────────────────────
    @property
    def write_count(self):
        return sum(
            1 for sql, _ in self.statements
            if sql.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))
        )

    def _kw_rows(self):
        return [Row(id=kid, term=term) for kid, term in sorted(self.keywords.items())]

    # ── connection API ────────────────────────────────────────────────
    def transaction(self):
        return _Transaction(self)

    def execute(self, sql, params=()):
        self.statements.append((sql, tuple(params)))
        s = " ".join(sql.split())

        if "strftime('%Y-%m','now')" in s:
            return Result([Row(month=self.now_month)])

        if s.startswith("SELECT id FROM projects WHERE id"):
            return Result([Row(id=self.project_id)] if params[0] == self.project_id else [])

        if s.startswith("SELECT id, term FROM keywords WHERE project_id"):
            return Result(self._kw_rows() if params[0] == self.project_id else [])

        if s.startswith("SELECT id FROM keywords WHERE project_id"):
            return Result(
                [Row(id=kid) for kid in sorted(self.keywords)]
                if params[0] == self.project_id else []
            )

        if "GROUP BY term HAVING COUNT(*) > 1" in s:
            counts = {}
            for term in self.keywords.values():
                counts[term] = counts.get(term, 0) + 1
            return Result([Row(term=t) for t, n in sorted(counts.items()) if n > 1])

        # get_grid's month-filtered join
        if s.startswith("SELECT r.keyword_id, r.month, r.rank FROM keyword_ranks"):
            months = set(params[1:])
            return Result([
                Row(keyword_id=kid, month=m, rank=rank)
                for (kid, m), rank in sorted(self.ranks.items())
                if m in months and kid in self.keywords
            ])

        # ranks_for_month
        if s.startswith("SELECT r.keyword_id, k.term, r.rank FROM keyword_ranks"):
            month = params[1]
            return Result([
                Row(keyword_id=kid, term=self.keywords[kid], rank=rank)
                for (kid, m), rank in sorted(self.ranks.items())
                if m == month and kid in self.keywords
            ])

        # _current_values
        if s.startswith("SELECT keyword_id, month, rank FROM keyword_ranks WHERE keyword_id IN"):
            wanted = set(params)
            return Result([
                Row(keyword_id=kid, month=m, rank=rank)
                for (kid, m), rank in sorted(self.ranks.items())
                if kid in wanted and m in wanted
            ])

        if s.startswith("DELETE FROM keyword_ranks"):
            key = (params[0], params[1])
            existed = key in self.ranks
            self.ranks.pop(key, None)
            return Result(rowcount=1 if existed else 0)

        if s.startswith("INSERT INTO keyword_ranks"):
            if self.fail_upsert_on == (params[0], params[1]):
                raise RuntimeError("simulated driver failure mid-write")
            self.ranks[(params[0], params[1])] = params[2]
            return Result(rowcount=1)

        raise AssertionError(f"FakeDb doesn't know this statement yet:\n  {s}")

    def executemany(self, sql, seq_of_params):
        rows = list(seq_of_params)
        total = 0
        for params in rows:
            total += self.execute(sql, params).rowcount
        return Result(rowcount=total)
