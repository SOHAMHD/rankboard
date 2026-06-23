"""API ENTRY POINT — wires routers and error handling into the app.

Bonus you get for free with FastAPI: open http://localhost:4000/docs
for interactive API documentation generated from the code — every
endpoint, testable in the browser. (Remember "the Postman stuff"?
This is that, built in.)

The two exception handlers below exist for one reason: the React
client expects errors shaped {"error": "..."} — that's the contract
the Node server established, so this server honors it exactly.
"""
import jwt
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import CORS_ORIGINS, DEBUG, JWT_SECRET
from .db import get_connection, init_db
from .permissions import READ_ONLY_ROLES
from .routers import auth, moz, projects, snapshots, users

init_db()

app = FastAPI(
    title="RankBoard API (Python)",
    # Docs expose the full API surface — disabled unless DEBUG is set.
    docs_url="/docs" if DEBUG else None,
    redoc_url="/redoc" if DEBUG else None,
    openapi_url="/openapi.json" if DEBUG else None,
)

# ── Read-only role enforcement (one middleware, by HTTP method) ──────
# A read-only role (any role in READ_ONLY_ROLES) may GET anything they can
# already see, but must never mutate. Rather than guard every write route
# individually — where a future route could be forgotten — we block by METHOD
# here: any POST/PUT/PATCH/DELETE from a read-only user gets 403, EXCEPT a
# small, explicit exemption list.
#
# READ_ONLY_ROLES is currently EMPTY: "Team" became a write-capable report
# author, so this middleware is presently a no-op. It stays wired in so a
# future read-only role is a one-line addition to that set (permissions.py).
#
# Two kinds of exemption:
#   • session/account routes the member must still reach to sign in and
#     activate their account (login, set-password);
#   • POST endpoints that only READ (the GA4 / Search Console panels send
#     their filters in a POST body) — blocking these would wrongly remove
#     the dashboard read access the role is meant to keep.
#
# The role is looked up FRESH from the DB by token subject (never trusted
# from the token body), matching require_auth: an admin demoting someone to
# read-only takes effect on their very next request. If the token is missing
# or invalid we do nothing and let the normal auth dependencies answer 401.
WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

# Exact paths always allowed even for read-only users (session / account).
READ_ONLY_EXEMPT_PATHS = {
    "/api/auth/login",
    "/api/auth/set-password",
}

# POST endpoints that are reads in disguise (filters travel in the body).
# Matched by suffix because each is nested under /api/projects/{id}/...
READ_ONLY_EXEMPT_SUFFIXES = (
    "/analytics",
    "/analytics/breakdown",
    "/analytics/report",
    "/search-console/performance",
)


def _read_only_exempt(path: str) -> bool:
    return path in READ_ONLY_EXEMPT_PATHS or path.endswith(READ_ONLY_EXEMPT_SUFFIXES)


def _role_for_request(request: Request) -> str | None:
    """The caller's CURRENT role from the DB, or None if we can't identify
    them (no/!invalid token, or the user no longer exists)."""
    authorization = request.headers.get("authorization")
    if not authorization or not authorization.startswith("Bearer "):
        return None
    try:
        payload = jwt.decode(authorization[7:], JWT_SECRET, algorithms=["HS256"])
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None
    # Use the same backend as the rest of the app (Postgres or SQLite), not a
    # hardcoded SQLite file, so the role is read from the live database.
    conn = get_connection()
    try:
        row = conn.execute("SELECT role FROM users WHERE id = ?", (user_id,)).fetchone()
    finally:
        conn.close()
    return row[0] if row else None


@app.middleware("http")
async def block_read_only_writes(request: Request, call_next):
    if request.method in WRITE_METHODS and not _read_only_exempt(request.url.path):
        if _role_for_request(request) in READ_ONLY_ROLES:
            return JSONResponse(
                status_code=403,
                content={"error": "Your access is read-only — you can view everything but can't make changes."},
            )
    return await call_next(request)


# Browser CORS: an explicit allowlist (never "*"), so only the known frontend
# origin(s) may call the API. Auth uses the Authorization header, but
# allow_credentials stays on so cookie-based flows aren't silently broken.
# The deployed frontend (Render) and local dev (Vite) are always allowed;
# CORS_ORIGINS (env, default http://localhost:5173) adds any extra origins.
# Added AFTER the read-only middleware so CORS sits OUTERMOST: a 403 from the
# block above still gets the CORS headers a browser needs to read it.
ALLOWED_ORIGINS = list(dict.fromkeys([
    "https://rankboard-1.onrender.com",  # deployed frontend (Render)
    "http://localhost:5173",             # local dev (Vite)
    *CORS_ORIGINS,
]))
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=400, content={"error": "Invalid request body."})


app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(users.router, prefix="/api/users", tags=["users"])
app.include_router(projects.router, prefix="/api/projects", tags=["projects"])
app.include_router(moz.router, prefix="/api/projects", tags=["moz"])
app.include_router(snapshots.router, prefix="/api/snapshots", tags=["snapshots"])
