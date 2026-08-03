"""Diff GA4's two channel-grouping models for a project.

Why this exists
---------------
GA4 has two channel groupings and they are NOT interchangeable:

  sessionPrimaryChannelGroup   - the current model, what the GA4 UI shows
  sessionDefaultChannelGroup   - the legacy model

They disagree most on Organic Search vs Direct, because they apply different
rules to sessions with missing or ambiguous referrer information. This script
runs the same query twice, once per grouping, and prints them side by side so
you can see exactly which channels move and by how much.

Usage
-----
    cd server-python
    python compare_channel_groups.py                       # project 16, last 28 days
    python compare_channel_groups.py --project 16
    python compare_channel_groups.py --project 16 --days 90
    python compare_channel_groups.py --project 16 --start 2026-07-01 --end 2026-07-31
    python compare_channel_groups.py --all                  # every active project
    python compare_channel_groups.py --metric sessions      # default: sessions
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app import db  # noqa: E402
from app.services import analytics_provider as ga  # noqa: E402

GROUPINGS = ("sessionPrimaryChannelGroup", "sessionDefaultChannelGroup")


def fetch(property_id: str, dimension: str, start: str, end: str, metric: str) -> dict:
    report = ga.run_custom_report(
        property_id,
        start,
        end,
        [dimension],
        [metric],
        limit=100,
        refresh=True,          # bypass the response cache so both sides are fresh
    )
    if isinstance(report, dict) and report.get("error"):
        raise RuntimeError(report["error"])
    rows = {}
    for r in report.get("rows", []):
        dims = r.get("dims") or []
        if dims:
            rows[str(dims[0])] = int(r.get("metrics", {}).get(metric) or 0)
    total = int((report.get("totals") or {}).get(metric) or 0)
    return {"rows": rows, "total": total}


def compare(name: str, property_id: str, start: str, end: str, metric: str) -> None:
    print(f"\n{'=' * 72}")
    print(f"{name}  (property {property_id})   {start} -> {end}   metric: {metric}")
    print("=" * 72)

    try:
        primary = fetch(property_id, GROUPINGS[0], start, end, metric)
        legacy = fetch(property_id, GROUPINGS[1], start, end, metric)
    except Exception as exc:
        print(f"  FAILED: {exc}")
        return

    channels = sorted(
        set(primary["rows"]) | set(legacy["rows"]),
        key=lambda c: -max(primary["rows"].get(c, 0), legacy["rows"].get(c, 0)),
    )

    print(f"  {'CHANNEL':26} {'PRIMARY':>10} {'LEGACY':>10} {'DIFF':>10}")
    print(f"  {'-' * 26} {'-' * 10} {'-' * 10} {'-' * 10}")
    for c in channels:
        p = primary["rows"].get(c, 0)
        l = legacy["rows"].get(c, 0)
        d = p - l
        flag = "  <<<" if abs(d) >= max(25, int(0.05 * max(p, l, 1))) else ""
        print(f"  {c[:26]:26} {p:>10,} {l:>10,} {d:>+10,}{flag}")

    print(f"  {'-' * 26} {'-' * 10} {'-' * 10} {'-' * 10}")
    print(
        f"  {'TOTAL (GA4 aggregate)':26} {primary['total']:>10,} {legacy['total']:>10,}"
        f" {primary['total'] - legacy['total']:>+10,}"
    )
    print(f"  {'sum of rows':26} {sum(primary['rows'].values()):>10,} {sum(legacy['rows'].values()):>10,}")
    print("\n  Rows marked <<< moved materially between the two models.")
    print("  Row sums exceeding the total is normal for user metrics (de-duplication).")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", type=int, default=None, help="Project id")
    ap.add_argument("--all", action="store_true", help="Every active project with a GA4 property")
    ap.add_argument("--days", type=int, default=28, help="Preset window length (default 28)")
    ap.add_argument("--start", help="Explicit start date YYYY-MM-DD (overrides --days)")
    ap.add_argument("--end", help="Explicit end date YYYY-MM-DD")
    ap.add_argument("--metric", default="sessions", help="GA4 metric to compare (default sessions)")
    args = ap.parse_args()

    if args.start and args.end:
        start, end = args.start, args.end
    else:
        # Relative tokens so GA4 resolves the window in the property's timezone.
        start, end = f"{args.days}daysAgo", "yesterday"

    gen = db.get_db()
    conn = next(gen)
    try:
        if args.all:
            rows = conn.execute(
                "SELECT id, name, ga_property_id FROM projects"
                " WHERE active = 1 AND ga_property_id IS NOT NULL AND ga_property_id <> ''"
                " ORDER BY name"
            ).fetchall()
        else:
            pid = args.project if args.project is not None else 16
            rows = conn.execute(
                "SELECT id, name, ga_property_id FROM projects WHERE id = ?", (pid,)
            ).fetchall()

        if not rows:
            print("No matching project with a GA4 property id.")
            return

        for r in rows:
            if not r["ga_property_id"]:
                print(f"\n{r['name']}: no GA4 property id, skipped")
                continue
            compare(r["name"], str(r["ga_property_id"]), start, end, args.metric)
    finally:
        gen.close()


if __name__ == "__main__":
    main()
