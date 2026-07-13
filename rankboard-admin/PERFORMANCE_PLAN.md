# RankBoard Admin — Performance Optimization Plan

_Profiling-first analysis of why the app feels slow, with a prioritized, low-risk fix sequence. No application code has been changed yet (except the already-approved report page-break fix)._

## The short version

The slowness comes from a handful of concrete, fixable causes rather than one broken thing:

- **Report generation is slow** because ~25–30 external API calls (GA4, GSC, Moz, ranks) run **one after another** instead of in parallel, and each report **re-fetches** everything with no caching.
- **PDF download is slow** because it launches a **brand-new headless Chromium browser on every download** (2–10s of pure startup each time).
- **Every write request is slower than it needs to be** because a blocking database query runs inside the async middleware on each POST/PUT/PATCH/DELETE.
- **The report editor lags while typing** because each keystroke re-serializes the whole document and re-renders every block and the preview pane.
- **Large tables and charts jank** because keyword/GA4 tables render every row with no virtualization and Recharts re-renders on every filter change.

None of these require a rewrite. They're targeted changes.

## Prioritized fix list

Ranked by impact ÷ effort. "Effort" is rough dev time.

| # | Fix | Where | Symptom it fixes | Impact | Effort |
|---|-----|-------|------------------|--------|--------|
| 1 | Parallelize external API fetches (GA4/GSC + the 7 GA4 breakdowns) | `report_google.py`, `analytics_provider.py` | Report generation & dashboard load | **High** — 15–30s → 3–6s | Med |
| 2 | Reuse one Chromium instead of launching per PDF | `report_pdf.py:1304` | PDF download | **High** — save 2–10s/download | Med |
| 3 | Fix blocking DB query in async write-middleware | `main.py:90-101` | Every write feels laggy | **High** | Low |
| 4 | Memoize editor preview + block renders; stop full re-serialize per keystroke | `ReportEditor.jsx`, `ReportDocumentEditor.jsx` | Typing lag in editor | **High** | Med |
| 5 | Memoize Recharts data + chart components | `Dashboard.jsx` | Chart jank on filter/tab change | **Med-High** | Low |
| 6 | Virtualize large tables (keywords, GA4 rows) | `Dashboard.jsx` | Slow scroll on big lists | **Med-High** | Med |
| 7 | Connection pooling for DB (esp. Supabase/Postgres) | `db.py:490-536` | Baseline latency on every request | **Med** | Med |
| 8 | HTTP connection reuse for DataForSEO / Moz | `rank_provider.py`, `moz_provider.py` | Rank check speed | **Med** | Low |
| 9 | Cache GA4/GSC/Moz results with short TTL | `report_service.py` | Accidental re-generates | **Med** | Med |
| 10 | Batch snapshot inserts with `executemany()` | `snapshot_service.py:70-76` | Snapshot creation | **Low-Med** | Low |
| 11 | Route-based code splitting / lazy load screens | `App.jsx`, `vite.config.js` | Initial page load | **Med** | Low |
| 12 | Add missing DB indexes | `db.py` | Scales at many projects | **Low** | Low |

## Detail by symptom

### "Generating a report takes forever"

The dominant cost is serial network I/O. In `report_google.py`, `fetch_ga4()` runs a 10-call GA4 sequence for the current month, then repeats the whole sequence for the prior month, then `fetch_gsc()` runs its calls — all sequentially (`report_service.py` `gather()`). Each call is ~0.5–1s, so a single generation is ~25–30 calls ≈ 15–30s.

Fix: run independent calls concurrently (`asyncio.gather`, or the existing thread-pool pattern already used in `rank_provider.py`). Current vs. prior month are independent; the 7 GA4 breakdowns in `analytics_provider.py` are independent. Parallelizing typically cuts this to the duration of the slowest call plus overhead — roughly 3–6s. Add a short-TTL cache so a double-click doesn't re-run everything.

### "Downloading the PDF is slow"

`render_pdf()` (`report_pdf.py:1304`) calls `p.chromium.launch()` every single time, which spins up a fresh browser process (~2–10s) before rendering. Fix: keep one long-lived browser (or a small pool) and open a fresh *page* per render. This removes almost all the per-download startup cost. (Note: the report HTML/pagination itself is fine — the page-break fix is already in.)

### "Everything feels a bit laggy, especially saving/editing"

`main.py` runs `_role_for_request()` — a synchronous `get_connection()` + SELECT — inside the async `block_read_only_writes` middleware on every write. Synchronous DB I/O inside an async handler stalls the event loop. Fix options: cache the role on the auth token/short-lived cache, run the check in a threadpool, or fold it into the existing auth dependency instead of middleware.

Combined with no DB connection pooling (`db.py` opens and closes a connection per request), every request pays avoidable overhead — worse against Supabase/Postgres where each connect is a network round-trip. Fix: a connection pool.

### "The report editor is sluggish while typing"

Each keystroke calls `editor.getJSON()` and `setDoc()`, re-serializing the whole document and re-rendering all blocks plus the preview pane (`ReportEditor.jsx`, `ReportDocumentEditor.jsx`), which walks the entire node tree with no memoization. Fixes: `React.memo` the block editors and preview, `useMemo` the derived work (e.g. `findUnresolved`), and debounce autosave/serialization so it doesn't fire on every character.

### "Charts and big tables stutter"

Recharts data arrays are rebuilt inline on every render, so charts re-render even when data is unchanged; keyword and GA4 tables render every row (up to 250+/thousands) with no virtualization. Fixes: `useMemo` chart data and memo the chart components; add row virtualization (e.g. `react-window`) to the large tables.

## Suggested sequencing

**Phase 1 — biggest wins, lowest risk (do first):** #3 (middleware), #5 (chart memo), #10 (batch inserts), #12 (indexes), #11 (lazy load). Mostly small, safe, immediately noticeable.

**Phase 2 — high-impact, moderate work:** #1 (parallelize fetches) and #2 (reuse Chromium). These are the two changes that make generation and PDF feel fast.

**Phase 3 — editor & tables:** #4, #6 — the front-end responsiveness work.

**Phase 4 — infrastructure:** #7 (pooling), #8 (HTTP reuse), #9 (caching).

## Notes / risks

- #1 and #2 need testing against real API credentials and a real multi-page report to confirm no regressions (parallel fetches can surface rate limits; browser reuse needs clean page teardown to avoid leaks).
- #7 pooling behaves differently for SQLite vs. Supabase/Postgres — the pool config should match the deployment target.
- The Node `server/` and `server-php/` directories appear to be alternate/legacy backends; this plan targets the active Python/FastAPI backend.
