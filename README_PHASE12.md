# Phase 12 — Configurable engine + Trade Assistant

Two capabilities, one upgrade:

1. **Unified config layer** — every previously hardcoded magic number
   (entry buffer, stop/target ATR multiples, scoring weights, trigger
   attempts, trail distance, the chop gate) is now a named, validated,
   layered parameter. Editable from the dashboard, the API, or a JSON
   file, with presets so a new user never touches raw numbers.

2. **Trade Assistant** — position sizing, copy-ready bracket plans, and a
   live "what do I do right now" advisor that runs on the existing
   lifecycle machine. Log your actual fill and the system manages *your*
   trade, feeding real R-multiples into the outcome journal.

Both preserve the glass-box invariant: nothing is invented. Every price
traces to engine evidence or a declared config formula; every action
traces to the lifecycle contract.

---

## What's in the zip (all paths repo-relative)

```
upgrade/
  config/                    NEW — the tuning surface (stdlib only)
    __init__.py
    schema.py                defaults + validation (defaults == old constants)
    loader.py                layered precedence + persistence + audit
    presets.py               conservative / balanced / aggressive
  assistant/                 NEW — sizing, plans, advice
    __init__.py
    sizing.py                shares + dollar risk from config
    plan.py                  bracket + copy-ready order checklist
    advisor.py               non-mutating "what now" + fill logging
  orchestrator/
    composer.py              RETROFIT — reads geometry/floors/gate from config
    scoring.py               RETROFIT — weights from config
  alerts/
    lifecycle.py             RETROFIT — trigger attempts from config
    engine.py                RETROFIT — trail distance from config
  apps/api/
    main.py                  RETROFIT — 2-line install of phase12 routers
    phase12.py               NEW — config + assistant HTTP surface
  apps/web/components/
    Settings.jsx             NEW — presets + live config editing
    Assistant.jsx            NEW — plans, sizing, fill, live advice
  tests/
    test_phase12.py          NEW — 30 tests (config, retrofits, assistant, API)
```

## Applying it

From the repo root:

```bash
# 1. drop the files in (overwrites the 4 retrofit files, adds the rest)
cp -r upgrade/config       .
cp -r upgrade/assistant    .
cp    upgrade/orchestrator/composer.py orchestrator/
cp    upgrade/orchestrator/scoring.py  orchestrator/
cp    upgrade/alerts/lifecycle.py      alerts/
cp    upgrade/alerts/engine.py         alerts/
cp    upgrade/apps/api/main.py         apps/api/
cp    upgrade/apps/api/phase12.py      apps/api/
cp    upgrade/apps/web/components/*.jsx apps/web/components/
cp    upgrade/tests/test_phase12.py    tests/

# 2. all prior tests stay green + the new ones pass
python3 -m pytest tests/ -q          # 136 passing (106 prior + 30 new)
```

### Wiring the two UI panels

`apps/web/page.jsx` — add the imports and render them (both are
`"use client"` and self-contained; drop them anywhere in the tree):

```jsx
import Settings from "../components/Settings";
import Assistant from "../components/Assistant";

// inside the `{d && (...)}` block, e.g. right after <SetupCards>:
<Assistant />
// and near the footer, or behind a tab:
<Settings />
```

No new npm dependencies — both use the same `fetch` + `NEXT_PUBLIC_API_URL`
convention as `Chat.jsx` and `Live.jsx`.

---

## The config file

Nothing is required — with no file the effective config is byte-identical
to the pre-Phase-12 constants, and the legacy env vars
(`CONFLUENCE_MIN_SCORE`, `_MIN_RR_T1`, `_MIN_RR_T2`,
`CONFLUENCE_FORCE_DIRECTION`) still work.

To pin choices, write `confluence.json` at the repo root (or point
`CONFLUENCE_CONFIG` elsewhere). Only the keys you set are stored:

```json
{
  "risk": { "min_score": 6.5, "account_size": 50000, "risk_per_trade_pct": 1.0 },
  "gates": { "chop_mode": "soft" }
}
```

**Precedence** (low → high): defaults → env vars → `confluence.json` →
runtime updates. The file beats env vars on purpose — the Settings UI
writes the file, and a stale shell export must not silently defeat a
change you just made.

---

## New endpoints

| Method | Path | Purpose |
|---|---|---|
| GET  | `/api/config` | effective config + file path |
| PUT  | `/api/config` | `{"patch": {...}}` — validated partial update |
| GET  | `/api/config/presets` | named presets + active config |
| POST | `/api/config/presets/{name}` | apply a preset |
| GET  | `/api/assistant/plans` | sized plans for current snapshot setups |
| POST | `/api/assistant/plan` | plan for one posted setup |
| POST | `/api/assistant/fill` | `{trade_id, price, shares?}` — log your entry |
| GET  | `/api/assistant/advise/{id}` | one instruction (`?price=` optional) |
| GET  | `/api/assistant/advise` | advice across all armed trades |

Invalid config PUTs return **422** with the exact violation list. A fill
on an already-active trade returns **409** — post-entry transitions stay
engine-owned.

---

## Design notes

- **Engine ownership preserved.** The advisor simulates the lifecycle on a
  *copy* and never mutates the engine's trade. `record_fill` is allowed
  only from WATCHING/TRIGGERED (you reporting reality — "I'm in at X");
  everything after entry is the engine's alone, same principle as the
  terminal-state-only trades PATCH.
- **Chop gate is now a dial, not a surprise.** Phase 11 made the gate
  transparent; Phase 12 makes it configurable: `hard` (unchanged
  no-trade), `soft` (composes with a loud counter-policy warning in the
  payload as `chop_warning`), `off` (trade regardless).
- **Sizing is traceable.** Every sizing result carries its formula and
  inputs, extending the anti-hallucination invariant into the assistant.
- **Config changes are audited.** Each update returns a `config_update`
  event (actor, timestamp, before→after diff) and is broadcast on the SSE
  feed, mirroring the `manual_update` audit pattern.

## Known follow-ups (unchanged from before, not addressed here)

Intraday data, the regex ticker extractor, gateway rate limiting, and the
half-finished `dashboard/` → `apps/` monorepo migration remain open. The
config file gives rate limiting a natural home (`gateway.rate_limit`) when
you get to it.
