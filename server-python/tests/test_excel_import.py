"""Excel keyword import: what happens when the file isn't the template.

The import dialog says "Download the template and fill in your keywords", but
people upload a Book1.xlsx they typed themselves, or an export from another tool.
Every one of those paths used to be able to reach an unhandled exception, which
the client rendered as "Something went wrong on the server." — no indication that
the file was the problem or what to change.
"""

import io

import pytest
from openpyxl import Workbook

from app.services.excel_service import (
    MAX_ROWS,
    MAX_TERM_LEN,
    build_sample_workbook,
    parse_keyword_workbook,
)


def book(rows, *, sheet_title="Sheet1", header="Keyword") -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = sheet_title
    if header is not None:
        ws.append([header])
    for r in rows:
        ws.append(r if isinstance(r, (list, tuple)) else [r])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ── the happy path, on a file the user made themselves ────────────────

def test_a_hand_made_book1_imports():
    # No styling, no notes, header typed in lowercase — nothing like the template.
    valid, errors = parse_keyword_workbook(book(["Yoga Classes Online", "meditation retreat"], header="keyword"))
    assert [v["term"] for v in valid] == ["yoga classes online", "meditation retreat"]
    assert errors == []


def test_terms_are_lowercased_and_trimmed():
    valid, _ = parse_keyword_workbook(book(["  Pranayama Course  "]))
    assert valid[0]["term"] == "pranayama course"


def test_the_shipped_template_round_trips():
    # The sample file's own notes rows must not come back as keywords.
    valid, errors = parse_keyword_workbook(build_sample_workbook())
    assert [v["term"] for v in valid] == [
        "online yoga classes",
        "meditation retreat rishikesh",
        "pranayama breathing course",
    ]
    assert errors == []


# ── files that aren't workbooks ───────────────────────────────────────

@pytest.mark.parametrize("payload", [
    b"",
    b"not a spreadsheet at all",
    b"PK\x03\x04 truncated zip",
    ("term,rank\nyoga,4\n").encode(),   # a CSV renamed to .xlsx
])
def test_junk_is_a_clean_error_not_a_crash(payload):
    # ValueError is what the router turns into a 400 with the message attached.
    with pytest.raises(ValueError) as exc:
        parse_keyword_workbook(payload)
    assert "Excel" in str(exc.value)


# ── shapes that used to escape as a 500 ───────────────────────────────

def test_a_numeric_cell_is_read_as_text():
    # Someone numbers their rows and the keyword lands in column A as an int.
    # str() on it is fine; the old code path was fine too, but assert it because
    # openpyxl returns a real int here, not a string.
    valid, _ = parse_keyword_workbook(book([2024, 15.5]))
    assert [v["term"] for v in valid] == ["2024", "15.5"]


def test_blank_rows_between_keywords_are_skipped():
    valid, errors = parse_keyword_workbook(book(["yoga", None, "", "   ", "meditation"]))
    assert [v["term"] for v in valid] == ["yoga", "meditation"]
    assert errors == []


def test_extra_columns_are_ignored():
    # An export with keyword, volume, difficulty. Only column A is read.
    valid, _ = parse_keyword_workbook(book([["yoga", 1200, "medium"], ["reiki", 90, "low"]]))
    assert [v["term"] for v in valid] == ["yoga", "reiki"]


def test_a_wholly_empty_sheet_yields_nothing_rather_than_erroring():
    valid, errors = parse_keyword_workbook(book([]))
    assert valid == []
    assert errors == []


# ── the limits ────────────────────────────────────────────────────────

def test_an_overlong_cell_is_reported_against_its_row():
    valid, errors = parse_keyword_workbook(book(["yoga", "x" * (MAX_TERM_LEN + 1), "reiki"]))
    assert [v["term"] for v in valid] == ["yoga", "reiki"]
    assert len(errors) == 1
    # Row 3: header is row 1, "yoga" is row 2.
    assert errors[0]["row"] == 3


def test_duplicates_within_the_file_are_reported_once_each():
    valid, errors = parse_keyword_workbook(book(["yoga", "Yoga", "  YOGA  "]))
    assert [v["term"] for v in valid] == ["yoga"]
    assert len(errors) == 2


def test_the_row_limit_stops_the_scan():
    valid, errors = parse_keyword_workbook(book([f"kw {i}" for i in range(MAX_ROWS + 50)]))
    assert len(valid) == MAX_ROWS
    assert len(errors) == 1
    assert str(MAX_ROWS) in errors[0]["reason"]


# ── the insert the parsed rows feed into ──────────────────────────────

def test_the_bulk_insert_names_no_conflict_target():
    """ON CONFLICT (project_id, term) needs that exact unique index to exist.

    idx_keywords_project_term is optional DDL — a database that already holds
    duplicate terms rejects it at boot — so naming it made every import fail with
    InvalidColumnReference on precisely the installs that most needed the import
    to work. The bare form conflicts on whatever unique index is there.
    """
    import inspect

    from app.routers import projects

    # Comments only, stripped — the explanation above the statement names the
    # broken form on purpose.
    src = "\n".join(
        line for line in inspect.getsource(projects.bulk_import_keywords).splitlines()
        if not line.strip().startswith("#")
    )
    assert "ON CONFLICT DO NOTHING" in src
    assert "ON CONFLICT (project_id, term)" not in src
