# Deploying the API (Render)

The backend is a FastAPI app served by Uvicorn. It is stateless apart from the
Postgres database and a scratch directory for report cover images.

Everything marked **CONFIRM:** below is inferred from the code, not read from a
Render config file (there is no `render.yaml` in the repo) — verify it against
the live service before relying on it.

**CONFIRM:** the deployed frontend is `https://rankboard-1.onrender.com`, which
is hard-coded into the CORS allow-list in `app/main.py`. The API's own Render URL
is not referenced anywhere in the code, so it has to be read off the dashboard.

---

## Service type

- Render **Web Service**, Python 3 runtime.
- Root directory: `server-python`
- **CONFIRM:** the React frontend is a separate Render **Static Site** built
  from `client/` (`npm ci && npm run build`, publish directory `client/dist`).
  Its one build-time variable is `VITE_API_BASE_URL`, which must point at this
  API service's URL — see `client/.env.example`.

## Build command

```
pip install -r requirements.txt && playwright install chromium
```

The second half is not optional. `app/services/report_pdf.py` renders report
PDFs with headless Chromium via Playwright, and `pip install playwright` only
installs the Python bindings — not the browser. A clean deploy that runs just
`pip install -r requirements.txt` will start fine, serve every other endpoint
fine, and then fail on the **first PDF export** with a Playwright
"executable doesn't exist" error. Until now this was documented only as a
trailing comment on the `playwright` line inside `requirements.txt`.

**CONFIRM:** on Render's native Python runtime the browser lands in
`~/.cache/ms-playwright`, which persists between the build and run phases of a
deploy but is rebuilt on every deploy — that is fine, since the build command
reinstalls it each time. If you ever see the browser go missing at runtime, set
`PLAYWRIGHT_BROWSERS_PATH=/opt/render/project/.playwright` for both the build
and the start command so the two phases agree on one location.

## Start command

```
python -m uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 2 --proxy-headers
```

(The repo root `package.json` has the same thing as `npm run start:api`.)

Notes on the flags:

- `--host 0.0.0.0` — Render routes to the container's external interface;
  the Uvicorn default of `127.0.0.1` is unreachable and the deploy will hang on
  the port scan.
- `--port $PORT` — Render assigns the port. `app/config.py` also reads `PORT`,
  but the uvicorn CLI flag is what actually binds.
- `--proxy-headers` — **required.** Render terminates TLS at its edge proxy, so
  without this every request arrives with `request.client.host` set to the
  proxy's internal IP. `app/routers/auth.py` uses `request.client.host` as the
  key for login/OTP rate limiting (see `app/services/throttle.py`), so without
  `--proxy-headers` every user on the internet shares one throttle bucket:
  one person fumbling their password locks out everybody else.
- `--workers 2` — PDF rendering is serialised on a single renderer thread per
  process (`report_pdf.RenderBusy` is returned as a 503 with `Retry-After` when
  the queue is deep), so a second worker keeps the rest of the API responsive
  while a report renders. Each worker holds its own psycopg connection pool, so
  raising this multiplies your Supabase connection count — check the pooler
  limit on your plan before going higher.

## Database — Postgres / Supabase

The app is **Postgres-only**. `app/db.py` raises at import if `DATABASE_URL` is
missing, and raises again if the URL does not start with `postgresql://`,
`postgres://` or `postgresql+psycopg://`. There is no SQLite fallback and no
local-file mode, despite `sqlite3`-shaped naming still visible in parts of the
code.

Use the Supabase **Session pooler** connection string (port 5432), from
Project settings → Database → Connection string.

### Migrations: set `SKIP_DB_INIT=1` on the app service

`app/main.py` calls `init_db()` at import time, and `init_db()` executes the
whole `CREATE TABLE IF NOT EXISTS` / `ALTER TABLE` schema block plus the seed
pass. The DDL is idempotent, but *every worker process runs it on every boot*,
which means:

- on a `--workers 2` deploy, two processes issue the same DDL concurrently and
  can deadlock or error out against each other on the same catalog rows;
- every restart pays the cost of a full schema round trip before serving.

So on the deployed service set:

```
SKIP_DB_INIT=1
```

and run the schema pass **once**, as a separate step, before or during the
deploy — a Render "pre-deploy command" or a manual one-off job:

```
cd server-python && python -c "from app.db import init_db; init_db()"
```

Run that with `SKIP_DB_INIT` **unset** in that job's environment, otherwise
`init_db()` prints "SKIP_DB_INIT is set — skipping schema/seed." and does
nothing. Locally, leave `SKIP_DB_INIT` unset entirely; single-process dev
servers have nothing to race.

### Backups

Backups are whatever Supabase does automatically for your project. Retention
depends on plan tier (and point-in-time recovery is a paid add-on) — confirm
what your project actually has before treating it as a backup strategy. There is
nothing in this repo that backs the database up.

---

## Environment variables

Set these in the Render dashboard (Environment → Environment Variables). The
`.env` file is a local-development convenience only — `app/config.py` reads it
if present but uses `os.environ.setdefault`, so real environment variables
always win. `server-python/.env.example` documents every one of these in more
detail.

### Required — the service will not work without them

| Variable | Why |
|---|---|
| `DATABASE_URL` | Postgres/Supabase URL. `app/db.py` raises at import without it. |
| `JWT_SECRET` | Auth token signing key. `app/config.py` raises at import without it. No fallback by design. Use 32+ random bytes. |
| `APP_URL` | Frontend origin, e.g. `https://rankboard-1.onrender.com`. **No trailing slash.** Invite links, sign-in links, `EMAIL_LOGO_URL` and `REPORT_ASSET_BASE_URL` are all derived from it. A wrong value here produces dead links in every email that goes out. |
| `SKIP_DB_INIT=1` | See migrations above. Not strictly required to boot, but required to deploy safely on more than one worker. |

### Strongly recommended in production

| Variable | Why |
|---|---|
| `CORS_ORIGINS` | Comma-separated allowed browser origins, no trailing slash. Defaults to `APP_URL`. Never `*` — the app sends `allow_credentials=True`. |
| `AGENCY_NAME` | Agency name on reports and emails. Defaults to `InfyApp Development`. |
| `REPORT_ASSET_BASE_URL` | Public URL for report cover images, embedded in report emails. Must point at the **API's** `/api/reports/covers`, not a static directory. Defaults to `<APP_URL>/report-covers`, which the frontend does not serve — so leaving it unset gives every recipient a broken cover image. |
| `SUPPORT_EMAIL` | Footer "contact a human" address. Defaults to `info@infyappdevelopment.com` — **the client must override this.** |
| `UNSUBSCRIBE_URL` | Footer unsubscribe link. Defaults to `https://infyappdevelopment.com/unsubscribe` — **the client must override this.** |
| `DEBUG` | Leave unset/false. Setting it true exposes `/docs`, `/redoc`, `/openapi.json`, adds `http://localhost:5173` to the CORS list, and returns exception detail in 500 bodies. |

### Optional — each disables a feature when unset

| Variable | Effect when unset |
|---|---|
| `BREVO_API_KEY` | Email is not sent; messages queue in the `emails` table (dev outbox). |
| `EMAIL_FROM` | Falls back to `SEO Dashboard <no-reply@example.com>`. Must be a Brevo-verified sender in production. |
| `BREVO_WEBHOOK_SECRET` | `/api/webhooks/brevo` rejects everything, so the Email Log shows no delivery/open events. Intentional: the token in the URL is the only proof an event is genuine. |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USER` / `SMTP_PASS` / `SMTP_SECURE` | SMTP transport unused; falls back to the Brevo API. SMTP takes priority when `SMTP_HOST` is set. |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | GA4 and Search Console panels report "not configured" rather than crashing. Path to the service-account key file, relative to `server-python/`. **CONFIRM:** on Render the key file is not in git (it is gitignored) — upload it as a Render *Secret File* and point this variable at the secret-file path. |
| `MOZ_API_TOKEN` | Domain Authority panel disabled. |
| `MOZ_ACCESS_ID` / `MOZ_SECRET_KEY` | Legacy Mozscape credential pair; unnecessary if `MOZ_API_TOKEN` is set. |
| `EMAIL_LOGO_URL` | Defaults to `<APP_URL>/infapp-logo.png`. Must be publicly reachable — mail clients fetch it with no session. |
| `REPORT_ASSET_DIR` | Defaults to `server-python/assets/public`. Render's filesystem is ephemeral, so cover images written there are lost on restart; point it at a mounted disk if you need them to survive. |
| `PORT` | Render sets this. Only read as a fallback default of 4000. |

---

## Post-deploy smoke check

1. `GET /api/...` any authenticated route → expect 401, not 500 (proves the DB
   connected; a DB failure surfaces as a 500).
2. Sign in from the deployed frontend → proves `CORS_ORIGINS` and `JWT_SECRET`.
3. Invite a throwaway user → open the email and click the link → proves
   `APP_URL` and the Brevo transport.
4. **Export a report as PDF** → proves `playwright install chromium` actually
   ran. This is the step a clean deploy fails on, and nothing before it will
   warn you.
