"""How a rank becomes a row, a colour and a bullet in the report."""

import pytest

from app.services import report_document, report_google, report_pdf, report_service


# ── rank tone ─────────────────────────────────────────────────────────
# Deliberately compares the two ranks rather than reading rank_delta: breaking
# into the results from nowhere is the largest possible improvement, and falling
# out of them entirely is the largest possible decline, but both leave rank_delta
# as None. A delta-based check rendered the two most significant movements as
# "no change".

@pytest.mark.parametrize("prev,cur,expected", [
    (9, 4, "row-up"),        # moved up
    (4, 9, "row-down"),      # moved down
    (5, 5, ""),              # unchanged
    (None, 7, "row-up"),     # wasn't ranking, now is
    (7, None, "row-down"),   # was ranking, dropped out
    (None, None, ""),        # never ranked
])
def test_rank_tone(prev, cur, expected):
    assert report_pdf._rank_tone(prev, cur) == expected


# ── formatting ────────────────────────────────────────────────────────

def test_missing_rank_renders_as_an_em_dash():
    assert report_pdf._fmt_value("rank", None) == "—"


def test_rank_renders_with_a_hash():
    assert report_pdf._fmt_value("rank", 7) == "#7"


def test_a_negative_rank_delta_is_an_improvement():
    _, tone = report_pdf._fmt_delta("rank", -3)
    assert tone == "up"


def test_a_positive_rank_delta_is_a_decline():
    _, tone = report_pdf._fmt_delta("rank", 2)
    assert tone == "down"


def test_a_positive_count_delta_is_an_improvement():
    # The sign means the opposite for ranks and for counts; keep both directions
    # pinned so a shared helper can't quietly invert one of them.
    _, tone = report_pdf._fmt_delta("count", 100)
    assert tone == "up"


# ── period arithmetic ─────────────────────────────────────────────────

@pytest.mark.parametrize("period,expected", [
    ("2026-08", "2026-07"),
    ("2026-01", "2025-12"),
    ("2026-03", "2026-02"),
])
def test_previous_period(period, expected):
    assert report_google.previous_period(period) == expected


@pytest.mark.parametrize("cur,prev,expected", [
    (4, 9, -5),
    (9, 4, 5),
    (5, 5, 0),
    (None, 9, None),
    (4, None, None),
])
def test_delta_needs_both_sides(cur, prev, expected):
    assert report_service._delta(cur, prev) == expected


# ── the keyword table block ───────────────────────────────────────────

def _section(items):
    return {"month": "2026-08", "prev_month": "2026-07", "prev2_month": "2026-06", "items": items}


def _item(term, cur, prev, prev2=None):
    delta = report_service._delta(cur, prev)
    return {"term": term, "current_rank": cur, "previous_rank": prev,
            "previous2_rank": prev2, "rank_delta": delta}


def test_table_columns_when_no_keyword_has_two_months_of_history():
    block = report_document._keyword_table(
        _section([_item("yoga", 4, 9)]), True, None, "August 2026", "July 2026", "June 2026"
    )
    keys = [c["key"] for c in block["columns"]]
    # A prev2 column of nothing but em-dashes reads as missing data rather than
    # as no history, so it's only offered when something is actually in it.
    assert keys == ["term", "previous_rank", "current_rank"]


def test_table_offers_the_prev2_column_once_any_keyword_has_that_history():
    block = report_document._keyword_table(
        _section([_item("yoga", 4, 9), _item("meditation", 12, 11, 20)]),
        True, None, "August 2026", "July 2026", "June 2026",
    )
    keys = [c["key"] for c in block["columns"]]
    assert keys == ["term", "previous2_rank", "previous_rank", "current_rank"]


def test_table_is_marked_unavailable_when_there_are_no_keywords():
    block = report_document._keyword_table(
        None, False, "no keywords added for this project yet",
        "August 2026", "July 2026", "",
    )
    assert block["available"] is False
    assert block["rows"] == []
    assert block["unavailableReason"] == "no keywords added for this project yet"


def test_every_table_column_is_typed_as_a_rank_except_the_term():
    block = report_document._keyword_table(
        _section([_item("yoga", 4, 9, 20)]), True, None, "August 2026", "July 2026", "June 2026"
    )
    for col in block["columns"]:
        assert col["type"] == ("text" if col["key"] == "term" else "rank")


# ── achievements ──────────────────────────────────────────────────────

def test_achievements_lists_improvements_biggest_first():
    bullets, terms = report_document.achievement_bullets([
        _item("small win", 8, 9),        # -1
        _item("big win", 3, 20),         # -17
        _item("a decline", 15, 6),       # +9, not an achievement
        _item("unchanged", 5, 5),        # 0
    ])
    assert terms == ["big win", "small win"]
    assert "17 places" in bullets[0]
    assert "improved 1 place to" in bullets[1]      # singular, not "1 places"


def test_achievements_pairs_each_bullet_with_its_term():
    # The pairing is what lets the editor drop a bullet when its keyword is
    # excluded from the table. Without it there was no way to tell which bullet
    # belonged to which row, so an excluded keyword stayed named in Achievements.
    bullets, terms = report_document.achievement_bullets([_item("yoga", 3, 9)])
    assert len(bullets) == len(terms) == 1
    assert terms[0] == "yoga"
    assert "yoga" in bullets[0]


def test_achievements_caps_the_list():
    items = [_item(f"kw{i}", 1, 50 + i) for i in range(20)]
    bullets, terms = report_document.achievement_bullets(items)
    assert len(bullets) == len(terms) == report_document.ACHIEVEMENT_LIMIT


def test_achievements_ignores_keywords_with_an_incomplete_delta():
    # Entering or leaving the results has no numeric delta, so it can't be
    # described as "improved N places" — those belong to the table's colouring,
    # not to this list.
    bullets, terms = report_document.achievement_bullets([
        _item("new entry", 7, None),
        _item("dropped out", None, 7),
    ])
    assert bullets == []
    assert terms == []


def test_achievements_block_carries_the_pristine_auto_list():
    block = report_document._achievements(_section([_item("yoga", 3, 9)]), True, "August 2026")
    assert block["bullets"] == block["autoBullets"]
    assert block["autoBulletTerms"] == ["yoga"]


def test_achievements_block_falls_back_to_a_placeholder_paragraph():
    block = report_document._achievements(None, False, "August 2026")
    assert block["bullets"] == []
    assert block["paragraphs"] and "August 2026" in block["paragraphs"][0]


# ── the registry contract ─────────────────────────────────────────────

def test_every_advertised_field_can_actually_resolve():
    # The "/" insert menu is built from the registry manifest, and a field with
    # no BLOB_MAP entry appears in the menu and then resolves to nothing. Three
    # used to break this: ranks.keyword_rank plus keywords.current_rank and
    # previous_rank, all left behind by storage that no longer exists.
    from app.services import report_blobs, report_registry

    advertised = {f["name"] for f in report_registry.REPORT_FIELDS if not f["deferred"]}
    assert advertised <= set(report_blobs.BLOB_MAP), (
        f"advertised but unresolvable: {sorted(advertised - set(report_blobs.BLOB_MAP))}"
    )
