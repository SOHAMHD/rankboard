"""Point projects at the right Search Console property.

    python -m scripts.fix_gsc_site_urls            # dry run
    python -m scripts.fix_gsc_site_urls --commit

Covers both ways a project ends up without working Search Console data:

  * gsc_site_url is set but isn't a property the service account can read — a
    stale value, or one typed in the wrong notation.
  * gsc_site_url is empty, and the project's domain does match a visible
    property. This is what happens when the service account is added to the
    property after the project was created: nothing re-resolves it on its own.

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
        # Empty ones are included deliberately. A project resolves its property
        # when it is created or saved, and nothing re-resolves it in between — so
        # granting the service account access to a property AFTER the project was
        # made leaves that project permanently blank until somebody happens to
        # open it and press Save. Those are matched on `domain` instead, which is
        # the same thing resolve_gsc_site_url() would match on.
        projects = db.execute(
            "SELECT id, name, domain, gsc_site_url FROM projects ORDER BY id"
        ).fetchall()

        fixes, unresolved = [], []
        for p in projects:
            current = (p["gsc_site_url"] or "").strip()
            if current and current in sites:
                continue
            against = current or (p["domain"] or "").strip()
            if not against:
                unresolved.append((p["id"], p["name"], "(no property, no domain)", []))
                continue
            matches = [s for s in sites if core(s) == core(against)]
            if len(matches) == 1:
                fixes.append((p["id"], p["name"], current or f"(empty, domain {against})",
                              matches[0]))
            else:
                unresolved.append((p["id"], p["name"], current or f"(empty, domain {against})",
                                   matches))

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
