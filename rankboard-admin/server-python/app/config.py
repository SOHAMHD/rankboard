"""Central config. In production these MUST come from environment
variables (never commit real secrets). The fallbacks exist only so
`uvicorn app.main:app` works out of the box."""
import os
from pathlib import Path

# ── Optional .env support ────────────────────────────────────────────
# If server-python/.env exists, its KEY=VALUE lines are loaded into the
# environment (without overriding variables that are already set).
# This keeps secrets out of code: .env stays on your machine only —
# never commit it to git (add ".env" to .gitignore).
_env_file = Path(__file__).resolve().parent.parent / ".env"
if _env_file.exists():
    for _line in _env_file.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _key, _, _value = _line.partition("=")
            _value = _value.strip()
            # Strip a trailing inline comment: a '#' that follows whitespace
            # starts a comment (so `CODE=2356  # India` parses as 2356). A '#'
            # NOT preceded by whitespace is kept (e.g. inside a password).
            for _i, _ch in enumerate(_value):
                if _ch == "#" and (_i == 0 or _value[_i - 1] in " \t"):
                    _value = _value[:_i]
                    break
            os.environ.setdefault(_key.strip(), _value.strip())

PORT = int(os.environ.get("PORT", 4000))
JWT_SECRET = os.environ.get("JWT_SECRET", "dev-secret-change-me-in-production")
APP_URL = os.environ.get("APP_URL", "http://localhost:5173")  # link in invite emails
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
EMAIL_FROM = os.environ.get("EMAIL_FROM", "RankBoard <onboarding@resend.dev>")

# ── Moz API (domain Authority overview) ─────────────────────────────
# The base64 API token copied straight from the Moz API dashboard, sent in the
# `x-moz-token` header. It decodes to the legacy "Access ID:Secret Key" pair —
# that's expected: post-2024 migration, that base64 string IS the modern token
# (no HMAC signing needed). Leave empty to disable the Authority panel; the
# refresh endpoint then returns a clear "not configured" message instead of
# crashing. Quota is tiny, so Moz is only ever called on an explicit refresh.
MOZ_API_TOKEN = os.environ.get("MOZ_API_TOKEN", "")

# ── Automatic rank checks (DataForSEO) ──────────────────────────────
# Leave LOGIN/PASSWORD empty for free SIMULATED mode (random-walk
# numbers, clearly labeled). Set both to do real Google lookups.
DATAFORSEO_LOGIN = os.environ.get("DATAFORSEO_LOGIN", "")
DATAFORSEO_PASSWORD = os.environ.get("DATAFORSEO_PASSWORD", "")
# Point at https://sandbox.dataforseo.com to test against mock data for free.
DATAFORSEO_BASE = os.environ.get("DATAFORSEO_BASE", "https://api.dataforseo.com")
RANK_LOCATION_CODE = int(os.environ.get("RANK_LOCATION_CODE", 2356))  # 2356 = India (2000 + ISO numeric)
RANK_LANGUAGE = os.environ.get("RANK_LANGUAGE", "en")
# Depth = how deep into Google we look. Billing is per page of 10
# results, so depth 30 = 3 pages. Deeper costs more per check.
RANK_CHECK_DEPTH = int(os.environ.get("RANK_CHECK_DEPTH", 30))

# ── Google Analytics 4 (GA4) traffic ────────────────────────────────
# Path to the Google service-account JSON key file. Leave empty to
# disable the GA4 traffic panel (the provider returns a clear
# "not configured" result instead of crashing). The same service
# account is reused for every project; each project stores its own
# GA4 property ID in the database.
GOOGLE_SERVICE_ACCOUNT_JSON = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "seo-dashboard-499607-25e8ccaf16ad.json")
