"""Parsing the keyword import workbook."""

import pytest
from openpyxl import Workbook

from app.services.excel_service import (
    MAX_ROWS,
    MAX_TERM_LEN,
    build_sample_workbook,
    parse_keyword_workbook,
)


def _workbook(rows):
    wb = Workbook()
    ws = wb.active
    ws.append(["Keyword"])
    for r in rows:
        ws.append([r])
    from io import BytesIO
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_terms_are_trimmed_and_lowercased():
    valid, errors = parse_keyword_workbook(_workbook(["  Online Yoga  ", "MEDITATION"]))
    assert [v["term"] for v in valid] == ["online yoga", "meditation"]
    assert errors == []


def test_the_header_row_is_skipped():
    valid, _ = parse_keyword_workbook(_workbook(["yoga"]))
    assert [v["term"] for v in valid] == ["yoga"]


def test_blank_rows_are_ignored_silently():
    valid, errors = parse_keyword_workbook(_workbook(["yoga", "", "   ", "meditation"]))
    assert [v["term"] for v in valid] == ["yoga", "meditation"]
    assert errors == []


def test_duplicates_within_the_file_are_reported_not_inserted():
    valid, errors = parse_keyword_workbook(_workbook(["yoga", "Yoga", "yoga "]))
    assert [v["term"] for v in valid] == ["yoga"]
    assert len(errors) == 2
    assert all("Duplicate" in e["reason"] for e in errors)


def test_the_templates_own_instruction_rows_are_skipped():
    # The generated template carries its notes in column A, so re-importing an
    # unmodified template must not create keywords out of the instructions.
    valid, _ = parse_keyword_workbook(
        _workbook(["yoga", "How to use this template:", "• Keep the header row."])
    )
    assert [v["term"] for v in valid] == ["yoga"]


def test_an_absurdly_long_cell_is_reported_not_inserted():
    valid, errors = parse_keyword_workbook(_workbook(["x" * (MAX_TERM_LEN + 1), "yoga"]))
    assert [v["term"] for v in valid] == ["yoga"]
    assert len(errors) == 1
    assert str(MAX_TERM_LEN) in errors[0]["reason"]


def test_the_row_limit_stops_the_parse():
    valid, errors = parse_keyword_workbook(_workbook([f"kw{i}" for i in range(MAX_ROWS + 50)]))
    assert len(valid) == MAX_ROWS
    assert len(errors) == 1
    assert str(MAX_ROWS) in errors[0]["reason"]


def test_a_file_that_isnt_a_workbook_raises():
    with pytest.raises(ValueError):
        parse_keyword_workbook(b"this is not a spreadsheet")


def test_the_sample_template_round_trips_through_the_parser():
    valid, _ = parse_keyword_workbook(build_sample_workbook())
    # The three example keywords survive; the notes below them don't become rows.
    assert len(valid) == 3


def test_the_sample_template_makes_no_promise_about_automatic_ranks():
    # It used to tell users the app "finds each keyword's current position
    # automatically the next time you run Check rankings" — a feature that does
    # not exist. Every rank in this app is typed in by hand.
    body = build_sample_workbook()
    from openpyxl import load_workbook
    from io import BytesIO

    ws = load_workbook(BytesIO(body)).active
    text = " ".join(
        str(c.value) for row in ws.iter_rows() for c in row if c.value is not None
    ).lower()
    assert "check rankings" not in text
    assert "automatically" not in text
    assert "by hand" in text
