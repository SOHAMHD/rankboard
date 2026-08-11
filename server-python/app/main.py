import traceback

import jwt
from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import CORS_ORIGINS, DEBUG, JWT_SECRET
from .db import close_pool, get_db, init_db
from .permissions import READ_ONLY_ROLES
from .routers import (
    auth,
    backlinks,
    email_log,
    locations,
    moz,
    posts,
    projects,
    reports,
    users,
    webhooks,
)

init_db()

app = FastAPI(
    title="SEO Dashboard API (Python)",
    docs_url="/docs" if DEBUG else None,
    redoc_url="/redoc" if DEBUG else None,
    openapi_url="/openapi.json" if DEBUG else None,
)

WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

READ_ONLY_EXEMPT_PATHS = {
    "/api/auth/login",
    "/api/auth/set-password",
    # Brevo's event webhook. It's a POST from a machine with no account here, so
    # the role lookup below finds nothing and the check would 403 every event.
    # Its own shared-secret check is in routers/webhooks.py.
    "/api/webhooks/brevo",
}

READ_ONLY_EXEMPT_SUFFIXES = (
    "/analytics",
    "/analytics/breakdown",
    "/analytics/report",
    "/search-console/performance",
)


def _read_only_exempt(path: str) -> bool:
    return path in READ_ONLY_EXEMPT_PATHS or path.endswith(READ_ONLY_EXEMPT_SUFFIXES)


def _role_for_request(request: Request) -> str | None:
    authorization = request.headers.get("authorization")
    if not authorization or not authorization.startswith("Bearer "):
        return None
    try:
        payload = jwt.decode(authorization[7:], JWT_SECRET, algorithms=["HS256"])
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None
    # Borrow from the pool rather than opening a dedicated connection — this runs
    # on every write request once READ_ONLY_ROLES is non-empty.
    gen = get_db()
    conn = next(gen)
    try:
        row = conn.execute("SELECT role FROM users WHERE id = ?", (user_id,)).fetchone()
    finally:
        gen.close()
    return row[0] if row else None


@app.middleware("http")
async def block_read_only_writes(request: Request, call_next):
    if (
        READ_ONLY_ROLES
        and request.method in WRITE_METHODS
        and not _read_only_exempt(request.url.path)
    ):
        role = await run_in_threadpool(_role_for_request, request)
        if role in READ_ONLY_ROLES:
            return JSONResponse(
                status_code=403,
                content={"error": "Your access is read-only — you can view everything but can't make changes."},
            )
    return await call_next(request)


ALLOWED_ORIGINS = list(dict.fromkeys([
    "https://rankboard-1.onrender.com",
    "http://localhost:5173",
    *CORS_ORIGINS,
]))
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("shutdown")
def _release_resources() -> None:
    close_pool()
    try:
        from .services.report_pdf import shutdown_renderer
        shutdown_renderer()
    except Exception:
        pass


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=400, content={"error": "Invalid request body."})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Return the shape the client parses, even when something unexpected breaks.

    Without this, an error the handlers didn't anticipate — a driver-level
    DataError, say — came back as Starlette's plain-text "Internal Server Error".
    api.js does `res.json().catch(() => ({}))`, so the real status was preserved
    but the user saw the generic "Something went wrong." with nothing logged
    client-side. The detail is only exposed when DEBUG is on.
    """
    traceback.print_exception(type(exc), exc, exc.__traceback__)
    detail = f"{exc.__class__.__name__}: {exc}" if DEBUG else "Something went wrong on the server."
    return JSONResponse(status_code=500, content={"error": detail})


app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(users.router, prefix="/api/users", tags=["users"])
app.include_router(locations.router, prefix="/api/locations", tags=["locations"])
app.include_router(projects.router, prefix="/api/projects", tags=["projects"])
app.include_router(moz.router, prefix="/api/projects", tags=["moz"])
app.include_router(backlinks.router, prefix="/api/projects", tags=["backlinks"])
app.include_router(posts.router, prefix="/api/projects", tags=["posts"])
app.include_router(reports.router, prefix="/api/reports", tags=["reports"])
app.include_router(email_log.router, prefix="/api/email-log", tags=["email-log"])
app.include_router(webhooks.router, prefix="/api/webhooks", tags=["webhooks"])
