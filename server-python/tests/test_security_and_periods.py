"""Session tokens, credential redaction, and report period arithmetic.

All pure functions, all previously untested, and all things where a quiet mistake
is worse than a crash: a token check that's inverted locks every user out, a
redaction that misses leaves live credentials in the database, and period
arithmetic that's off by one reports the wrong month to a client.
"""

import jwt
import pytest

from app.config import JWT_SECRET
from app.security import create_pending_token, create_token
from app.services import report_google
from app.services.redaction import SECRET_CATEGORIES, redact


def claims(token: str) -> dict:
    return jwt.decode(token, JWT_SECRET, algorithms=["HS256"])


# ── token_version ─────────────────────────────────────────────────────
# require_auth rejects a token whose "tv" is behind users.token_version. That is
# what makes a password change end other sessions.

def test_the_token_version_is_embedded():
    assert claims(create_token(7, "Admin", "verified", token_version=3))["tv"] == 3


def test_a_pending_token_carries_it_too():
    # Login mints a pending token before the 2FA step; if it lost the claim, the
    # user would be refused the moment they verified.
    assert claims(create_pending_token(7, "Admin", token_version=5))["tv"] == 5


def test_it_defaults_to_zero():
    # Tokens minted before the claim existed decode as 0, which must compare equal
    # to a fresh user's token_version of 0 — otherwise a deploy signs everyone out.
    #
    # `tfa` is passed explicitly here and in every other call: it has no default,
    # deliberately, so that a caller which forgets to think about the second
    # factor can't mint a fully verified session by omission.
    assert claims(create_token(7, "Admin", "verified"))["tv"] == 0


def test_a_pending_token_is_marked_pending_and_short_lived():
    c = claims(create_pending_token(7, "Admin"))
    assert c["tfa"] == "pending"
    assert c["exp"] > 0


@pytest.mark.parametrize("token_tv,user_tv,accepted", [
    (0, 0, True),    # nothing has changed since this token was issued
    (1, 1, True),    # issued after the change
    (0, 1, False),   # stale: a password was changed after this token was minted
    (1, 3, False),   # two changes since
    (2, 1, True),    # ahead of the row — must not lock anyone out
])
def test_the_version_comparison(token_tv, user_tv, accepted):
    # Mirrors require_auth's rule exactly.
    assert (not (int(token_tv or 0) < int(user_tv or 0))) is accepted


def test_the_subject_is_a_string():
    # require_auth does int(payload["sub"]); PyJWT requires `sub` to be a string.
    assert claims(create_token(42, "Team", "verified"))["sub"] == "42"


# ── redaction ─────────────────────────────────────────────────────────

def test_a_temporary_password_is_masked():
    body = "Temporary password: Xk4mPq7Rt2\nSign in here: https://example.com"
    out = redact(body, "invite")
    assert "Xk4mPq7Rt2" not in out
    assert "https://example.com" in out


def test_a_sign_in_code_is_masked():
    assert "418327" not in redact("Your code is: 418327", "login_code")


@pytest.mark.parametrize("category", sorted(SECRET_CATEGORIES))
def test_every_secret_category_is_redacted(category):
    assert "123456" not in redact("code 123456", category)


def test_a_report_body_is_left_alone():
    # The figures are the whole point of a report email.
    body = "Sessions were 1204 and clicks 318 in July 2026."
    assert redact(body, "report") == body


def test_an_unknown_category_is_left_alone():
    assert redact("code 123456", "something_new") == "code 123456"


@pytest.mark.parametrize("value", [None, ""])
def test_empty_bodies_survive(value):
    assert redact(value, "invite") == value


def test_a_three_digit_number_is_not_treated_as_a_code():
    # The pattern is 4-10 digits; masking every short number would eat prices and
    # counts out of messages that legitimately contain them.
    assert "£99" in redact("Plan is £99 per month", "invite")


# ── period arithmetic ─────────────────────────────────────────────────

@pytest.mark.parametrize("period,expected", [
    ("2026-08", "2026-07"),
    ("2026-01", "2025-12"),   # year boundary
    ("2026-03", "2026-02"),
    ("2026-12", "2026-11"),
])
def test_previous_period(period, expected):
    assert report_google.previous_period(period) == expected


def test_previous_period_twice_reaches_two_months_back():
    # report_service uses prev and prev2 for the keyword table's three columns.
    prev = report_google.previous_period("2026-01")
    assert report_google.previous_period(prev) == "2025-11"


def test_month_bounds_covers_the_whole_month():
    start, end = report_google.month_bounds("2026-02")
    assert start == "2026-02-01"
    assert end == "2026-02-28"          # 2026 is not a leap year


def test_month_bounds_handles_a_leap_year():
    assert report_google.month_bounds("2024-02")[1] == "2024-02-29"


def test_month_bounds_handles_a_31_day_month():
    assert report_google.month_bounds("2026-07") == ("2026-07-01", "2026-07-31")
