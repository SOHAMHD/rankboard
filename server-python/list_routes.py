"""THROWAWAY DEV SCRIPT — list every route the FastAPI app registers.

Imports the existing app and walks app.routes (no server, no app changes).

This FastAPI build uses LAZY router inclusion: include_router() appends an
_IncludedRouter wrapper to app.routes instead of flattening the child routes,
so the real (prefixed) paths live behind _IncludedRouter.effective_route_contexts().
We resolve those here. Delete this file when done.
"""
from app.main import app


def _iter_paths():
    """Yield (method, path) for every concrete operation the app serves."""
    for route in app.routes:
        # Lazily-included router: expand to its effective (prefixed) routes.
        if hasattr(route, "effective_route_contexts"):
            for ctx in route.effective_route_contexts():
                sr = getattr(ctx, "starlette_route", None)
                if sr is not None:  # non-API route (Mount/WebSocket/plain Route)
                    path = getattr(sr, "path", None)
                    methods = getattr(sr, "methods", None)
                else:  # APIRoute: prefixed path/methods live on the context itself
                    path = getattr(ctx, "path", None)
                    methods = getattr(ctx, "methods", None)
                yield from _emit(path, methods)
        else:  # a route registered directly on the app
            yield from _emit(getattr(route, "path", None), getattr(route, "methods", None))


def _emit(path, methods):
    if path is None:
        return
    if methods:
        for m in sorted(methods):
            if m in {"HEAD", "OPTIONS"}:  # auto-added by Starlette; skip noise
                continue
            yield (m, path)
    else:
        yield ("-", path)  # mounts / websockets — no HTTP methods


def main() -> int:
    rows = sorted(set(_iter_paths()), key=lambda r: (r[1], r[0]))
    for m, path in rows:
        print(f"{m:7} {path}")
    print(f"\n{len(rows)} routes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
