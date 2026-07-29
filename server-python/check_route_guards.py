"""SAFETY NET — fail loudly if any project-scoped route is missing its guard.

Per-client scoping leans on EVERY route with a `{project_id}` path param being
protected by `require_project_access` (see app/security.py). A future route
added without it would silently let any signed-in user reach another client's
project. This script catches that: it imports the real app, finds every route
whose path contains "{project_id}", and exits non-zero if any of them lacks the
guard in its (fully-merged) dependency tree.

Run it from the server-python directory:

    python check_route_guards.py

Exit 0 = every project-scoped route is guarded. Exit 1 = at least one is not
(the offenders are listed). Importing the app runs init_db(), which only
CREATEs tables IF NOT EXISTS (no reset) and starts no server.

It's also pytest-collectable: `pytest check_route_guards.py` runs
test_all_project_routes_guarded().
"""
import sys

from fastapi.routing import APIRoute

from app.main import app
from app.security import require_project_access

PROJECT_ID_MARKER = "{project_id}"


def _dependant_calls(dependant):
    """Yield the `.call` of every dependency in a route's dependant tree,
    recursively. A route's per-route `dependencies=[...]` (where the guard is
    applied) and the router-level dependencies are both merged into
    route.dependant when the route is added, so this sees the full picture."""
    for dep in dependant.dependencies:
        if dep.call is not None:
            yield dep.call
        yield from _dependant_calls(dep)


def _walk_routes(routes, prefix=""):
    """Yield (full_path, APIRoute) for every concrete route.

    This app's FastAPI uses LAZY router inclusion: app.routes holds
    `_IncludedRouter` wrappers, not flattened APIRoutes. Each wrapper exposes
    `.original_router` (the real APIRouter) and `.include_context.prefix`. We
    recurse through those to reach the actual APIRoutes and rebuild their full
    paths. Falls back gracefully to standard flat APIRoutes if a plain FastAPI
    ever materializes them directly."""
    for route in routes:
        if isinstance(route, APIRoute):
            yield prefix + route.path, route
            continue
        orig = getattr(route, "original_router", None)
        if orig is None:
            continue
        ctx = getattr(route, "include_context", None)
        sub_prefix = prefix + (getattr(ctx, "prefix", "") or "")
        yield from _walk_routes(orig.routes, sub_prefix)


def collect_project_routes():
    """All {project_id} routes with whether each is guarded — for reporting."""
    rows = []
    for full_path, route in _walk_routes(app.routes):
        if PROJECT_ID_MARKER not in full_path:
            continue
        guarded = any(call is require_project_access for call in _dependant_calls(route.dependant))
        methods = ",".join(sorted(route.methods or []))
        rows.append((methods, full_path, guarded))
    return sorted(rows)


def find_unguarded_routes():
    """Return [(method, path)] for every {project_id} route missing the guard."""
    return [(m, p) for m, p, guarded in collect_project_routes() if not guarded]


def test_all_project_routes_guarded():
    """pytest entry point: every {project_id} route must carry the guard."""
    unguarded = find_unguarded_routes()
    assert not unguarded, f"Unguarded {{project_id}} routes: {unguarded}"


def main() -> int:
    rows = collect_project_routes()
    if not rows:
        print("No {project_id} routes found — nothing to check (unexpected).")
        return 1

    for methods, path, guarded in rows:
        mark = "OK  " if guarded else "MISSING"
        print(f"  [{mark}] {methods:7} {path}")

    unguarded = [(m, p) for m, p, g in rows if not g]
    print()
    if unguarded:
        print(f"FAIL: {len(unguarded)} project-scoped route(s) missing require_project_access:")
        for methods, path in unguarded:
            print(f"  - {methods} {path}")
        return 1

    print(f"PASS: all {len(rows)} project-scoped routes are guarded by require_project_access.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
