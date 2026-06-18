# RankBoard — Admin Panel (full stack)

A real three-tier application: React frontend, Express API, SQLite database.

The main website: after signing in, every role lands on the Projects page
(add / activate / deactivate / delete, gated by role). Opening a project shows
its dashboard with a fixed left nav of SEO tools — first tool: the Rank Ledger
(keywords, previous vs. current position, add/remove). The Super Admin also has
the People page to onboard users (add person → choose role → invite email with
a temporary password); invited people set their own password on first sign-in.

Role permissions live in ONE file — `server/src/permissions.js` — enforced on
every API request and mirrored to the UI via `/api/auth/me`. Team and Client
rules are provisional (Team: keywords only; Client: read-only) until decided.

## Requirements

- Node.js 22.13+ — check with `node -v` (SQLite is built into Node now, so there are no native dependencies to compile)

## Run it

```bash
npm install        # installs the root dev tool (concurrently)
npm run setup      # installs server + client dependencies
npm run dev        # starts API on :4000 and the web app on :5173
```

Open http://localhost:5173

First boot creates `server/rankboard.db` and seeds a Super Admin:

```
soham@infyappdevelopment.com / admin123
```

Delete `server/rankboard.db` any time to start completely fresh.

## Try the full loop

1. Sign in as the Super Admin.
2. "Onboard someone" → name, email, role → Create & send invite.
3. The composed invite email appears with a server-generated temporary password
   (shown once — only its hash is stored).
4. Sign out, sign in with the new person's email + temp password.
5. You're forced to set a real password; the account flips Invited → Active.

## Architecture

```
Browser (React, :5173)
   │  fetch /api/...  (Vite proxies to :4000 — no CORS needed in dev)
   ▼
Express API (:4000)
   │  routes → middleware (JWT auth, role checks) → handlers
   ▼
SQLite (server/rankboard.db)
   users, emails tables — the single source of truth
```

Key files, in the order a request flows:

| File | Job |
|---|---|
| `client/src/api.js` | One doorway to the backend; attaches the JWT |
| `client/src/App.jsx` | Screens render server state; mutations refetch |
| `server/src/index.js` | Express wiring + central error handler |
| `server/src/middleware/auth.js` | requireAuth (who are you) / requireRole (are you allowed) |
| `server/src/routes/auth.routes.js` | login, /me, set-password |
| `server/src/permissions.js` | the role matrix + requirePermission guard |
| `server/src/routes/users.routes.js` | user management (manageUsers permission) |
| `server/src/routes/projects.routes.js` | projects + Rank Ledger keywords |
| `server/src/services/email.service.js` | invite emails (dev outbox → swap for a real provider) |
| `server/src/db.js` | schema, constraints, seed |

## Security notes (what's real now)

- Passwords are **bcrypt-hashed** — plain text is never stored. That's why
  "resend invite" generates a *new* temp password: the old one is unrecoverable.
- Roles are enforced **on the server** for every request. Hiding buttons in the
  UI is courtesy; `requireRole` is the law.
- All SQL uses **parameterized queries** (`?` placeholders) — no SQL injection.
- Login failures return one generic message — no account enumeration.
- JWTs expire after 8h; the user is re-loaded from the DB on every request, so
  role changes and deletions apply immediately.

## Automatic rank checks (DataForSEO) — Python backend

The Rank Ledger has a "Check rankings" button that looks up every keyword's
Google position for the project's domain and records the lookup (current
becomes previous, date stamps). It runs through a swappable provider:

- **No credentials set (default):** free simulated mode — random-walk numbers,
  clearly labeled in the UI. Lets you demo the feature without an account.
- **Credentials set:** real lookups via DataForSEO's SERP API (Live mode).

```bash
DATAFORSEO_LOGIN=you@example.com DATAFORSEO_PASSWORD=your_api_password npm run dev:py
```

Setup notes:
- Sign up at dataforseo.com (pay-as-you-go: prepaid balance, no subscription;
  new accounts get a small free credit, minimum top-up applies). Your API
  password is in their dashboard, not your account password.
- Test for free against mock data by also setting
  `DATAFORSEO_BASE=https://sandbox.dataforseo.com`.
- A project must have a **domain** for real checks — set it when creating the
  project, or `PATCH /api/projects/:id {"domain": "yoursite.com"}`.
- Tuning via env vars: `RANK_LOCATION_CODE` (default 2356 = India),
  `RANK_LANGUAGE` (default en), `RANK_CHECK_DEPTH` (default 30 = top 30
  results; billing is per page of 10, so deeper costs more per check).
- Cost shape (verify current rates on their pricing page): Live mode is a few
  tenths of a US cent per results page, so one project of 25 keywords at
  depth 30 costs roughly half a US cent per check. Their Standard queue is
  ~3x cheaper but asynchronous — a good upgrade once a scheduled job exists.
- Keywords not found within the checked depth are reported and left unchanged.

## PHP backend (Laravel) — optional, interchangeable

A third backend implementing the exact same API contract, in PHP with
Laravel. The React client is untouched — it cannot tell which backend
is answering.

Application code lives in `server-php-overlay/`; you generate the
Laravel skeleton with Composer on your machine and copy the overlay on
top. Full step-by-step (including installing PHP via Laravel Herd on
Windows): **server-php-overlay/SETUP-PHP.md**.

Once set up: `npm run dev:php` starts Laravel on port 4000 + the React
dev server, same as `dev` (Node) and `dev:py` (Python).

## Python backend (optional, interchangeable)

The same React client also runs against a Python/FastAPI backend in
`server-python/` — same endpoints, same JSON shapes, same status codes, same
permission matrix. The frontend cannot tell them apart.

```bash
cd server-python
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cd ..
npm run dev:py                   # FastAPI on :4000 + web app on :5173
```

Requires Python 3.11+. SQLite comes from Python's standard library, so like
the Node server there are no native dependencies. Bonus: open
http://localhost:4000/docs for interactive API documentation generated from
the code — every endpoint, testable in the browser.

Pick whichever backend you'd rather maintain; both stay in the repo and both
honor the same contract. Delete `server-python/rankboard.db` to reset it.

## Enable real email sending

Out of the box, invites go to a dev outbox (the `emails` table) so the app
works with zero accounts or keys. To actually deliver them:

1. Create a free account at https://resend.com and generate an API key.
2. Start the server with the key:
   ```bash
   RESEND_API_KEY=re_your_key npm run dev
   ```
3. Deliverability reality: until you verify your own domain (Resend gives you
   SPF + DKIM DNS records to add), you can only send from their shared test
   address and only to the email you signed up with. After domain verification
   you can send from no-reply@yourdomain.com to anyone. Optionally set
   `EMAIL_FROM="RankBoard <no-reply@yourdomain.com>"`.

Every send is still logged to the outbox table either way, so you keep an
audit trail of what was sent to whom.

## Production upgrades, when you're ready

- **Postgres/MySQL**: the schema and queries translate almost 1:1; swap
  better-sqlite3 for `pg`, make handlers async.
- **Secrets**: set `JWT_SECRET` (and `APP_URL`, `PORT`) as environment
  variables. Never ship the dev fallback.
- **Token storage**: move the JWT from localStorage to an httpOnly cookie to
  harden against XSS.
- **HTTPS + rate limiting** on the login route.
