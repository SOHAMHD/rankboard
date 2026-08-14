import sys

from fastapi.routing import APIRoute

from app.main import app
from app.security import require_project_access

PROJECT_ID_MARKER = "{project_id}"


def _dependant_calls(dependant):
    for dep in dependant.dependencies:
        if dep.call is not None:
            yield dep.call
        yield from _dependant_calls(dep)


def _walk_routes(routes, prefix=""):
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
    rows = []
    for full_path, route in _walk_routes(app.routes):
        if PROJECT_ID_MARKER not in full_path:
            continue
        guarded = any(call is require_project_access for call in _dependant_calls(route.dependant))
        methods = ",".join(sorted(route.methods or []))
        rows.append((methods, full_path, guarded))
    return sorted(rows)


def find_unguarded_routes():
    return [(m, p) for m, p, guarded in collect_project_routes() if not guarded]


def test_all_project_routes_guarded():
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
