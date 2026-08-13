"""Repoint projects whose gsc_site_url doesn't match a real Search Console property.

    python -m scripts.fix_gsc_site_urls            # dry run
    python -m scripts.fix_gsc_site_urls --commit

Only rewrites where exactly one visible property matches after normalising away
the scheme, `www.` and the trailing slash — i.e. where the intent is unambiguous.
Anything with no match, or more than one, is listed for you to decide.
"""

import sys

from app.db import db_session
from app.services.search_console_provider import list_sites


def core(s: str) -> str:
    if s.lower().startswith("sc-domain:"):
        return s.split(":", 1)[1].strip().strip("/").lower()
    s = s.split("://", 1)[-1].strip("/").lower()
    return s[4:] if s.startswith("www.") else s


def main() -> int:
    commit = "--commit" in sys.argv

    sites, err = list_sites()
    if err:
        print(f"Could not reach Search Console: {err}")
        return 1
    if not sites:
        print("The service account can't see any properties — nothing to match against.")
        return 1

    with db_session() as db:
        projects = db.execute(
            "SELECT id, name, gsc_site_url FROM projects"
            " WHERE gsc_site_url IS NOT NULL AND gsc_site_url <> ''"
            " ORDER BY id"
        ).fetchall()

        fixes, unresolved = [], []
        for p in projects:
            current = p["gsc_site_url"]
            if current in sites:
                continue
            matches = [s for s in sites if core(s) == core(current)]
            if len(matches) == 1:
                fixes.append((p["id"], p["name"], current, matches[0]))
            else:
                unresolved.append((p["id"], p["name"], current, matches))

        for pid, name, old, new in fixes:
            print(f"#{pid} {name}\n    {old!r}\n -> {new!r}")
            if commit:
                db.execute("UPDATE projects SET gsc_site_url = ? WHERE id = ?", (new, pid))

        for pid, name, old, matches in unresolved:
            print(f"#{pid} {name}: {old!r} — {'ambiguous: ' + str(matches) if matches else 'no matching property'}")

    print(f"\n{len(fixes)} fixable, {len(unresolved)} need a decision.")
    if fixes and not commit:
        print("Dry run — re-run with --commit to apply.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
