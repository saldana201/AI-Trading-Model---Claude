# Confluence — Phase 9 + Phase 13

Two upgrades in one verified package, built against your **clean** repo
(commit `611180d`, 112 tracked files).

**Phase 9 — headless CRUD.** API key auth, resource-style REST, and a Refine
admin at `/admin`. This is the upgrade that was written but never applied.

**Phase 13 — make the assistant reachable.** Phase 12 shipped position
sizing, trade plans, and exit advice, but the two UI panels were never
rendered and chat had no tools for any of it. Now it does.

Verified: **184 tests pass** (160 existing + 13 Phase 9 + 11 Phase 13), and
auth, the resource endpoints, and the chat intents were exercised against a
running gateway.

---

## What's in the zip

```
upgrade/
  apps/api/
    main.py                          MODIFIED  v0.8.0 (6 surgical edits, see below)
    auth.py                          NEW       API key dependency
    resources/__init__.py            NEW       drift-safe install() + CORS origins
    resources/common.py              NEW       simple-REST dialect
    resources/trades.py              NEW       list/get/patch (terminal-only writes)
    resources/events.py              NEW       read-only audit trail
    resources/watchlist.py           NEW       full CRUD incl. pinned
  orchestrator/
    chat.py                          MODIFIED  3 assistant tools, both chat modes
  apps/web/
    package.json                     MODIFIED  adds @refinedev/core + nextjs-router
    app/page.jsx                     MODIFIED  renders <Assistant/> and <Settings/>
    lib/confluence.js                NEW       hand-written data + auth provider
    app/admin/layout.jsx             NEW       dynamic segment + Suspense
    app/admin/refine-shell.jsx       NEW       client <Refine> mount
    app/admin/page.jsx               NEW       trades table
    app/admin/watchlist/page.jsx     NEW       watchlist CRUD
    app/admin/login/page.jsx         NEW       API key entry
  tests/
    test_phase9_resources.py         NEW       13 tests
    test_phase13.py                  NEW       11 tests
```

`main.py` is **modified, not replaced** — the six edits are listed at the
bottom so you can diff them. Replacing that file wholesale is what destroyed
Phase 10/11 last time; it won't happen again.

## Applying

```bash
# from the repo root — paths line up 1:1
cp -r upgrade/* .

python3 -m pytest tests/ -q          # expect 184 passed

cd apps/web && npm install           # pulls the two Refine packages
```

Run it:

```bash
# terminal 1 (repo root)
CONFLUENCE_DATA=synthetic CONFLUENCE_API_KEY=dev-secret \
  uvicorn apps.api.main:app --port 8000

# terminal 2
cd apps/web && npm run dev
```

Then `http://localhost:3000` for the dashboard (Assistant + Settings panels
now visible) and `http://localhost:3000/admin` for the CRUD surface (enter
`dev-secret`).

---

## Phase 13 — what you can now ask

The three questions your original request was about, answered in chat with
every number traced to engine evidence:

```
Q: how many shares of AVGO should i buy
A: 31 shares of AVGO (capped by your max position limit): entry 196.9,
   stop 192.86, 4.04 risk per share = $125.24 total, $6103.9 position.

Q: what is my plan for AVGO
A: AVGO long — 31 shares ($125.24 at risk). Buy stop 196.9, protective
   stop 192.86, trim 15 at 201.96 then stop to breakeven, run 16 to 205.33.

Q: what do i do with my AVGO position
A: AVGO at 193.75: HOLD — stop 192.86, next objective 201.96.

Q: what do i do with my ZZZZ position
A: No composed setup for ZZZZ right now, so there are no engine levels to
   manage against. Without a validated stop and targets I'd be inventing
   numbers — name a symbol that's in today's setups, or arm it first.
```

That last one is the anti-hallucination invariant holding at the chat layer,
and there's a test asserting no `$` figure appears in that reply.

Three new tools (`size_position`, `get_trade_plan`, `advise_open_trade`) are
registered in `EngineToolbox.SPECS` for LLM tool-use mode **and** wired into
the deterministic router, so they work without an API key. The exit intent is
matched *before* the old generic "stop" branch, which would otherwise swallow
"what do I do with my position" and answer with just a stop level.

**The two dead panels are now rendered.** `Assistant.jsx` and `Settings.jsx`
existed since Phase 12 but were never imported into `page.jsx` — the entire
user-facing half was invisible. `test_phase13.py` asserts both are imported
*and* rendered, so this can't silently regress.

---

## Phase 9 — the gateway

1. **Auth.** `CONFLUENCE_API_KEY` set → `POST /api/chat`,
   `POST /api/alerts/arm|tick`, and everything under `/api/resources/*`
   require `X-API-Key` or `Authorization: Bearer` (constant-time compare).
   Unset → disabled with a logged warning, so local dev is unchanged.
   `/api/health` reports `"auth": "api_key" | "disabled"`.
   Reads (`/api/snapshot`, `/api/quotes`) stay open so the dashboard works.

2. **Resource REST.** Every list endpoint speaks the simple-REST dialect
   Refine consumes natively: `_start`/`_end`, `_sort`/`_order`,
   `field=value` filters, and `X-Total-Count` (exposed via CORS — without
   that header pagination silently breaks).

   - `trades` — PATCH accepts **only terminal states** plus a note.
     Non-terminal transitions stay engine-owned; a UI must not fake a
     lifecycle move. Every manual change writes a `manual_update` audit
     event. No DELETE — trades are an audit trail.
   - `events` — read-only. An audit log you can edit isn't one.
   - `watchlist` — full CRUD over `watchlist.json`, with `_pinned` surfaced
     as the pseudo-sector `PINNED` so pinned tickers are editable. Symbols
     validated, upper-cased, deduped. Responses state that edits apply on
     the **next snapshot rebuild**.

3. **CORS from config.** `CONFLUENCE_CORS_ORIGINS`, comma-separated.

Mounted through a single `install(app, get_state)` call, the same drift-safe
pattern as `phase12.py`.

### Frontend notes

- `lib/confluence.js` is a hand-written ~140-line data + auth provider
  instead of `@refinedev/simple-rest`, so the whole HTTP contract is
  readable in one file with no axios dependency.
- `app/admin/layout.jsx` forces dynamic rendering and wraps the client shell
  in Suspense. Refine's router reads search params at runtime, which Next 14
  can't statically prerender — if you add an admin page and hit a
  `useSearchParams()` prerender error, this layout is why the others work.
- Refine **v5** hook shapes throughout (`result`, `tableQuery`,
  `currentPage`, `mutation.isPending`). Don't paste v4-era snippets from
  older blog posts.

---

## The six edits to `main.py`

1. `from apps.api.auth import require_api_key` added to imports
2. `from fastapi import FastAPI` → `from fastapi import Depends, FastAPI`
3. version `0.7.0` → `0.8.0`; CORS block now uses `_cors_origins()`,
   `allow_credentials=True`, and `expose_headers=["X-Total-Count"]`
4. `dependencies=[Depends(require_api_key)]` on the three mutating routes
5. `/api/health` gains `"auth": auth_mode()`
6. Two lines appended: `install_resources(app, get_state)`

Everything else in that file — including `load_pinned`, the funnel block,
and `/api/journal` — is untouched.

## Known follow-ups (unchanged)

Intraday data, the regex ticker extractor, gateway rate limiting (slowapi is
the natural fit now that auth exists; `gateway.rate_limit` has a home in
`confluence.json`), and retiring the duplicate `dashboard/scripts/` tree.

History still contains the old build-artifact blobs, so `.git` won't shrink
without `git filter-repo`. Optional — clone time is already fixed.
