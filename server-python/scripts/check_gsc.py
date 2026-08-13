"""Show which Search Console properties the service account can actually read.

    python -m scripts.check_gsc

Read-only. Prints the service-account email, every property Google will accept
from it, and each project's configured gsc_site_url side by side — which is the
only reliable way to tell "not shared with the service account" apart from
"shared, but the string doesn't match the property".

The two failure modes look identical in the UI and have completely different
fixes:

  403  the service account is not a user on that property -> add it in Search
       Console (Settings -> Users and permissions), Full or Restricted
  400  the property exists but the string is wrong -> a domain property is
       `sc-domain:example.com`; a URL-prefix property is `https://example.com/`,
       trailing slash included, and http/https and www/non-www are all distinct
       properties
"""

import json
import sys

from app.config import GOOGLE_SERVICE_ACCOUNT_JSON
from app.db import db_session
from app.services.search_console_provider import _build_service, default_range


def service_account_email() -> str:
    raw = GOOGLE_SERVICE_ACCOUNT_JSON
    if not raw:
        return "(no key configured)"
    try:
        info = json.loads(raw) if raw.lstrip().startswith("{") else json.load(open(raw))
        return info.get("client_email") or "(key has no client_email)"
    except Exception as exc:
        return f"(could not read key: {exc})"


def main() -> int:
    print(f"service account: {service_account_email()}\n")

    service, err = _build_service()
    if err:
        print(f"FAILED to build the Search Console client: {err}")
        return 1

    try:
        entries = service.sites().list().execute().get("siteEntry", []) or []
    except Exception as exc:
        print(f"sites().list() failed: {exc}")
        return 1

    visible = {e.get("siteUrl", "") for e in entries}

    print(f"properties visible to the service account: {len(entries)}")
    if not entries:
        print(
            "  none — the service account has not been added to any property.\n"
            "  In Search Console: pick the property, Settings -> Users and\n"
            "  permissions -> Add user, paste the address above."
        )
    for e in sorted(entries, key=lambda e: e.get("siteUrl", "")):
        print(f"  {e.get('siteUrl')}   [{e.get('permissionLevel')}]")

    with db_session() as db:
        projects = db.execute(
            "SELECT id, name, gsc_site_url FROM projects ORDER BY id"
        ).fetchall()

    print("\nprojects:")
    problems = 0
    for p in projects:
        configured = p["gsc_site_url"]
        if not configured:
            print(f"  #{p['id']} {p['name']}: (no property set)")
            continue
        if configured in visible:
            verdict = "OK"
        else:
            verdict = "NOT VISIBLE — will fail"
            problems += 1
        print(f"  #{p['id']} {p['name']}: {configured!r} -> {verdict}")
        if verdict != "OK":
            near = [v for v in visible if configured.strip("/ ").endswith(v.strip("/ ").split("//")[-1].strip("/"))]
            for n in near:
                print(f"        did you mean: {n!r}")

    # A live read proves permission end to end; sites().list() alone doesn't.
    ok = [p for p in projects if p["gsc_site_url"] in visible]
    if ok:
        target = ok[0]["gsc_site_url"]
        start, end = default_range(28)
        print(f"\ntest query on {target!r} for {start}..{end}:")
        try:
            res = service.searchanalytics().query(
                siteUrl=target,
                body={"startDate": start, "endDate": end, "dataState": "all"},
            ).execute()
            rows = res.get("rows", []) or []
            if rows:
                r = rows[0]
                print(
                    f"  clicks={int(r.get('clicks', 0))} "
                    f"impressions={int(r.get('impressions', 0))}"
                )
            else:
                print(
                    "  the query succeeded but returned no rows — permission is fine,\n"
                    "  this property genuinely has no search data for that window."
                )
        except Exception as exc:
            print(f"  FAILED: {exc}")
            problems += 1

    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
