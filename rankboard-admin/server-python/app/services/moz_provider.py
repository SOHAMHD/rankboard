"""MOZ PROVIDER — domain Authority & link metrics from the Moz API.

The modern Moz API is JSON-RPC 2.0 over a SINGLE endpoint
(https://api.moz.com/jsonrpc), authenticated with an `x-moz-token` header —
NOT the legacy Access ID / Secret Key HMAC. The token comes from
config.MOZ_API_TOKEN, loaded from .env the same way DataForSEO / Resend are.

Moz's quota is tiny, so this is NEVER called on page load — only on an explicit
refresh. fetch_moz_metrics() is the single entry point so a future scheduled
refresh can reuse identical logic: it normalizes the domain, makes two POSTs
(site.metrics.fetch + site.ranking_keywords.count), and maps the result into a
flat dict, defensively — any missing field becomes None rather than raising. On
an HTTP error, an auth failure (401/403), a transport error, or a top-level
JSON-RPC error it raises MozApiError with a readable message, so the endpoint
can return a friendly 502 instead of a 500 crash.

Uses urllib (no extra dependency), matching email_service / rank_provider.
"""
import json
import logging
import urllib.error
import urllib.request

from ..config import MOZ_API_TOKEN

logger = logging.getLogger(__name__)

MOZ_API_URL = "https://api.moz.com/jsonrpc"
_TIMEOUT = 20  # seconds — short enough to fail fast when Moz is unreachable


class MozApiError(Exception):
    """Raised on any Moz API failure (HTTP error, auth failure, transport
    error, or a top-level JSON-RPC error) with a human-readable message."""


def normalize_domain(raw: str | None) -> str:
    """ "https://www.InfyApp.com/about?x=1" -> "infyapp.com".

    Strip the scheme, drop "www.", and strip any path/query → the bare root
    domain Moz expects. Returns "" for empty/garbage input so the caller can
    decide there's nothing to look up."""
    d = (raw or "").strip().lower()
    d = d.split("://")[-1]   # drop scheme
    d = d.split("/")[0]      # drop path
    d = d.split("?")[0]      # drop query (defensive — the path split usually covers it)
    if d.startswith("www."):
        d = d[4:]
    return d


def _rpc(method: str, data: dict) -> dict:
    """POST one JSON-RPC call to Moz and return the FULL parsed response body.

    Translates every failure mode into MozApiError: a missing token, an HTTP
    error (401/403 auth, other 4xx/5xx), a transport error, or a top-level
    JSON-RPC `error` object in the body (which arrives with HTTP 200)."""
    if not MOZ_API_TOKEN:
        raise MozApiError("Moz is not configured on the server (set MOZ_API_TOKEN).")

    payload = {"jsonrpc": "2.0", "id": "1", "method": method, "params": {"data": data}}
    req = urllib.request.Request(
        MOZ_API_URL,
        data=json.dumps(payload).encode(),
        headers={"x-moz-token": MOZ_API_TOKEN, "Content-Type": "application/json"},
        method="POST",
    )

    # TEMP DEBUG — confirm the token is loaded and looks right WITHOUT ever
    # logging the secret itself (only its length + first 6 / last 4 chars).
    logger.warning(
        "Moz %s: token len=%d prefix=%r suffix=%r",
        method, len(MOZ_API_TOKEN), MOZ_API_TOKEN[:6], MOZ_API_TOKEN[-4:],
    )

    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as res:
            raw_body = res.read()
            # TEMP DEBUG — urllib only returns here for 2xx, but log defensively
            # if the status is anything other than 200.
            if res.status != 200:
                logger.warning(
                    "Moz %s non-200 response: status=%s body=%s",
                    method, res.status, raw_body.decode(errors="replace")[:1000],
                )
            body = json.loads(raw_body)
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode(errors="replace")
        except Exception:
            pass
        # TEMP DEBUG — log the failing status + response body (truncated; the
        # token is never included here).
        logger.warning("Moz %s error response: status=%s body=%s", method, exc.code, detail[:1000])
        if exc.code in (401, 403):
            raise MozApiError("Moz authentication failed — check MOZ_API_TOKEN.") from exc
        raise MozApiError(f"Moz API returned HTTP {exc.code}. {detail[:200]}".strip()) from exc
    except urllib.error.URLError as exc:
        raise MozApiError(f"Could not reach the Moz API: {exc.reason}") from exc
    except Exception as exc:  # malformed JSON, etc.
        raise MozApiError(f"Moz API request failed: {exc}") from exc

    # A JSON-RPC error object means the call was rejected even with HTTP 200.
    if isinstance(body, dict) and body.get("error"):
        err = body["error"]
        msg = err.get("message") if isinstance(err, dict) else str(err)
        raise MozApiError(f"Moz API error: {msg}")

    return body if isinstance(body, dict) else {}


def fetch_moz_metrics(domain: str) -> dict:
    """Fetch Moz authority metrics for a domain. The ONE entry point, so a
    future scheduled refresh reuses identical logic.

    Returns a flat dict:
        {
          "domain": "<normalized root domain>",
          "domain_authority": int | None,
          "linking_domains":  int | None,
          "inbound_links":    int | None,
          "ranking_keywords": int | None,
          "spam_score":       float | None,
          "raw": {"site_metrics": <full body>, "ranking_keywords": <full body>},
        }

    Any field Moz omits maps to None rather than raising. Both full JSON
    responses are captured under "raw" (stored as raw_json for debugging).
    Raises MozApiError on HTTP/auth/transport failures or a JSON-RPC error."""
    normalized = normalize_domain(domain)
    if not normalized:
        raise MozApiError("This project has no domain to look up on Moz.")

    raw: dict = {}

    # ── Call 1: site metrics (DA, linking domains, inbound links, spam) ──
    body1 = _rpc("site.metrics.fetch", {"site_query": {"query": normalized, "scope": "root_domain"}})
    raw["site_metrics"] = body1
    sm = (body1.get("result") or {}).get("site_metrics") or {}

    domain_authority = sm.get("domain_authority")
    # Prefer root-domain link counts; fall back to subdomain counts when absent.
    linking_domains = sm.get("root_domains_to_root_domain") or sm.get("root_domains_to_subdomain")
    inbound_links = sm.get("external_pages_to_root_domain") or sm.get("external_pages_to_subdomain")
    spam_score = sm.get("spam_score")

    # ── Call 2: ranking keyword count ──
    body2 = _rpc(
        "site.ranking_keywords.count",
        {"target_query": {"query": normalized, "scope": "root_domain", "locale": "en-US"}},
    )
    raw["ranking_keywords"] = body2
    r2 = body2.get("result") or {}
    ranking_keywords = r2.get("ranking_keywords_count") or r2.get("count")

    return {
        "domain": normalized,
        "domain_authority": domain_authority,
        "linking_domains": linking_domains,
        "inbound_links": inbound_links,
        "ranking_keywords": ranking_keywords,
        "spam_score": spam_score,
        "raw": raw,
    }
