"""Reconcile this app's GA4 and Search Console figures against the Google UIs.

Prints every number the app computes next to the exact report and column it should
match, so a mismatch identifies itself instead of needing a screenshot comparison.

Usage
-----
    cd server-python
    python verify_google_data.py                        # project 16, last full month
    python verify_google_data.py --project 16
    python verify_google_data.py --project 16 --start 2026-07-01 --end 2026-07-31
    python verify_google_data.py --all                  # every active project

Every query bypasses the response cache, so figures are live.
"""

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app import db  # noqa: E402
from app.services import search_console_provider as scp  # noqa: E402
from app.services.analytics_provider import run_custom_report  # noqa: E402


def fmt_secs(v) -> str:
    try:
        t = int(round(float(v)))
    except (TypeError, ValueError):
        return "—"
    return f"{t // 60}m {t % 60}s" if t >= 60 else f"{t}s"


def num(v) -> str:
    try:
        return f"{int(round(float(v))):,}"
    except (TypeError, ValueError):
        return "—"


def hdr(text: str) -> None:
    print(f"\n{text}")
    print("-" * len(text))


def check_ga4(property_id: str, start: str, end: str) -> None:
    hdr("GA4 — compare against: Reports > Acquisition > User acquisition")
    print("   dimension: First user primary channel group")
    print(f"   date range: {start} -> {end}\n")

    r = run_custom_report(
        property_id, start, end,
        ["firstUserPrimaryChannelGroup"],
        ["totalUsers", "activeUsers", "newUsers", "sessions",
         "userEngagementDuration", "eventCount", "keyEvents"],
        limit=25, refresh=True,
    )
    if isinstance(r, dict) and r.get("error"):
        print(f"   FAILED: {r['error']}")
        return

    t = r.get("totals") or {}
    dur = float(t.get("userEngagementDuration") or 0)
    act = float(t.get("activeUsers") or 0)
    ses = float(t.get("sessions") or 0)

    print(f"   {'app value':>14}   GA4 column to compare")
    rows = [
        (num(t.get("totalUsers")),  "Total users"),
        (num(t.get("activeUsers")), "Active users"),
        (num(t.get("newUsers")),    "New users"),
        (num(t.get("sessions")),    "Sessions  (Traffic acquisition report)"),
        (num(t.get("eventCount")),  "Event count"),
        (num(t.get("keyEvents")),   "Key events"),
        (fmt_secs(dur / act if act else 0), "Average engagement time per active user"),
        (fmt_secs(dur / ses if ses else 0), "Average engagement time per session"),
    ]
    for value, label in rows:
        print(f"   {value:>14}   {label}")

    print("\n   Per-channel (app | GA4 should match Total users):")
    for row in (r.get("rows") or [])[:8]:
        m = row.get("metrics") or {}
        name = (row.get("dims") or ["?"])[0]
        print(f"     {str(name)[:24]:24} {num(m.get('totalUsers')):>9}")

    print("\n   NOTE: rows sum to MORE than the total for user metrics — GA4")
    print("   de-duplicates people across channels. That is correct, not a bug.")


def check_gsc(site_url: str, start: str, end: str) -> None:
    hdr("Search Console — compare against: Performance > Search results")
    print(f"   property: {site_url}")
    print(f"   date range: {start} -> {end}")
    print(f"   GSC's own last available date is about {scp.gsc_last_available_date()}")
    print("   search type: Web    (GSC UI default)\n")

    rows = scp.query_performance(site_url, start, end, "web", [], [], refresh=True)
    if isinstance(rows, dict) and rows.get("error"):
        print(f"   FAILED: {rows['error']}")
        return
    if not rows:
        print("   No rows returned for this window.")
        return

    m = rows[0]
    print(f"   {'app value':>14}   GSC column to compare")
    print(f"   {num(m.get('clicks')):>14}   Total clicks")
    print(f"   {num(m.get('impressions')):>14}   Total impressions")
    print(f"   {(float(m.get('ctr') or 0) * 100):>13.2f}%   Average CTR")
    print(f"   {float(m.get('position') or 0):>14.1f}   Average position")

    top = scp.query_performance(site_url, start, end, "web", ["query"], [], refresh=True)
    if isinstance(top, list) and top:
        print(f"\n   Top queries returned: {len(top)}  (GSC UI shows its own top slice)")
        for q in top[:5]:
            keys = q.get("keys") or [""]
            print(f"     {str(keys[0])[:34]:34} {num(q.get('clicks')):>7} clicks")
        print("\n   NOTE: query rows will NOT sum to Total clicks. GSC withholds")
        print("   low-volume anonymised queries. The GSC UI behaves the same way.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", type=int, default=16)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--start")
    ap.add_argument("--end")
    args = ap.parse_args()

    if args.start and args.end:
        start, end = args.start, args.end
    else:
        # Last complete calendar month — the only window where both APIs are settled.
        first_this = date.today().replace(day=1)
        last_prev = first_this - timedelta(days=1)
        start = last_prev.replace(day=1).isoformat()
        end = last_prev.isoformat()

    gen = db.get_db()
    conn = next(gen)
    try:
        sql = ("SELECT id, name, ga_property_id, gsc_site_url FROM projects"
               " WHERE active = 1 ORDER BY name" if args.all else
               "SELECT id, name, ga_property_id, gsc_site_url FROM projects WHERE id = ?")
        rows = conn.execute(sql, () if args.all else (args.project,)).fetchall()
    finally:
        gen.close()

    if not rows:
        print("No matching project.")
        return

    for p in rows:
        print("\n" + "=" * 72)
        print(f"{p['name']}  (project {p['id']})")
        print("=" * 72)
        if p["ga_property_id"]:
            check_ga4(str(p["ga_property_id"]), start, end)
        else:
            print("\nGA4: no property id set for this project.")
        if p["gsc_site_url"]:
            check_gsc(str(p["gsc_site_url"]), start, end)
        else:
            print("\nGSC: no site url set for this project.")


if __name__ == "__main__":
    main()
