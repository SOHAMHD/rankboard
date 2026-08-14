import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import CORS_ORIGINS, DEBUG
from .db import close_pool, db_session, init_db
from .services import report_pdf
from .routers import (
    auth,
    backlinks,
    email_log,
    moz,
    posts,
    projects,
    reports,
    users,
    webhooks,
)

# Configure the root logger before anything else imports and starts logging.
# Modules across the app log through logging.getLogger(__name__); without a
# handler configured here those records went nowhere and the app's only visible
# diagnostics were stray print()s on stdout with no timestamp or source.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)

init_db()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: nothing to do — init_db() runs at import time, before the first
    # worker is ready to accept a request.
    yield
    # Shutdown. Was @app.on_event("shutdown"), which Starlette deprecates.
    close_pool()
    try:
        from .services.report_pdf import shutdown_renderer
        shutdown_renderer()
    except Exception:
        logger.warning("PDF renderer did not shut down cleanly.", exc_info=True)


app = FastAPI(
    title="SEO Dashboard API (Python)",
    docs_url="/docs" if DEBUG else None,
    redoc_url="/redoc" if DEBUG else None,
    openapi_url="/openapi.json" if DEBUG else None,
    lifespan=lifespan,
)

# The read-only-role middleware that used to live here was gated on
# permissions.READ_ONLY_ROLES, an empty frozenset — so it never ran. It has been
# removed along with READ_ONLY_EXEMPT_PATHS, _read_only_exempt and
# _role_for_request. Note that re-adding it would put a database round trip in
# front of every write request, which is why it was worth deleting rather than
# leaving as scaffolding.


ALLOWED_ORIGINS = list(dict.fromkeys([
    "https://rankboard-1.onrender.com",
    # The Vite dev server, only when DEBUG is on. It was unconditional, so
    # production advertised a localhost origin with allow_credentials=True. The
    # practical risk is small — auth is a Bearer token, not a cookie — but a dev
    # origin has no business in a production Access-Control-Allow-Origin list.
    *(["http://localhost:5173"] if DEBUG else []),
    *CORS_ORIGINS,
]))
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", include_in_schema=False)
def health():
    """Liveness/readiness probe. Unauthenticated and deliberately cheap.

    A bare {"ok": true} would pass while the database was unreachable, which is
    the failure a platform health check most needs to catch — so it takes a
    pooled connection and runs SELECT 1. That is one round trip and no rows, and
    it uses db_session so the connection goes straight back to the pool.
    """
    try:
        with db_session() as db:
            db.execute("SELECT 1").fetchone()
    except Exception:
        logger.warning("Health check failed: database unreachable.", exc_info=True)
        return JSONResponse(status_code=503, content={"ok": False, "db": False})
    return {"ok": True}


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=400, content={"error": "Invalid request body."})


@app.exception_handler(report_pdf.RenderBusy)
async def render_busy_handler(request: Request, exc: report_pdf.RenderBusy):
    """503 with Retry-After, not a 500.

    Rendering is serialised on one thread. Arriving behind a deep queue is a
    capacity condition the client can sensibly retry, and saying so beats holding
    the request open for 90 seconds and then failing.
    """
    return JSONResponse(status_code=503, content={"error": str(exc)},
                        headers={"Retry-After": "20"})


@app.exception_handler(report_pdf.RenderTimeout)
async def render_timeout_handler(request: Request, exc: report_pdf.RenderTimeout):
    return JSONResponse(status_code=504, content={"error": str(exc)})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Return the shape the client parses, even when something unexpected breaks.

    Without this, an error the handlers didn't anticipate — a driver-level
    DataError, say — came back as Starlette's plain-text "Internal Server Error".
    api.js does `res.json().catch(() => ({}))`, so the real status was preserved
    but the user saw the generic "Something went wrong." with nothing logged
    client-side. The detail is only exposed when DEBUG is on.
    """
    logger.exception("Unhandled error on %s %s", request.method, request.url.path,
                     exc_info=exc)
    detail = f"{exc.__class__.__name__}: {exc}" if DEBUG else "Something went wrong on the server."
    return JSONResponse(status_code=500, content={"error": detail})


app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(users.router, prefix="/api/users", tags=["users"])
app.include_router(projects.router, prefix="/api/projects", tags=["projects"])
app.include_router(moz.router, prefix="/api/projects", tags=["moz"])
app.include_router(backlinks.router, prefix="/api/projects", tags=["backlinks"])
app.include_router(posts.router, prefix="/api/projects", tags=["posts"])
app.include_router(reports.router, prefix="/api/reports", tags=["reports"])
app.include_router(email_log.router, prefix="/api/email-log", tags=["email-log"])
app.include_router(webhooks.router, prefix="/api/webhooks", tags=["webhooks"])
