import jwt
from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import CORS_ORIGINS, DEBUG, JWT_SECRET
from .db import get_connection, init_db
from .permissions import READ_ONLY_ROLES
from .routers import auth, backlinks, locations, moz, posts, projects, reports, snapshots, users

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
    conn = get_connection()
    try:
        row = conn.execute("SELECT role FROM users WHERE id = ?", (user_id,)).fetchone()
    finally:
        conn.close()
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


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=400, content={"error": "Invalid request body."})


app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(users.router, prefix="/api/users", tags=["users"])
app.include_router(locations.router, prefix="/api/locations", tags=["locations"])
app.include_router(projects.router, prefix="/api/projects", tags=["projects"])
app.include_router(moz.router, prefix="/api/projects", tags=["moz"])
app.include_router(backlinks.router, prefix="/api/projects", tags=["backlinks"])
app.include_router(posts.router, prefix="/api/projects", tags=["posts"])
app.include_router(snapshots.router, prefix="/api/snapshots", tags=["snapshots"])
app.include_router(reports.router, prefix="/api/reports", tags=["reports"])
