# RankBoard — Project Overview (handoff brief)

> A single, self-contained brief on the RankBoard codebase. Read this to
> understand the whole system before touching any code. It reflects the code as
> it actually is, not aspirations.

---

## 1. What RankBoard is

RankBoard is a **multi-tenant SEO admin panel** for an agency (InfyApp). After
signing in, a user lands on a **Projects** list; opening a project reveals a
dashboard of SEO tools in a fixed left rail. The headline tool is the **Rank
Ledger** (keyword positions, previous vs. current). Around it sit **Traffic
(GA4)**, **Search Console**, **Backlinks**, **Domain Authority (Moz)**,
**Snapshots** (frozen monthly rank copies), and a **Report** builder that
generates a monthly client-facing SEO report and exports it to PDF.

The product is built as **one React frontend** that talks to a `/api/...`
contract, plus **three interchangeable backends** that each implement that same
contract. The frontend cannot tell which backend is answering.

| Layer            | Location                                    | Role |
|------------------|---------------------------------------------|------|
| React client     | `rankboard-admin/client/`                   | The only UI. Shared across all backends. |
| Node/Express     | `rankboard-admin/server/`                   | Original reference backend (core features only). |
| **Python/FastAPI** | **`rankboard-admin/server-python/`**      | **Most complete backend — where ALL work happens.** |
| PHP/Laravel      | `rankboard-admin/server-php/` (+ `-overlay/`) | Core-only port. **FROZEN — do not modify.** |

### ⚠️ Working rules (critical)
- **All changes happen in the Python backend** (`server-python/app/`). The PHP
  Laravel code (`server-php/`, `server-php-overlay/`) is **off-limits** — leave
  it exactly as it is.
- The Node and PHP backends implement only the *core* (auth, users, projects,
  rank ledger, Excel import). The **Python backend is far ahead**: it alone has
  snapshots, Moz, backlinks, GA4, Search Console, and the full report/PDF
  pipeline. So the three backends are **not** at feature parity today.
- The React client is shared; when a Python response shape changes, the client
  must stay in sync.

Only one backend can hold **port 4000** at a time (the Vite dev server proxies
`/api` there).

---

## 2. Tech stack

- **Frontend:** React 18 + Vite, Tailwind CSS, `lucide-react` icons, `recharts`
  for charts, `@tiptap/react` (ProseMirror) for the report prose editor.
- **Python backend:** FastAPI, raw SQL (no ORM), `bcrypt`, `PyJWT`,
  `google-analytics-data` + `google-api-python-client` (GA4/GSC),
  `openpyxl` (Excel), `playwright` (headless Chromium → PDF), `psycopg` v3
  (Postgres, optional).
- **Database:** SQLite by default; **Supabase Postgres** when `DATABASE_URL` is
  set. The app is written once in SQLite dialect; a bridge in `db.py` translates
  to Postgres at runtime (see §5).
- **Auth token:** JWT (HS256, 8h expiry) in the Python/Node backends; Laravel
  Sanctum in the PHP backend. Client stores it in `localStorage` and sends
  `Authorization: Bearer <token>`.

---

## 3. Directory map (Python backend)

```
server-python/app/
├── main.py                     # FastAPI app: routers, CORS, exception handlers, read-only middleware
├── config.py                   # env loading (.env), all settings + secrets
├── db.py                       # SQLite/Postgres connection + dialect bridge + schema + seed
├── permissions.py              # role→action matrix + role groups (AUTHOR/SENDER/DELETER)
├── access.py                   # per-project scoping (which projects a Client may see)
├── security.py                 # auth dependencies: require_auth / require_active_user / require_permission / require_roles / require_project_access
├── routers/
│   ├── auth.py                 # login, /me, set-password
│   ├── users.py                # People admin (onboard, resend invite, update role/projects, delete)
│   ├── projects.py             # projects CRUD + keywords + rank check + Excel + GA4 + GSC + snapshots
│   ├── moz.py                  # /projects/{id}/moz (cached) + /moz/refresh
│   ├── backlinks.py            # /projects/{id}/backlinks import/list/delete
│   ├── snapshots.py            # /snapshots/{id}/download (CSV)
│   └── reports.py              # report versions: generate/fork/delete/list/get/pdf/blobs/content
└── services/
    ├── rank_provider.py        # DataForSEO SERP live lookups OR simulated random walk
    ├── moz_provider.py         # Moz JSON-RPC domain authority fetch
    ├── analytics_provider.py   # GA4 Data API (dashboard traffic panel — never raises)
    ├── search_console_provider.py # GSC Search Analytics (dashboard panel — never raises)
    ├── email_service.py        # Resend API OR dev outbox (emails table)
    ├── excel_service.py        # .xlsx sample template + upload parser (openpyxl)
    ├── snapshot_service.py     # freeze the ledger into snapshots + snapshot_ranks
    ├── backlink_service.py     # month-wise backlink storage + report read-path
    ├── report_registry.py      # single source of truth: every report field, its source + type
    ├── report_google.py        # LIVE GA4+GSC fetch FOR REPORTS (raises on failure — classified)
    ├── report_service.py       # gather → validate → freeze pipeline; generate/fork/delete/content
    ├── report_blobs.py         # flatten frozen blob → insertable scalar "blobs" for the editor
    ├── report_document.py      # build the editable block document from a frozen report
    └── report_pdf.py           # block document → full multi-page HTML → PDF (Playwright)
```

Client screens (`client/src/screens/`): `Auth`, `Projects`, `AdminPanel`
(People), `Dashboard` (the tool shell + Rank Ledger + Snapshots + Traffic +
Search Console), `MozOverview`, `Backlinks`, `ReportEditor` (list + editors),
`ReportDocument` / `ReportDocumentEditor` (block-document editor). Shared bits:
`api.js` (fetch doorway), `ui.jsx` (design tokens, role helpers, `can()`),
`lib/blobFormats.js` (chip display formats), `lib/blobNode.jsx` (TipTap node).

---

## 4. Roles & permissions

Four roles are stored verbatim in `users.role`. The report workflow maps onto
these same four (there is exactly one role vocabulary):

| Stored role   | Spec name     | Capability summary |
|---------------|---------------|--------------------|
| `Super Admin` | admin         | Everything, incl. managing users. |
| `Admin`       | manager       | All projects; full project/keyword writes; authors reports; the only role that may (later) SEND reports. |
| `Team`        | team_member   | Sees all projects; **authors reports**; but **no** project/keyword/user write rights and cannot send. |
| `Client`      | user          | Scoped to assigned projects (`user_projects`); read-only. |

Two independent authorization mechanisms:

1. **Permission matrix** (`permissions.py` → `PERMISSIONS`): booleans for
   `manageUsers, addProject, toggleProject, deleteProject, addKeyword,
   deleteKeyword`. Enforced by `require_permission("addProject")`. Default-deny.
   The matrix row is also sent to the client via `/auth/me` so the UI knows
   which buttons to draw — but **the server re-checks every request**.
2. **Role groups** (for the report workflow, NOT in the matrix):
   - `AUTHOR_ROLES = {Super Admin, Admin, Team}` — may author reports & write backlinks.
   - `SENDER_ROLES = {Super Admin, Admin}` — may send a report (not built yet).
   - `DELETER_ROLES = {Super Admin, Admin}` — may hard-delete a report version.
   Enforced by `require_roles(*AUTHOR_ROLES)`.

**Important history:** "Team" used to be read-only and is now a write-capable
report author. Its matrix row is still all-`False` (no project/keyword writes);
its authoring power comes entirely from `require_roles(*AUTHOR_ROLES)`.
`READ_ONLY_ROLES` is now an **empty** set, so the method-based read-only
middleware in `main.py` is currently a no-op (kept wired for a future read-only
role).

**Per-project scoping** (`access.py`): staff (`Super Admin/Admin/Team`) see
every project; a `Client` sees only projects linked in the `user_projects` join
table. `require_project_access` guards every `/{project_id}/...` route.

**Auth dependency chain** (`security.py`):
- `require_auth` — decodes the JWT, **re-loads the user fresh from the DB** (so
  role changes / deletions apply immediately). Used only by `/me` &
  `/set-password`.
- `require_active_user` — adds "status must be active and no pending password
  change." Base for all data/action endpoints.
- `require_permission(action)` / `require_roles(*roles)` / `require_project_access`
  layer on top.
- `401` = we don't know who you are; `403` = we know and the answer is no.

---

## 5. Database (`db.py`)

Raw SQL, **no ORM**. One connection per request (`get_db` dependency),
**autocommit** on both backends (a deferred commit could let a client read stale
data — a real race they hit).

- **Default: SQLite** at `server-python/rankboard.db`.
- **Postgres** when `DATABASE_URL` looks like a Postgres URL (Supabase session
  pooler). `psycopg` is imported only then.
- **Dialect bridge:** the app is written entirely in SQLite SQL with `?`
  placeholders. `_PgConnection`/`_PgCursor`/`_Row` present the exact sqlite3
  surface (`.execute().fetchone()/.fetchall()/.lastrowid/.rowcount`, rows
  indexable by name and position). `_translate()` rewrites SQLite-isms:
  `datetime('now')`/`date('now')`/`strftime('%Y-%m','now')` → `to_char(...)`
  producing **identical text formats**; `INSERT OR IGNORE` → `ON CONFLICT DO
  NOTHING`; appends `RETURNING id` for `lastrowid`; `?` → `%s`.
- **Two schemas kept in parallel** — `SCHEMA` (SQLite) and `_PG_SCHEMA`
  (Postgres). ⚠️ **Any new table/column/index must be added to BOTH.**
- The SQLite path also runs "poor-man's migrations" (ALTER TABLE / table
  rebuilds) to evolve older local DBs; Postgres runs additively against an empty
  DB.

### Tables
- **users** — id, name, email (unique), role (CHECK in the 4 roles),
  password_hash, must_change_password (0/1), status (`invited`|`active`), created_at.
- **emails** — dev outbox (to_email, subject, body, sent_at). Every invite is logged here.
- **projects** — id, name, domain, `location_code` (DataForSEO country),
  `ga_property_id` (GA4), `gsc_site_url` (Search Console), active (0/1), created_at.
- **keywords** — project_id (FK cascade), term, current_rank, previous_rank
  (both nullable, CHECK ≥1), last_checked, created_at.
- **snapshots** — frozen point-in-time rank copies. NOT one-per-month: every
  save inserts a new immutable row, distinguished by `created_at` (full
  timestamp). `period_key`/`label` group by month for the UI.
- **snapshot_ranks** — per-snapshot frozen rows; the term/rank/last_checked are
  **copied in** (not referenced), so they survive later keyword edits/deletes.
- **moz_metrics** — one row per Moz refresh (history kept; newest shown). DA,
  linking_domains, inbound_links, spam_score, raw_json, fetched_at.
- **user_projects** — Client↔project links (UNIQUE(user_id, project_id)).
- **report_version** — one row per generated report version. `data_json`
  (FROZEN immutable data blob), `content_json` (EDITABLE block document),
  status (`draft`|`in_review`|`sent`), `parent_version_id` (fork lineage,
  SET NULL on delete), `rank_snapshot_id`, created_by, frozen_at.
- **backlinks** — per-project, month-wise (`month` = "YYYY-MM"),
  UNIQUE(project_id, month, url).

First-boot seed (idempotent): Super Admin `soham@infyappdevelopment.com` /
`admin123` (bcrypt-hashed), plus demo projects (Sattva Connect, Urban Bloom
Florists, Peak Performance Gym) and keywords.

---

## 6. API surface (Python)

All prefixed `/api`. Errors are always `{"error": "message"}` (client reads only
`data.error`). Router-level dependencies gate whole groups.

### Auth (`/api/auth`)
- `POST /login` → `{token, user}`. Generic failure message (no account enumeration).
- `GET /me` → `{user}` (with permission row). `require_auth`.
- `POST /set-password` → sets password, clears must_change, flips status→active.

### Users (`/api/users`) — all gated by `require_permission("manageUsers")`
- `GET ""` — list users (+ their projectIds).
- `POST ""` — onboard: validates name/email/role, validates any Client project
  assignments, creates the user with a crypto-random 10-char temp password
  (returned once in plaintext), sends invite email. 409 on duplicate email.
- `POST /{id}/resend-invite` — generates a NEW temp password (old hash is
  unrecoverable), re-emails. Only for `invited` users.
- `PATCH /{id}` — change role and/or project assignments. Guards: can't change
  your own role; can't demote the last Super Admin; project reassignment is a
  single transaction (delete-then-insert).
- `DELETE /{id}` — can't delete yourself.

### Projects & Rank Ledger (`/api/projects`) — router dep `require_active_user`
- `GET ""` — projects + keyword counts (per-client scoped).
- `GET /{id}` — project + its keywords. `require_project_access`.
- `POST ""` — create (`addProject`). Domain/GA/GSC normalized.
- `PATCH /{id}` — update active/domain/locationCode/gaPropertyId/gscSiteUrl
  (`toggleProject` + project access).
- `DELETE /{id}` — delete (`deleteProject`; keywords cascade).
- `POST /{id}/keywords` — add keyword (`addKeyword`).
- `PATCH /{id}/keywords/{kid}` — record new lookup: current→previous, new→current, stamp date.
- `DELETE /{id}/keywords/{kid}` — delete (`deleteKeyword`).
- `POST /{id}/check-ranks` — check every keyword via the rank provider
  (`addKeyword`). Uses per-project `location_code` or the server default.
- `GET /keywords/sample-template` — download the .xlsx template.
- `POST /{id}/keywords/bulk-import` — upload .xlsx (≤5MB), per-row validation,
  partial success (imports good rows, reports each bad row + reason), skips terms
  already tracked.
- **GA4 (POST, filters in body):** `/{id}/analytics`, `/{id}/analytics/breakdown`,
  `/{id}/analytics/report` (the "Explore" builder). All validate dimensions /
  metrics / operators against allowlists; never crash — errors come back as
  `{error}` in a 200.
- **GSC:** `GET /{id}/search-console` (totals/queries/pages/trend) and
  `POST /{id}/search-console/performance` (filtered performance report).
- **Snapshots:** `POST /{id}/snapshots` (freeze, `addKeyword`),
  `GET /{id}/snapshots` (list), `GET /{id}/snapshots/{sid}` (detail with frozen rows).

### Moz (`/api/projects/{id}`) — router dep `require_active_user`
- `GET /moz` — most recent stored row (never calls Moz).
- `POST /moz/refresh` — call Moz, store a new row, return it (`addKeyword` +
  project access). 502 on Moz failure, never 500.

### Backlinks (`/api/projects/{id}`)
- `POST /backlinks/import` — mass import a month's URLs (`AUTHOR_ROLES`).
  De-dupes per project+month.
- `GET /backlinks` — grouped by month (read; project access).
- `DELETE /backlinks/{bid}` — remove one (`AUTHOR_ROLES`).

### Snapshots export (`/api/snapshots`)
- `GET /{sid}/download` — CSV of a snapshot's frozen rows (per-project access
  checked via the snapshot's project).

### Reports (`/api/reports`) — every endpoint `require_roles(*AUTHOR_ROLES)` (delete uses `DELETER_ROLES`)
- `POST /generate` — gather→validate→freeze a new version. 409 if an unsent
  version already exists for that project+period (fork instead). 201.
- `POST /{id}/fork` — copy a version's frozen data + content verbatim into a new draft.
- `DELETE /{id}` — hard-delete (any status, incl. sent). `DELETER_ROLES`.
- `GET ""?projectId=` — list versions (metadata only).
- `GET /{id}` — one version incl. frozen data + editable content.
- `GET /{id}/pdf` — render the version to PDF (Playwright), stream it.
- `GET /{id}/blobs` — the scalar values insertable as chips in the editor.
- `GET /{id}/template-blocks` — canonical template blocks rebuilt from frozen
  data (to re-add a removed section).
- `PATCH /{id}/content` — save the editor's block document. **Draft-only** (409 if in_review/sent).

---

## 7. The swappable-provider pattern

Three services follow the same shape: **real transport when configured, a safe
fallback otherwise**, and callers only learn "it happened + the source."

- **`rank_provider`** — DataForSEO SERP Live API when `DATAFORSEO_LOGIN/PASSWORD`
  set (one POST per keyword, run concurrently; matches organic `rank_group` for
  the project's domain); otherwise a **simulated** random walk around the current
  rank. Returns `({term: rank|None}, source)`; `None` = not found in the checked
  depth (row left unchanged).
- **`email_service`** — Resend HTTP API when `RESEND_API_KEY` set; otherwise the
  dev outbox only. Either way the email row is logged (audit trail).
- **`moz_provider`** — Moz JSON-RPC (`data.site.metrics.fetch`) via `x-moz-token`.
  Raises `MozApiError` on any failure → router returns 502. No keyword-count
  (Moz has no working "count" method on this plan).

The two **dashboard** Google providers (`analytics_provider`,
`search_console_provider`) deliberately **never raise** — every failure becomes
`{"error": ...}` so a misconfigured project shows a friendly message. GA4 traffic
panel measures active users / new users / avg engagement (+ sessions); the
Explore builder allows arbitrary dimensions/metrics/filters (all allowlisted).

---

## 8. The report pipeline (the most complex feature)

Goal: produce a **frozen, versioned, editable, exportable** monthly SEO report.

### Data flow
1. **`report_service.gather()`** assembles an in-memory `blob` for a
   project+period ("YYYY-MM"):
   - **Ranks + keywords**: from the latest saved **snapshot** for that month
     (`snapshot_ranks`), with month-over-month deltas vs. the previous snapshot.
     No live rank call.
   - **Moz**: the `moz_metrics` row captured at/just-before the period end, with
     deltas vs. the prior refresh.
   - **GA4 + GSC**: **fetched LIVE from Google at generate time** (via
     `report_google.py`) for the report month AND prior month, then FROZEN.
   - **Backlinks**: the month's URLs from the `backlinks` table.
   - Each source records a `present` flag + human `reason` when absent.
2. **`report_service.validate()`** is now **LENIENT** — always `(True, None,
   200)`. A missing source is no longer fatal; it's flagged in the document.
   (Only hard blocks: 404 project-not-found, 409 duplicate unsent version.)
3. **`report_document.build_document()`** turns the frozen blob into an ordered
   **block document** (the editable `content_json`): header, progress-summary
   narrative, key-metrics grid, achievements, Moz grid, GA4 overview + 8 GA4
   tables, GSC grid + trend chart, keyword table, backlinks list, targets &
   strategy narratives. Block VALUES are seeded read-only from frozen data; only
   narrative prose/titles are editable. Narratives are **deterministic
   mail-merge (no LLM)**.
4. **`report_service.freeze()`** is the only writer: `data_json` (frozen) +
   `content_json` (editable document) → a new `report_version` row.

### Key concepts
- **`report_registry.py`** is the single source of truth for every field a report
  can carry: stable name, source (`snapshot_ranks`/`moz_metrics`/`keywords`/
  `ga4`/`gsc`), and display type (`count`/`duration`/`percent`/`rank`/`text`).
- **`report_google.py`** is separate from the dashboard providers because report
  generation must fail LOUDLY: `GoogleAccessError` (403/401/bad property → 422,
  "fix access") vs. `GoogleTransportError` (timeout/5xx/429 → 503, "retry").
  Under lenient validation these become flags, not hard failures.
- **Period logic**: a completed past month uses the full calendar month; the
  current in-progress month is fetched up to today and flagged "still maturing"
  (GA4 data matures ~48h). A future month has no data.
- **`report_blobs.py`** flattens the deeply-nested frozen blob into a flat list
  of insertable **scalar chips** (`{name, label, type, source, group,
  currentValue, deltaValue}`) — the one source the editor palette AND live
  preview consume.
- **Delta sign convention** (everywhere): deltas are raw `current − previous`.
  For **rank** types a NEGATIVE delta = improvement (position number shrank);
  for counts/percent/duration a POSITIVE delta = growth. `blobFormats.js` and
  `report_pdf.py` present direction without inverting the stored number.

### Editor (client)
`ReportEditor.jsx` + `ReportDocumentEditor.jsx` + `ReportDocument.jsx`:
TipTap-based. An author writes prose and inserts data "blobs" as atomic chips
(via a palette or `/` command), picks each chip's display format, sees a live
preview with chips resolved, and saves the TipTap JSON to `content_json` (not
rendered HTML — so reopening restores chips and resolution stays dynamic).
Draft-only editing; locked versions open read-only. A "finalize" gate is blocked
while any chip can't resolve. Generated reports carry a `report_document` block
and use the block editor; the legacy prose editor is only for pre-block drafts.

### PDF (`report_pdf.py`)
Renders the **full multi-page A4 report** (cover, TOC, all sections, running
footer, page numbers) as self-contained HTML — Poppins fonts + agency logo
embedded as base64 data URIs, brand palette, inline SVG for the GSC trend chart —
then converts to PDF via **Playwright headless Chromium**. Long sections
(GA4/keyword/backlinks tables) are **pre-paginated** in Python into fixed-size
page chunks. Values come from the already-seeded content blocks; nothing is
re-fetched. Must run in a sync context (it's a sync FastAPI handler → worker
thread, so the Playwright sync API is safe).

---

## 9. Configuration (`config.py`, env / `.env`)

Loaded from `server-python/.env` (KEY=VALUE, inline `#` comments after
whitespace stripped) without overriding already-set env vars.

- `JWT_SECRET` — **required, no fallback** (hard startup error if unset).
- `PORT` (4000), `APP_URL` (link in invite emails), `DEBUG` (gates `/docs`,
  `/redoc`, `/openapi.json` — off in prod), `CORS_ORIGINS` (allowlist, never `*`).
- `DATABASE_URL` — set → Supabase Postgres; unset → local SQLite.
- `RESEND_API_KEY`, `EMAIL_FROM` — email delivery.
- `MOZ_API_TOKEN` — Moz authority panel (empty = disabled).
- `DATAFORSEO_LOGIN` / `DATAFORSEO_PASSWORD` / `DATAFORSEO_BASE` (sandbox
  supported) / `RANK_LOCATION_CODE` (default 2356 = India) / `RANK_LANGUAGE` /
  `RANK_CHECK_DEPTH` (default 30).
- `GOOGLE_SERVICE_ACCOUNT_JSON` — one service account for BOTH GA4 & GSC; may be
  a file path (local dev) or the full JSON content (hosts like Render). Each
  project stores its own GA4 property id + GSC site url.

CORS in `main.py` always allows the deployed frontend
(`https://rankboard-1.onrender.com`) + local Vite (`http://localhost:5173`) plus
`CORS_ORIGINS`; it sits OUTERMOST so even a 403 carries CORS headers.

---

## 10. Run it

```bash
# Python backend
cd rankboard-admin/server-python
python -m venv .venv && .venv\Scripts\activate    # Windows
pip install -r requirements.txt
# set JWT_SECRET (required) in .env
cd .. && npm run dev:py                            # FastAPI :4000 + Vite :5173
```

- Frontend: http://localhost:5173 — sign in `soham@infyappdevelopment.com` / `admin123`.
- With `DEBUG=true`: interactive API docs at http://localhost:4000/docs.
- Delete `server-python/rankboard.db` to reset the local DB.
- `playwright install chromium` is needed for PDF (behind a TLS proxy here it
  needs `NODE_OPTIONS=--use-system-ca`).

---

## 11. Conventions & gotchas worth knowing

- **Client fetch doorway:** every call goes through `api()` in
  `client/src/api.js` (attaches the Bearer token, shapes errors). `can(user,
  action)` in `ui.jsx` reads the server-sent permission row — hiding a button is
  UX only; the server always re-checks.
- **camelCase API shapes:** DB is snake_case; routers convert to camelCase in
  `row_to_*` helpers (e.g. `currentRank`, `gaPropertyId`, `keywordCount`).
- **Purple "orange":** the Tailwind theme overrides `orange-*` to render PURPLE
  and `stone-*` to cool grays (`client/src/index.css` `@theme`). Class names say
  orange; the UI looks purple. This is intentional.
- **Both schemas:** any DB change must be mirrored in `SCHEMA` and `_PG_SCHEMA`
  in `db.py`.
- **Google providers never raise; report_google always classifies and raises** —
  don't conflate the two.
- **Autocommit is deliberate** — don't wrap handlers in deferred transactions
  (except the explicit `BEGIN/COMMIT` in the user project-reassignment path).
- **`npm install` fails on this machine** (TLS: `UNABLE_TO_VERIFY_LEAF_SIGNATURE`)
  — write code and edit `package.json`, but the human installs client deps.
- **PHP is frozen** — never edit `server-php/` or `server-php-overlay/`.

---

## 12. One-paragraph summary for a fresh Claude

RankBoard is an agency SEO admin panel: a shared React SPA plus three
interchangeable backends behind one `/api` contract. **Work only in the Python
FastAPI backend at `server-python/app/`; the PHP/Laravel backend is frozen.** It
uses raw SQL over SQLite (or Supabase Postgres via a dialect bridge in `db.py` —
mirror every schema change into both `SCHEMA` and `_PG_SCHEMA`). Four roles
(Super Admin/Admin/Team/Client) are enforced server-side via a permission matrix
plus report role-groups (`AUTHOR/SENDER/DELETER_ROLES`) and per-project scoping;
Team is a write-capable report author despite an all-False matrix row. Core
features: users/onboarding, projects, the Rank Ledger (DataForSEO or simulated),
Excel import, monthly snapshots, Moz authority, month-wise backlinks, GA4 &
Search Console panels. The flagship is the report pipeline: gather (snapshot
ranks + Moz + live-frozen GA4/GSC + backlinks) → lenient validate → build an
editable block document → freeze into `report_version` (frozen `data_json` +
editable `content_json`); authors edit prose and insert formatted data chips in
a TipTap editor; export is a full multi-page PDF via Playwright. Errors are
always `{"error": ...}`, tokens are 8h JWTs re-checked against the DB every
request, and the client mirrors server permissions purely for UX.
```
