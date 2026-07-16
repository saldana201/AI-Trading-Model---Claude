# Confluence — Headless CRUD Framework Upgrade

This package turns the gateway into a proper headless API (resource-style
REST + API key auth + worker-safe state) and mounts **Refine** — the headless
React framework for enterprise CRUD apps — inside your existing Next.js
dashboard at `/admin`. The main dashboard, engines, orchestrator, alert
lifecycle, and SSE feed are untouched.

Everything here was tested against your repo: **all 109 existing tests pass,
10 new phase-9 tests pass, `next build` succeeds, and both servers were
verified end-to-end** with synthetic data.

---

## What's in the zip

```
.gitignore                              REPLACE  framework-aware ignore rules
apps/api/main.py                        REPLACE  gateway v0.8.0 (see below)
apps/api/auth.py                        NEW      API key auth dependency
apps/api/resources/__init__.py          NEW      router registry
apps/api/resources/common.py            NEW      pagination/sort/filter dialect
apps/api/resources/trades.py            NEW      trades resource (list/get/patch)
apps/api/resources/events.py            NEW      audit trail (read-only)
apps/api/resources/watchlist.py         NEW      watchlist.json full CRUD
tests/test_phase9_resources.py          NEW      10 tests for auth + resources
apps/web/package.json                   REPLACE  adds @refinedev/core + router
apps/web/lib/confluence.js              NEW      data + auth providers (glass box)
apps/web/app/admin/layout.jsx           NEW      server segment config
apps/web/app/admin/refine-shell.jsx     NEW      client <Refine> mount
apps/web/app/admin/page.jsx             NEW      trades table (useTable)
apps/web/app/admin/watchlist/page.jsx   NEW      watchlist CRUD (useList/Create/…)
apps/web/app/admin/login/page.jsx       NEW      API key entry (useLogin)
```

## How to apply

From the repo root (`AI Trading Model - Claude`), PowerShell or Git Bash:

```bash
# 1. Unzip over the repo root — paths line up 1:1
#    (only .gitignore, apps/api/main.py, apps/web/package.json are overwritten)

# 2. Purge the tracked build output / DBs the old .gitignore let in
git rm -r --cached apps/web/.next dashboard/.next 2>/dev/null
git rm --cached alerts.db alerts.jsonl 2>/dev/null
git add -A && git commit -m "Headless CRUD upgrade: auth, resource REST, Refine admin"

# 3. Backend deps are unchanged. Frontend needs the Refine packages:
cd apps/web && npm install

# 4. Run it
#    terminal 1 (repo root):
CONFLUENCE_DATA=synthetic CONFLUENCE_API_KEY=dev-secret uvicorn apps.api.main:app --port 8000
#    terminal 2:
cd apps/web && npm run dev
#    then open http://localhost:3000/admin  (enter dev-secret at the login)

# 5. Verify
python -m pytest tests/            # 119 tests
```

## Gateway changes (apps/api/main.py, v0.7.0 -> v0.8.0)

1. **Auth** (known issue #3). `CONFLUENCE_API_KEY` set → `POST /api/chat`,
   `POST /api/alerts/arm|tick`, and everything under `/api/resources/*`
   require `X-API-Key: <key>` or `Authorization: Bearer <key>` (constant-time
   compare). Unset → auth disabled with a logged warning, so local dev flow
   is unchanged. `/api/health` now reports `"auth": "api_key" | "disabled"`.

2. **Worker-safe state**. The lazily-mutated module-level `_state` dict is
   now built explicitly in the lifespan handler and lives on
   `app.state.confluence`; endpoints receive it via dependency injection.
   `get_state()` remains as a back-compat accessor (your phase 6/7 tests and
   any scripts keep working). Honest caveat: caches and the SSE broadcaster
   are still in-process, so `--workers N` gives each worker its own — run one
   worker until a Redis-backed layer exists.

3. **Resource REST** for admin frameworks. Every list endpoint speaks the
   simple-REST dialect Refine consumes natively:
   `_start/_end` pagination, `_sort/_order`, `field=value` equality filters,
   and the pre-pagination total in an `X-Total-Count` header (exposed via
   CORS). Resources:

   - `trades` — the lifecycle store. PATCH only allows terminal states
     (manual close) plus a note; non-terminal transitions stay the engine's
     job, and every manual change writes a `manual_update` audit event. No
     DELETE — trades are an audit trail. Glass-box constraint preserved.
   - `events` — read-only audit log, filterable by `trade_id`.
   - `watchlist` — full CRUD over `watchlist.json` (env
     `CONFLUENCE_WATCHLIST` overrides the path). Symbols are validated,
     upper-cased, and deduped; responses say explicitly that edits apply on
     the next snapshot rebuild.

4. **Config over hardcoding**. CORS origins come from
   `CONFLUENCE_CORS_ORIGINS` (comma-separated; defaults to localhost:3000).

## Frontend: Refine at /admin

Refine is headless — it contributes data fetching, caching, mutation
invalidation, and the auth flow via hooks; every pixel uses your existing
Confluence design system from `globals.css`. Notes:

- `lib/confluence.js` is a hand-written ~70-line data provider (plus auth
  provider) instead of `@refinedev/simple-rest`, so the entire HTTP contract
  is inspectable in one file and there's no axios dependency. Same
  philosophy as the engines.
- The API key is entered once at `/admin/login`, verified against a real
  resource call, kept in localStorage, and sent as `X-API-Key`. Any 401
  bounces back to login. If the gateway reports auth disabled, login is
  skipped entirely.
- `app/admin/layout.jsx` is a thin server component that forces dynamic
  rendering (Refine's router reads search params at runtime, which Next 14
  can't statically prerender) and wraps the client-side `refine-shell.jsx`
  in Suspense. If you ever see a `useSearchParams()` prerender error on a
  new admin page, this layout is why existing ones don't.
- Packages: `@refinedev/core@^5` and `@refinedev/nextjs-router@^7`. v5 hook
  shapes are used throughout (`result`/`tableQuery`, `currentPage`,
  `mutation.isPending`) — don't mix in v4-era snippets from older blog posts.

## Why this direction

Your backend was already the "headless" part — the composable piece other
apps can integrate. This upgrade makes that real: any client (Refine today,
a mobile app, another team's tool, an MCP wrapper) can now consume the same
authenticated, conventional REST surface. The frontend framework became a
swappable choice instead of a hand-rolled dependency.

## Follow-ups this deliberately does not include

- Consolidating the duplicate `scripts/` vs `dashboard/scripts/` trees and
  retiring the old `dashboard/` frontend (delete after confirming `apps/web`
  covers it).
- Swapping raw sqlite3 in `alerts/store.py` for SQLModel/SQLAlchemy so the
  TimescaleDB note in its docstring becomes a connection-string change.
- Rate limiting (slowapi is the natural fit once auth is in).
- Intraday data and the ticker-extraction rewrite — unchanged priorities.
