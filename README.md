# RankBoard — SEO reporting dashboard

An agency tool for producing monthly SEO reports for client websites. It pulls
the numbers it can pull automatically, lets the team enter by hand the numbers
nobody can pull automatically, assembles the result into a designed report,
renders it to PDF, and emails it to the client — then tracks whether the email
was actually delivered and opened.

## What it does

**Per project (= one client website):**

- **Traffic — Google Analytics 4.** Sessions, users, channel groupings and
  trends, via the GA4 Data API. Each project stores its own GA4 property ID.
- **Search — Google Search Console.** Clicks, impressions, CTR, average
  position, plus query and page breakdowns. Each project stores its own GSC
  site URL; the app can auto-resolve which verified property matches a domain.
- **Authority — Moz.** Domain Authority / Page Authority, fetched only on an
  explicit refresh because the API quota is small.
- **Keyword ranks — entered by hand.** There is no rank-tracking API in this
  app. Positions are typed into the Keywords grid or bulk-loaded from a
  spreadsheet, and snapshotted per period so month-over-month movement is real
  history rather than a re-query.
- **Backlinks and published posts — entered by hand**, with spreadsheet import.

**Reports.** The per-period data above is composed into a report document
(editable rich text alongside the generated charts and tables), rendered to PDF
with a full-bleed designed cover page, and emailed to the project's recipient
list.

**Email log.** Every message the system sends is recorded. If Brevo webhooks are
configured, delivery / open / click / bounce / spam / unsubscribe events are
ingested and rolled up against the original send, so "did the client get the
report" has an answer.

**Accounts.** Four roles — Super Admin, Admin, Team, Client — with clients
scoped to only the projects they are assigned. Sign-in supports emailed one-time
codes and TOTP two-factor with backup codes. Login and OTP endpoints are
IP-rate-limited.

## Architecture

```
client/            React 18 + Vite 5 + Tailwind 4  →  static site
  src/api.js       talks to the API at VITE_API_BASE_URL

server-python/     FastAPI + Uvicorn                →  web service
  app/main.py      app assembly, CORS, error handlers, router mounting
  app/config.py    every environment variable, read once at import
  app/db.py        psycopg 3 + connection pool; schema DDL and seed
  app/routers/     HTTP layer (auth, users, projects, moz, backlinks,
                   posts, reports, email-log, webhooks)
  app/services/    the actual logic — Google providers, Moz, report
                   assembly, PDF rendering, email, throttling, TOTP
  scripts/         one-off operational tools (see below)
  tests/           pytest suite, no database required

Postgres (Supabase)   all persistence
Playwright/Chromium   headless HTML → PDF for report export
Brevo                 transactional email + delivery/open webhooks
```

Both halves deploy as separate services. See
[`server-python/DEPLOY.md`](server-python/DEPLOY.md).

## Prerequisites

- **Python 3.11+** and **Node 18+**
- A **Postgres database** — Supabase in production. There is no SQLite mode;
  see gotchas.
- Optional but needed for the corresponding features: a Google **service
  account** with access to the GA4 property and the Search Console property, a
  **Moz** API token, and a **Brevo** account for email.

## First-time setup

### Backend

```bash
cd server-python
python -m venv .venv
# Windows:  .venv\Scripts\activate
# macOS/Linux:  source .venv/bin/activate

pip install -r requirements.txt -r requirements-dev.txt
playwright install chromium          # required — see gotchas

cp .env.example .env                 # then fill it in
```

At minimum `.env` needs `DATABASE_URL` and `JWT_SECRET`; the app refuses to
start without either, deliberately, so a misconfigured server fails at boot
rather than at the first request. `server-python/.env.example` documents every
variable the backend reads, which one disables which feature, and which
defaults are InfyApp-specific and must be changed.

The database schema is created automatically on first start (`init_db()` runs
idempotent DDL plus a seed pass) — nothing to run by hand locally.

### Frontend

```bash
npm run setup                        # from the repo root: installs client deps
cp client/.env.example client/.env   # set VITE_API_BASE_URL
```

Leave `VITE_API_BASE_URL` empty for local development and the client will call
same-origin paths; point it at the deployed API URL for a production build.

## Running in development

From the repo root:

```bash
npm run dev:py     # API on :4000 (reload) + Vite dev server on :5173, together
```

or separately:

```bash
npm run api:py                  # API only, with --reload
npm run dev --prefix client     # Vite only
```

Set `DEBUG=true` in `server-python/.env` while developing: it enables `/docs`,
`/redoc` and `/openapi.json`, allows the `http://localhost:5173` CORS origin,
and includes exception detail in 500 responses. Leave it off in production.

## Tests

```bash
cd server-python
pytest
```

`pytest.ini` handles the paths. The suite opens no database connection — the
units under test take a connection as an argument and each test supplies a fake;
`tests/conftest.py` sets the environment variables `app.config` and `app.db`
demand at import time.

## Build and deploy

```bash
npm run build:web     # client → client/dist  (static site)
npm run start:api     # production Uvicorn: 0.0.0.0, $PORT, 2 workers, proxy headers
```

Full Render deployment instructions — build command, start command, the
required-vs-optional environment variable list, the migration story, and the
post-deploy smoke test — are in
**[`server-python/DEPLOY.md`](server-python/DEPLOY.md)**.

## Environment variables

There are two `.env` files and they do not overlap:

- `server-python/.env` — everything the API reads. Copy from
  `server-python/.env.example`, which is the authoritative, commented list.
  Read at import by `app/config.py` using `os.environ.setdefault`, so a real
  environment variable always wins over the file. In production set them in
  the host's dashboard and don't ship a `.env` at all.
- `client/.env` — one variable, `VITE_API_BASE_URL`, baked in at **build**
  time by Vite. Changing it requires a rebuild, not a restart.

Neither `.env` is committed. Both `.env.example` files are.

The two variables that most often go wrong in a fresh deployment are `APP_URL`
(every emailed link is built from it — get it wrong and every invite is a dead
link) and `REPORT_ASSET_BASE_URL` (must point at the API's
`/api/reports/covers`, not the frontend, or every report email has a broken
cover image).

## Operational scripts

`server-python/scripts/` holds one-off tools, run with the venv active from the
`server-python/` directory. Notably:

- `verify_google_data.py` — re-queries GA4 / Search Console directly and prints
  the raw numbers. This is what you run when a client disputes a figure in a
  report.
- `list_routes.py`, `check_route_guards.py` — dump the route table and check
  every route has an auth guard.
- `poll_brevo_events.py`, `rebuild_email_rollups.py` — email-log maintenance,
  for backfilling when the webhook was down.
- `force_admin_reset.py` — recover a locked-out admin account.
- `check_gsc.py`, `fix_gsc_site_urls.py`, `compare_channel_groups.py`,
  `dedupe_keywords.py`, `backfill_ranks_from_snapshots.py`,
  `check_keyword_index.py`, `drop_location_columns.py` — targeted data fixes.

## Gotchas

- **`playwright install chromium` is a required install step.** `pip install`
  brings in the Playwright Python bindings but not the browser binary. Skip it
  and everything works until the first PDF export, which fails with an
  "executable doesn't exist" error. It belongs in the deploy build command, not
  just in local setup.
- **The app is Postgres-only, despite appearances.** Parts of the code carry
  `sqlite3`-flavoured naming and type hints left over from an earlier
  incarnation. They're cosmetic. `app/db.py` requires `DATABASE_URL` and
  rejects any URL that isn't Postgres; there is no file-backed mode to fall
  back on.
- **`SKIP_DB_INIT=1` on multi-worker deployments.** `init_db()` runs at import
  in *every* worker process. The DDL is idempotent but concurrent workers race
  on it. Run the schema pass as its own deploy step. See DEPLOY.md.
- **`--proxy-headers` matters behind a proxy.** Rate limiting keys off
  `request.client.host`. Without it, every request looks like it came from the
  platform's proxy IP and all users share one throttle bucket.
- **Backups are Supabase's automated ones — nothing in this repo backs anything
  up.** Retention depends on your Supabase plan tier, and point-in-time recovery
  is a paid add-on. Confirm what your project actually has before assuming a
  restore is possible.
- **Report cover images are written to disk** (`REPORT_ASSET_DIR`). On a host
  with an ephemeral filesystem they disappear on restart; use a persistent disk
  if old report emails need to keep rendering their covers.
- **Never set `CORS_ORIGINS=*`.** The API sends `allow_credentials=True`.
- **Trailing slashes break things.** `APP_URL` and `CORS_ORIGINS` must have
  none: an origin with a trailing slash never matches a browser `Origin` header,
  and `APP_URL` gets paths concatenated onto it.
