import base64
import json
import logging
import urllib.error
import urllib.request
import uuid

from ..config import MOZ_ACCESS_ID, MOZ_SECRET_KEY, MOZ_API_TOKEN
from .response_cache import cached

logger = logging.getLogger(__name__)

LINKS_API_URL = "https://lsapi.seomoz.com/v2/url_metrics"
JSONRPC_URL = "https://api.moz.com/jsonrpc"
_TIMEOUT = 20


class MozApiError(Exception):
    pass


def normalize_domain(raw):
    d = (raw or "").strip().lower()
    d = d.split("://")[-1]
    d = d.split("/")[0]
    d = d.split("?")[0]
    if d.startswith("www."):
        d = d[4:]
    return d


def _request(url, headers):
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
    token = base64.b64encode(f"{MOZ_ACCESS_ID}:{MOZ_SECRET_KEY}".encode()).decode()
    body = _request(LINKS_API_URL, {"Authorization": f"Basic {token}"})({"targets": [normalized]})
    results = (body or {}).get("results") or []
    return _map_metrics(normalized, results[0] if results else {}, {"url_metrics": body})


def _fetch_jsonrpc(normalized):
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


@cached("fetch_moz_metrics")
def fetch_moz_metrics(domain):
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
