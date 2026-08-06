"""The monthly rank grid: validation, atomicity, and the report's three-month view.

Each test names the behaviour it protects. Several of these correspond to bugs
that were live in production — they're marked so nobody "simplifies" them away.
"""

import pytest
from fastapi import HTTPException

from app.services import keyword_rank_service as krs
from fake_db import FakeDb


# ── _clean_rank ───────────────────────────────────────────────────────

@pytest.mark.parametrize("value", [None, "", 0, -1, -999])
def test_blank_or_nonpositive_means_clear_the_cell(value):
    # Absence, not zero, is how "not ranking" is stored — that's what lets the
    # PDF tell "wasn't ranking, now is" apart from "no change".
    assert krs._clean_rank(value) is None


@pytest.mark.parametrize("value,expected", [(1, 1), ("7", 7), (krs.MAX_RANK, krs.MAX_RANK)])
def test_valid_ranks_pass_through(value, expected):
    assert krs._clean_rank(value) == expected


def test_rank_above_the_ceiling_is_rejected():
    # REGRESSION: unbounded, this reached Postgres as a value the INTEGER column
    # couldn't hold. The driver raised NumericValueOutOfRange — a DataError, and
    # so a sibling of IntegrityError, which is why the upsert's except clause
    # never caught it and the request 500'd.
    with pytest.raises(HTTPException) as exc:
        krs._clean_rank(99999999999)
    assert exc.value.status_code == 400
    assert str(krs.MAX_RANK) in exc.value.detail


def test_non_numeric_rank_is_rejected():
    with pytest.raises(HTTPException) as exc:
        krs._clean_rank("seven")
    assert exc.value.status_code == 400


# ── months ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("month", ["2026-01", "2026-12", "2000-01"])
def test_well_formed_months_are_accepted(month):
    assert krs._valid_month(month)


@pytest.mark.parametrize("month", [None, "", "2026", "2026-13", "2026-00", "26-01", "2026-1", "not-a-month"])
def test_malformed_months_are_rejected(month):
    assert not krs._valid_month(month)


def test_far_future_months_are_rejected():
    with pytest.raises(HTTPException) as exc:
        krs._check_month("2030-01", latest="2026-09")
    assert exc.value.status_code == 400
    assert "future" in exc.value.detail


def test_the_month_ceiling_allows_one_month_past_utc():
    # The grid builds its columns from the BROWSER's local time while the server
    # works in UTC. A strict UTC ceiling meant that from local midnight on the 1st
    # until UTC caught up, every client east of UTC asked for a month the server
    # called "the future" — and get_grid validates all requested months before
    # returning anything, so the whole Keywords screen 400'd for hours.
    db = FakeDb(keywords={1: "yoga"}, now_month="2026-08")
    assert krs.latest_allowed_month(db) == "2026-09"
    grid = krs.get_grid(db, 1, ["2026-09"])       # must not raise
    assert grid["months"] == ["2026-09"]


def test_the_month_ceiling_rolls_over_the_year():
    assert krs.latest_allowed_month(FakeDb(now_month="2026-12")) == "2027-01"


def test_a_month_two_ahead_is_still_rejected():
    db = FakeDb(keywords={1: "yoga"}, now_month="2026-08")
    with pytest.raises(HTTPException):
        krs.get_grid(db, 1, ["2026-10"])


def test_absurdly_old_months_are_rejected():
    with pytest.raises(HTTPException):
        krs._check_month("0202-05", latest="2026-08")


def test_clean_months_dedupes_and_keeps_order():
    assert krs.clean_months("2026-08, 2026-07 ,2026-08") == ["2026-08", "2026-07"]


def test_clean_months_requires_at_least_one():
    with pytest.raises(HTTPException):
        krs.clean_months("")


def test_clean_months_caps_the_request():
    many = ",".join(f"2020-{m:02d}" for m in range(1, 13)) + "," + ",".join(
        f"2021-{m:02d}" for m in range(1, 13)
    ) + ",2022-01"
    with pytest.raises(HTTPException) as exc:
        krs.clean_months(many)
    assert str(krs.MAX_MONTHS) in exc.value.detail


# ── get_grid ──────────────────────────────────────────────────────────

def _db(**kw):
    kw.setdefault("keywords", {1: "yoga", 2: "meditation"})
    return FakeDb(**kw)


def test_grid_returns_a_row_per_keyword_in_creation_order():
    db = _db(ranks={(1, "2026-08"): 4, (1, "2026-07"): 9})
    grid = krs.get_grid(db, 1, ["2026-07", "2026-08"])

    assert grid["months"] == ["2026-07", "2026-08"]
    assert [k["term"] for k in grid["keywords"]] == ["yoga", "meditation"]
    assert grid["keywords"][0]["ranks"] == {"2026-07": 9, "2026-08": 4}
    # A keyword with nothing recorded gets an empty map, not a missing key.
    assert grid["keywords"][1]["ranks"] == {}


def test_grid_ignores_months_outside_the_request():
    db = _db(ranks={(1, "2026-08"): 4, (1, "2026-01"): 50})
    grid = krs.get_grid(db, 1, ["2026-08"])
    assert grid["keywords"][0]["ranks"] == {"2026-08": 4}


def test_grid_404s_for_an_unknown_project():
    with pytest.raises(HTTPException) as exc:
        krs.get_grid(_db(), 999, ["2026-08"])
    assert exc.value.status_code == 404


# ── save_cells ────────────────────────────────────────────────────────

def test_saving_writes_and_clearing_deletes():
    db = _db(ranks={(2, "2026-08"): 30})
    out = krs.save_cells(db, 1, [
        {"keywordId": 1, "month": "2026-08", "rank": 5},
        {"keywordId": 2, "month": "2026-08", "rank": None},
    ])
    assert out == {"saved": 1, "cleared": 1}
    assert db.ranks == {(1, "2026-08"): 5}


def test_an_existing_cell_is_updated_in_one_statement():
    # The old implementation did UPDATE, checked rowcount, INSERTed, caught the
    # integrity error, then UPDATEd again — and never touched updated_at. One
    # ON CONFLICT upsert replaces all of that.
    db = _db(ranks={(1, "2026-08"): 9})
    krs.save_cells(db, 1, [{"keywordId": 1, "month": "2026-08", "rank": 3}])
    assert db.ranks[(1, "2026-08")] == 3
    assert db.write_count == 1
    upsert = [s for s, _ in db.statements if s.lstrip().startswith("INSERT")][0]
    assert "ON CONFLICT" in upsert
    assert "updated_at" in upsert


def test_a_bad_cell_writes_nothing_at_all():
    # REGRESSION: validation used to happen inside the write loop, and because
    # connections run with autocommit=True the cells before the bad one were
    # already committed while the caller was told the save had failed.
    db = _db()
    with pytest.raises(HTTPException) as exc:
        krs.save_cells(db, 1, [
            {"keywordId": 1, "month": "2026-08", "rank": 5},    # fine
            {"keywordId": 2, "month": "nonsense", "rank": 3},   # not
        ])
    assert exc.value.status_code == 400
    assert db.ranks == {}
    assert db.write_count == 0


def test_an_oversized_rank_late_in_the_batch_writes_nothing():
    db = _db()
    with pytest.raises(HTTPException):
        krs.save_cells(db, 1, [
            {"keywordId": 1, "month": "2026-08", "rank": 5},
            {"keywordId": 2, "month": "2026-08", "rank": 10**12},
        ])
    assert db.ranks == {}


def test_a_keyword_from_another_project_is_refused():
    db = _db()
    with pytest.raises(HTTPException) as exc:
        krs.save_cells(db, 1, [{"keywordId": 4242, "month": "2026-08", "rank": 5}])
    assert exc.value.status_code == 400
    assert db.write_count == 0


def test_the_same_cell_twice_in_one_batch_is_refused():
    db = _db()
    with pytest.raises(HTTPException) as exc:
        krs.save_cells(db, 1, [
            {"keywordId": 1, "month": "2026-08", "rank": 5},
            {"keywordId": 1, "month": "2026-08", "rank": 6},
        ])
    assert exc.value.status_code == 400
    assert "twice" in exc.value.detail


def test_an_over_large_batch_is_refused():
    db = _db()
    cells = [{"keywordId": 1, "month": "2026-08", "rank": 1}] * (krs.MAX_CELLS + 1)
    with pytest.raises(HTTPException):
        krs.save_cells(db, 1, cells)


def test_writes_happen_inside_a_transaction():
    db = _db()
    krs.save_cells(db, 1, [{"keywordId": 1, "month": "2026-08", "rank": 5}])
    assert db.transactions_opened == 1
    assert db.transaction_depth == 0
    assert db.rolled_back is False


def test_a_failure_mid_write_rolls_the_whole_batch_back():
    # Pre-validation covers the cases we can see coming. This covers the one we
    # can't — the driver failing on the third row after the first two are already
    # written. Without db.transaction() those two stay committed, because the
    # connection runs with autocommit=True.
    db = _db(keywords={1: "yoga", 2: "meditation", 3: "pranayama"},
             fail_upsert_on=(3, "2026-08"))
    with pytest.raises(RuntimeError):
        krs.save_cells(db, 1, [
            {"keywordId": 1, "month": "2026-08", "rank": 5},
            {"keywordId": 2, "month": "2026-08", "rank": 6},
            {"keywordId": 3, "month": "2026-08", "rank": 7},
        ])
    assert db.rolled_back is True
    assert db.ranks == {}


def test_a_delete_is_rolled_back_with_a_failed_upsert():
    # Deletes run first, so a later upsert failure has to undo them too.
    db = _db(ranks={(2, "2026-08"): 30}, fail_upsert_on=(1, "2026-08"))
    with pytest.raises(RuntimeError):
        krs.save_cells(db, 1, [
            {"keywordId": 2, "month": "2026-08", "rank": None},
            {"keywordId": 1, "month": "2026-08", "rank": 5},
        ])
    assert db.ranks == {(2, "2026-08"): 30}   # the cleared cell came back


# ── optimistic concurrency ────────────────────────────────────────────

def test_expected_value_matching_the_store_saves_normally():
    db = _db(ranks={(1, "2026-08"): 9})
    out = krs.save_cells(db, 1, [
        {"keywordId": 1, "month": "2026-08", "rank": 4, "expected": 9},
    ])
    assert out["saved"] == 1
    assert db.ranks[(1, "2026-08")] == 4


def test_a_cell_changed_underneath_you_raises_409():
    db = _db(ranks={(1, "2026-08"): 3})   # someone else already moved it to 3
    with pytest.raises(HTTPException) as exc:
        krs.save_cells(db, 1, [
            {"keywordId": 1, "month": "2026-08", "rank": 4, "expected": 9},
        ])
    assert exc.value.status_code == 409
    assert "yoga" in exc.value.detail
    assert db.ranks == {(1, "2026-08"): 3}   # untouched


def test_expecting_an_empty_cell_that_now_has_a_value_raises_409():
    db = _db(ranks={(1, "2026-08"): 3})
    with pytest.raises(HTTPException) as exc:
        krs.save_cells(db, 1, [
            {"keywordId": 1, "month": "2026-08", "rank": 4, "expected": None},
        ])
    assert exc.value.status_code == 409


def test_a_legacy_rank_above_the_ceiling_can_still_be_corrected():
    # `expected` is what the grid read back from the database, not something the
    # user typed. keyword_ranks only ever constrained rank >= 1, so rows written
    # before MAX_RANK existed can hold a bigger number — and validating `expected`
    # against the ceiling made exactly those cells impossible to fix, with an
    # error blaming the user for a value they never entered.
    db = _db(ranks={(1, "2026-08"): 5000})
    out = krs.save_cells(db, 1, [
        {"keywordId": 1, "month": "2026-08", "rank": 7, "expected": 5000},
    ])
    assert out["saved"] == 1
    assert db.ranks[(1, "2026-08")] == 7


def test_a_legacy_rank_above_the_ceiling_can_still_be_cleared():
    db = _db(ranks={(1, "2026-08"): 5000})
    out = krs.save_cells(db, 1, [
        {"keywordId": 1, "month": "2026-08", "rank": None, "expected": 5000},
    ])
    assert out["cleared"] == 1
    assert db.ranks == {}


def test_omitting_expected_keeps_last_write_wins():
    db = _db(ranks={(1, "2026-08"): 3})
    out = krs.save_cells(db, 1, [{"keywordId": 1, "month": "2026-08", "rank": 4}])
    assert out["saved"] == 1
    assert db.ranks[(1, "2026-08")] == 4


# ── ranks_for_month and the duplicate-term fallback ───────────────────

def test_ranks_for_month_keys_by_id_and_term():
    db = _db(ranks={(1, "2026-08"): 4, (2, "2026-08"): 12})
    maps = krs.ranks_for_month(db, 1, "2026-08")
    assert maps["by_keyword_id"] == {1: 4, 2: 12}
    assert maps["by_term"] == {"yoga": 4, "meditation": 12}
    assert maps["count"] == 2


def test_a_term_held_by_two_keywords_is_left_out_of_the_term_map():
    # REGRESSION: with no uniqueness on (project_id, term) a project could hold
    # two keywords called "yoga". by_term was a plain dict, so the second
    # overwrote the first, and the duplicate that had no rank of its own picked
    # up its twin's number through the fallback and reported it as its own.
    db = _db(keywords={1: "yoga", 2: "yoga", 3: "meditation"},
             ranks={(1, "2026-08"): 4, (3, "2026-08"): 12})
    maps = krs.ranks_for_month(db, 1, "2026-08")
    assert maps["by_keyword_id"] == {1: 4, 3: 12}
    assert "yoga" not in maps["by_term"]
    assert maps["by_term"] == {"meditation": 12}


def test_ambiguous_terms_reports_duplicates():
    db = _db(keywords={1: "yoga", 2: "yoga", 3: "meditation"})
    assert krs.ambiguous_terms(db, 1) == {"yoga"}


def test_ambiguous_terms_is_empty_for_a_clean_project():
    assert krs.ambiguous_terms(_db(), 1) == set()
