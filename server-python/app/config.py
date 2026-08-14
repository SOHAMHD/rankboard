import os
from pathlib import Path

_env_file = Path(__file__).resolve().parent.parent / ".env"
if _env_file.exists():
    for _line in _env_file.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _key, _, _value = _line.partition("=")
            _value = _value.strip()
            for _i, _ch in enumerate(_value):
                if _ch == "#" and (_i == 0 or _value[_i - 1] in " \t"):
                    _value = _value[:_i]
                    break
            os.environ.setdefault(_key.strip(), _value.strip())

PORT = int(os.environ.get("PORT", 4000))

JWT_SECRET = os.environ.get("JWT_SECRET", "").strip()
if not JWT_SECRET:
    raise RuntimeError(
        "JWT_SECRET is not set. Set a long random value (32+ bytes) in the "
        "environment or server-python/.env before starting the server."
    )

APP_URL = os.environ.get("APP_URL", "http://localhost:5173")

AGENCY_NAME = os.environ.get("AGENCY_NAME", "InfyApp Development")

DEBUG = os.environ.get("DEBUG", "false").strip().lower() in {"1", "true", "yes", "on"}

CORS_ORIGINS = [o.strip() for o in os.environ.get("CORS_ORIGINS", APP_URL).split(",") if o.strip()]
BREVO_API_KEY = os.environ.get("BREVO_API_KEY", "")
EMAIL_FROM = os.environ.get("EMAIL_FROM", "SEO Dashboard <no-reply@example.com>")

#: Shared secret guarding POST /api/webhooks/brevo.
#:
#: Brevo has no request signing — it will POST whatever URL you give it, with no
#: proof the request came from Brevo. The URL itself is the credential, so the
#: secret is passed as ?token=… (or an X-Webhook-Token header) and compared with
#: secrets.compare_digest. Leave it unset and the endpoint refuses everything:
#: an open ingest would let anyone forge delivery and open events.
BREVO_WEBHOOK_SECRET = os.environ.get("BREVO_WEBHOOK_SECRET", "").strip()

SMTP_HOST = os.environ.get("SMTP_HOST", "").strip()
SMTP_PORT = int(os.environ.get("SMTP_PORT", 587))
SMTP_USER = os.environ.get("SMTP_USER", "").strip()
SMTP_PASS = os.environ.get("SMTP_PASS", "")
SMTP_SECURE = os.environ.get("SMTP_SECURE", "starttls").strip().lower()

MOZ_API_TOKEN = os.environ.get("MOZ_API_TOKEN", "")
MOZ_ACCESS_ID = os.environ.get("MOZ_ACCESS_ID", "").strip()
MOZ_SECRET_KEY = os.environ.get("MOZ_SECRET_KEY", "").strip()

# DATAFORSEO_LOGIN / _PASSWORD / _BASE were read here for
# scripts/import_locations.py, which refreshed the `locations` table from
# DataForSEO's geo-target list. That script and that table are gone with the
# location feature, and nothing else in the app ever called DataForSEO — keyword
# ranks are entered by hand (see keyword_rank_service). The credentials can come
# out of .env too.

#: Path to the GA4 / Search Console service-account key, or the key's JSON itself.
#:
#: Empty by default. It used to default to a specific key filename checked into
#: one developer's working copy, so an unconfigured server looked configured: the
#: providers passed their `if not GOOGLE_SERVICE_ACCOUNT_JSON` guard and then
#: failed deeper down with a file-not-found that reads like a broken credential.
#: Empty makes them report "not configured on the server", which is the truth.
GOOGLE_SERVICE_ACCOUNT_JSON = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")

REPORT_ASSET_DIR = os.environ.get(
    "REPORT_ASSET_DIR",
    str(Path(__file__).resolve().parent.parent / "assets" / "public"),
)
REPORT_ASSET_BASE_URL = os.environ.get(
    "REPORT_ASSET_BASE_URL", f"{APP_URL.rstrip('/')}/report-covers"
).rstrip("/")

EMAIL_LOGO_URL = os.environ.get(
    "EMAIL_LOGO_URL", f"{APP_URL.rstrip('/')}/infapp-logo.png"
)

SUPPORT_EMAIL = os.environ.get("SUPPORT_EMAIL", "info@infyappdevelopment.com")
UNSUBSCRIBE_URL = os.environ.get(
    "UNSUBSCRIBE_URL", "https://infyappdevelopment.com/unsubscribe"
)
