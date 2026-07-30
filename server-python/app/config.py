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

# Signing key for auth tokens. REQUIRED — no fallback. An empty or missing
# value is a hard startup error (fail fast) rather than a silent insecure
# default that would let anyone forge tokens. Set a long random value in the
# environment (or server-python/.env) before starting the server.
JWT_SECRET = os.environ.get("JWT_SECRET", "").strip()
if not JWT_SECRET:
    raise RuntimeError(
        "JWT_SECRET is not set. Set a long random value (32+ bytes) in the "
        "environment or server-python/.env before starting the server."
    )

APP_URL = os.environ.get("APP_URL", "http://localhost:5173")  # link in invite emails

# Interactive API docs (/docs, /redoc, /openapi.json) expose the full API
# surface, so they are OFF unless DEBUG is explicitly enabled. Keep DEBUG
# false in production.
DEBUG = os.environ.get("DEBUG", "false").strip().lower() in {"1", "true", "yes", "on"}

# Browser CORS allowlist — comma-separated origins, defaulting to the frontend
# (APP_URL). NEVER "*", especially with credentials.
CORS_ORIGINS = [o.strip() for o in os.environ.get("CORS_ORIGINS", APP_URL).split(",") if o.strip()]
# Brevo (formerly Sendinblue) transactional email — the API key from
# Brevo dashboard → SMTP & API → API Keys (starts with "xkeysib-").
BREVO_API_KEY = os.environ.get("BREVO_API_KEY", "")
# The From address. With Brevo the address (or its domain) must be a
# verified sender/domain in your Brevo account, or the send is rejected.
EMAIL_FROM = os.environ.get("EMAIL_FROM", "SEO Dashboard <no-reply@example.com>")

# ── SMTP transport (preferred when configured) ──────────────────────
# Set SMTP_HOST to send real email through your own mail server / Gmail /
# any SMTP provider (including Brevo's SMTP relay, smtp-relay.brevo.com:587)
# — this takes priority over the Brevo API. Leave SMTP_HOST empty to fall
# back to the Brevo API, then to the dev outbox. SMTP_SECURE: "ssl"
# (implicit TLS, usually port 465), "starttls"/"tls" (upgrade on port 587,
# the default), or "none".
SMTP_HOST = os.environ.get("SMTP_HOST", "").strip()
SMTP_PORT = int(os.environ.get("SMTP_PORT", 587))
SMTP_USER = os.environ.get("SMTP_USER", "").strip()
SMTP_PASS = os.environ.get("SMTP_PASS", "")
SMTP_SECURE = os.environ.get("SMTP_SECURE", "starttls").strip().lower()

# ── Moz API (domain Authority overview) ─────────────────────────────
# The base64 API token copied straight from the Moz API dashboard, sent in the
# `x-moz-token` header. It decodes to the legacy "Access ID:Secret Key" pair —
# that's expected: post-2024 migration, that base64 string IS the modern token
# (no HMAC signing needed). Leave empty to disable the Authority panel; the
# refresh endpoint then returns a clear "not configured" message instead of
# crashing. Quota is tiny, so Moz is only ever called on an explicit refresh.
MOZ_API_TOKEN = os.environ.get("MOZ_API_TOKEN", "")
# Moz Links API v2 (legacy-style) credentials: Access ID + Secret Key, used
# with HTTP Basic auth. Preferred when set; falls back to MOZ_API_TOKEN.
MOZ_ACCESS_ID = os.environ.get("MOZ_ACCESS_ID", "").strip()
MOZ_SECRET_KEY = os.environ.get("MOZ_SECRET_KEY", "").strip()

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

# ── Publicly served report assets (email cover thumbnails) ──────────
# The monthly report email embeds a thumbnail of page 1 of the report PDF.
# Mail clients fetch images over plain HTTPS with no cookies and no auth
# headers, so the file MUST live in a publicly reachable directory and be
# referenced by an ABSOLUTE url. REPORT_ASSET_DIR is where the app writes the
# PNG; REPORT_ASSET_BASE_URL is the public url prefix serving that same
# directory. Filenames are random tokens, so the urls are unguessable.
#
# On the cPanel host these point into public_html, e.g.
#   REPORT_ASSET_DIR=/home/<cpuser>/public_html/report-covers
#   REPORT_ASSET_BASE_URL=https://your-domain/report-covers
REPORT_ASSET_DIR = os.environ.get(
    "REPORT_ASSET_DIR",
    str(Path(__file__).resolve().parent.parent / "assets" / "public"),
)
REPORT_ASSET_BASE_URL = os.environ.get(
    "REPORT_ASSET_BASE_URL", f"{APP_URL.rstrip('/')}/report-covers"
).rstrip("/")

# Absolute url of the logo in the report email's header bar. Publicly
# reachable for the same reason as the cover thumbnail.
EMAIL_LOGO_URL = os.environ.get(
    "EMAIL_LOGO_URL", f"{APP_URL.rstrip('/')}/infapp-logo.png"
)

# Values rendered into the report email's support line and legal strip.
SUPPORT_EMAIL = os.environ.get("SUPPORT_EMAIL", "info@infyappdevelopment.com")
UNSUBSCRIBE_URL = os.environ.get(
    "UNSUBSCRIBE_URL", "https://infyappdevelopment.com/unsubscribe"
)