"""API ENTRY POINT — wires routers and error handling into the app.

Bonus you get for free with FastAPI: open http://localhost:4000/docs
for interactive API documentation generated from the code — every
endpoint, testable in the browser. (Remember "the Postman stuff"?
This is that, built in.)

The two exception handlers below exist for one reason: the React
client expects errors shaped {"error": "..."} — that's the contract
the Node server established, so this server honors it exactly.
"""
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import CORS_ORIGINS, DEBUG
from .db import init_db
from .routers import auth, moz, projects, users

init_db()

app = FastAPI(
    title="RankBoard API (Python)",
    # Docs expose the full API surface — disabled unless DEBUG is set.
    docs_url="/docs" if DEBUG else None,
    redoc_url="/redoc" if DEBUG else None,
    openapi_url="/openapi.json" if DEBUG else None,
)

# Browser CORS: an explicit allowlist (never "*"), so only the known frontend
# origin(s) may call the API. Auth uses the Authorization header, but
# allow_credentials stays on so cookie-based flows aren't silently broken.
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
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
