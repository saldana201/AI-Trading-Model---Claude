# Phase 14 — Universe Explorer

Every sector expandable, every ticker viewable with the full card treatment
(entry / stop / T1 / T2 / R:R, pinned badge, options context, thesis, risks)
— while arming stays strictly trigger-driven. You see the full picture; the
gates decide what's actionable.

Verified: **195 tests pass** (184 prior + 11 new), endpoints exercised live.

## What's in the zip

```
upgrade/
  orchestrator/composer.py        MODIFIED  adds explore() + explore_universe()
                                            (compose() untouched — tested)
  apps/api/main.py                MODIFIED  GET /api/explore,
                                            GET /api/explore/{symbol}, 5-min cache
  apps/web/components/Explorer.jsx NEW      expandable sectors, lazy cards,
                                            per-gate PASS/FAIL report
  apps/web/app/page.jsx           MODIFIED  renders <Explorer />
  tests/test_phase14.py           NEW       11 tests
```

## Applying

```bash
cp -r upgrade/* .
python3 -m pytest tests/ -q      # expect 195 passed
```

No new dependencies, backend or frontend.

## How it behaves

- `GET /api/explore` — all sectors (watchlist + rotation-tracked) with
  status/rank and ticker lists. Sectors rotation tracks but the watchlist
  has no names for show up empty, so the gap is visible.
- `GET /api/explore/{symbol}?direction=long|short` — the full card built by
  the SAME pipeline as compose(): construction, scoring, validation,
  thesis. Plus a per-gate report: regime, sector rotation, screen class,
  R:R floors, confidence floor, evidence validation — each PASS/FAIL with
  the exact numbers.
- `in_composed: true` only when every required gate passes (pinned tickers
  are excused from sector rotation, matching compose()). A test asserts
  explore() and compose() can never contradict each other.
- Cards are view-only in the UI. Failed gates render with what would need
  to resolve for the setup to become actionable — "rely on triggers to arm."
- If the levels engine can't produce structure, the answer is an honest
  "no card", never an invented one. Engine failures surface as clean 422s.

## Notes

- Cards cache for 5 minutes per symbol+direction; `?refresh=1` bypasses.
- In synthetic mode every symbol string yields deterministic bars by
  design, so even garbage tickers get cards there. Live yfinance mode is
  where unknown tickers hit the 422 path (covered by test with a forced
  engine failure).
- Direction defaults to the regime lean; the API accepts an override so
  you can inspect the short side of a long-regime name.
