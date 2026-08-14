from app.main import app


def _iter_paths():
    for route in app.routes:
        if hasattr(route, "effective_route_contexts"):
            for ctx in route.effective_route_contexts():
                sr = getattr(ctx, "starlette_route", None)
                if sr is not None:
                    path = getattr(sr, "path", None)
                    methods = getattr(sr, "methods", None)
                else:
                    path = getattr(ctx, "path", None)
                    methods = getattr(ctx, "methods", None)
                yield from _emit(path, methods)
        else:
            yield from _emit(getattr(route, "path", None), getattr(route, "methods", None))


def _emit(path, methods):
    if path is None:
        return
    if methods:
        for m in sorted(methods):
            if m in {"HEAD", "OPTIONS"}:
                continue
            yield (m, path)
    else:
        yield ("-", path)


def main() -> int:
    rows = sorted(set(_iter_paths()), key=lambda r: (r[1], r[0]))
    for m, path in rows:
        print(f"{m:7} {path}")
    print(f"\n{len(rows)} routes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
