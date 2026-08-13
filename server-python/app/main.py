import traceback

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import CORS_ORIGINS, DEBUG
from .db import close_pool, init_db
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

init_db()

app = FastAPI(
    title="SEO Dashboard API (Python)",
    docs_url="/docs" if DEBUG else None,
    redoc_url="/redoc" if DEBUG else None,
    openapi_url="/openapi.json" if DEBUG else None,
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
    traceback.print_exception(type(exc), exc, exc.__traceback__)
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
