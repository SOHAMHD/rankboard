"""MOZ PROVIDER - domain Authority & link metrics from the Moz API.

This account has BOTH kinds of Moz credentials, so the provider supports both
and picks automatically:

  1. Links API v2 (Access ID + Secret Key) - HTTP Basic auth, the preferred path
     when MOZ_ACCESS_ID + MOZ_SECRET_KEY are set:
        POST https://lsapi.seomoz.com/v2/url_metrics
        Authorization: Basic base64("<ACCESS_ID>:<SECRET_KEY>")
        body: {"targets": ["<root domain>"]}

  2. New JSON-RPC API (single token) - x-moz-token header, used when only
     MOZ_API_TOKEN is set:
        POST https://api.moz.com/jsonrpc  (method data.site.metrics.fetch)

Credentials load from config (from .env). Quota is tiny, so this is NEVER called
on page load - only on an explicit refresh. fetch_moz_metrics() is the single
entry point and maps whichever response into the SAME flat dict defensively - any
missing field becomes None. On HTTP/auth/transport failure it raises MozApiError
with a readable message so the endpoint returns a friendly 502, never a 500.

Uses urllib (no extra dependency), matching email_service / rank_provider.
"""
import base64
import json
import logging
import urllib.error
import urllib.request
import uuid

from ..config import MOZ_ACCESS_ID, MOZ_SECRET_KEY, MOZ_API_TOKEN

logger = logging.getLogger(__name__)

LINKS_API_URL = "https://lsapi.seomoz.com/v2/url_metrics"
JSONRPC_URL = "https://api.moz.com/jsonrpc"
_TIMEOUT = 20  # seconds - fail fast when Moz is unreachable


class MozApiError(Exception):
    """Raised on any Moz API failure with a human-readable message."""


def normalize_domain(raw):
    """ "https://www.InfyApp.com/about?x=1" -> "infyapp.com". Strip scheme, drop
    "www.", strip path/query. Returns "" for empty/garbage input."""
    d = (raw or "").strip().lower()
    d = d.split("://")[-1]
    d = d.split("/")[0]
    d = d.split("?")[0]
    if d.startswith("www."):
        d = d[4:]
    return d


def _request(url, headers):
    """POST helper returning parsed JSON; classifies failures into MozApiError."""
    def do(body):
        req = urllib.request.Request(
            url, data=json.dumps(body).encode(),
            headers={**headers, "Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as res:
                raw = res.read()
                if res.status != 200:
                    logger.warning("Moz non-200: status=%s body=%s",
                                   res.status, raw.decode(errors="replace")[:1000])
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode(errors="replace")
            except Exception:
                pass
            logger.warning("Moz error: status=%s body=%s", exc.code, detail[:1000])
            if exc.code in (401, 403):
                raise MozApiError("Moz authentication failed - check your Moz credentials.") from exc
            raise MozApiError(f"Moz API returned HTTP {exc.code}. {detail[:200]}".strip()) from exc
        except urllib.error.URLError as exc:
            raise MozApiError(f"Could not reach the Moz API: {exc.reason}") from exc
        except Exception as exc:
            raise MozApiError(f"Moz API request failed: {exc}") from exc
    return do


def _map_metrics(normalized, m, raw):
    """Map either API's metric object into the shared flat dict."""
    linking_domains = (m.get("root_domains_to_root_domain")
                       or m.get("root_domains_to_subdomain")
                       or m.get("linking_root_domains"))
    inbound_links = (m.get("external_pages_to_root_domain")
                     or m.get("external_pages_to_subdomain")
                     or m.get("pages_to_root_domain")
                     or m.get("external_links"))
    return {
        "domain": normalized,
        "domain_authority": m.get("domain_authority"),
        "linking_domains": linking_domains,
        "inbound_links": inbound_links,
        "spam_score": m.get("spam_score"),
        "raw": raw,
    }


def _fetch_links_api(normalized):
    """Moz Links API v2 (Access ID + Secret Key, Basic auth)."""
    token = base64.b64encode(f"{MOZ_ACCESS_ID}:{MOZ_SECRET_KEY}".encode()).decode()
    body = _request(LINKS_API_URL, {"Authorization": f"Basic {token}"})({"targets": [normalized]})
    results = (body or {}).get("results") or []
    return _map_metrics(normalized, results[0] if results else {}, {"url_metrics": body})


def _fetch_jsonrpc(normalized):
    """New Moz JSON-RPC API (single x-moz-token). Request id must be >= 24 chars."""
    payload_body = {"site_query": {"query": normalized, "scope": "domain"}}
    call = _request(JSONRPC_URL, {"x-moz-token": MOZ_API_TOKEN})
    body = call({"jsonrpc": "2.0", "id": uuid.uuid4().hex,
                 "method": "data.site.metrics.fetch", "params": {"data": payload_body}})
    if isinstance(body, dict) and body.get("error"):
        err = body["error"]
        msg = err.get("message") if isinstance(err, dict) else str(err)
        raise MozApiError(f"Moz API error: {msg}")
    sm = (body.get("result") or {}).get("site_metrics") or {}
    return _map_metrics(normalized, sm, {"site_metrics": body})


def fetch_moz_metrics(domain):
    """Fetch Moz authority metrics for a domain, choosing the auth scheme by which
    credentials are configured. Returns the shared flat dict; raises MozApiError
    on failure."""
    normalized = normalize_domain(domain)
    if not normalized:
        raise MozApiError("This project has no domain to look up on Moz.")
    if MOZ_ACCESS_ID and MOZ_SECRET_KEY:
        return _fetch_links_api(normalized)
    if MOZ_API_TOKEN:
        return _fetch_jsonrpc(normalized)
    raise MozApiError(
        "Moz is not configured on the server (set MOZ_ACCESS_ID + MOZ_SECRET_KEY, "
        "or MOZ_API_TOKEN).")
