# Confluence — Phases 1–11: full system, live, backtested, automated

Phase 1 of the trade entry/exit forecasting system (see `trade-forecasting-app-design.md`).
Two deterministic MCP servers and the shared fractal/level core they're built on.

## What's here

```
confluence/
├── engines/
│   ├── shared/
│   │   ├── providers.py    # DataProvider protocol: YFinanceProvider (live) + SyntheticProvider (offline/tests)
│   │   ├── fractals.py     # Williams fractal detection + recency-weighted level clustering
│   │   └── levels.py       # Weekly pivots, ATR outliers, MA reclaim/loss, RVOL, level-break primitive
│   ├── vix_mcp/            # VIX pivot + upside/downside targets + index alignment   (design doc §4.1)
│   └── levels_mcp/         # Full SPY/QQQ/stock level engine                          (design doc §4.2)
├── tests/test_phase1.py    # 16 tests covering the methodology and both engines
├── demo.py                 # End-to-end demo (synthetic or live)
└── requirements.txt
```

## Setup

```bash
pip install -r requirements.txt
python -m pytest tests/ -q                      # all 16 should pass
CONFLUENCE_DATA=synthetic python demo.py        # offline demo
python demo.py                                  # live data via yfinance
```

`CONFLUENCE_DATA=synthetic` swaps in seeded random-walk bars — useful for tests,
offline dev, and shaping scenarios (e.g. trending QQQ vs falling VIX).

## Using the MCP servers

Run standalone (stdio transport):

```bash
python -m engines.vix_mcp.server
python -m engines.levels_mcp.server
```

Claude Desktop / Claude Code config:

```json
{
  "mcpServers": {
    "vix-mcp": {
      "command": "python",
      "args": ["-m", "engines.vix_mcp.server"],
      "cwd": "/path/to/confluence"
    },
    "levels-mcp": {
      "command": "python",
      "args": ["-m", "engines.levels_mcp.server"],
      "cwd": "/path/to/confluence"
    }
  }
}
```

### Tools

| Server | Tool | Returns |
|---|---|---|
| vix-mcp | `get_vix_levels()` | VIX spot, pivot, upside targets 1/2, downside targets 1/2, fractal clusters |
| vix-mcp | `get_vix_alignment(symbol)` | `confirming_bullish` / `confirming_bearish` / `diverging_warning` / `diverging_supportive` / `neutral_chop` + evidence |
| levels-mcp | `get_index_levels(symbol)` | HOD/LOD, prior day H/L, weekly pivot/ceiling/floor, ATR outliers, gap levels, fractal S/R clusters with strength, bullish/bearish triggers, MA status, RVOL |
| levels-mcp | `get_stock_levels(symbol)` | Same payload for individual stocks |
| levels-mcp | `check_level_break(symbol, level, direction)` | Broken/held + RVOL context — the alert-engine primitive |

## Methodology notes

- **Fractals:** 5-bar Williams fractals (`wing=2`) on daily bars; strict-extreme rule avoids flat-top false positives.
- **Clustering:** fractal prices within 0.35% (equities) / 1.5% (VIX) merge; each cluster weighted by exponential recency decay (30-bar half-life) and √touches, normalized to a 0–1 strength.
- **VIX pivot/targets:** pivot = cluster nearest spot; targets 1/2 = next clusters above/below.
- **Triggers:** bullish trigger = strongest cluster above spot; bearish = strongest below. These are the alert-arming levels for the daily game plan.
- **Anti-hallucination contract:** every level record carries `method` + `computed_at` so the future orchestrator's validator can reject any setup citing a level not present in engine evidence.

## Phase 2 additions

| Server | Tool | Returns |
|---|---|---|
| volume-mcp | `get_rvol(symbol)` / `classify_phase(symbol)` | RVOL stack; price-volume phase (accumulation / mark_up / distribution / mark_down / consolidation / exhaustion / failed_breakout / failed_breakdown) with evidence |
| momentum-mcp | `get_rsi_stack(symbol)` / `find_divergences(symbol)` | Wilder RSI across monthly→30m with zone + direction; fractal-anchored divergences citing exact pivot pairs |
| regime-mcp | `get_regime()` | risk_on / risk_off / chop, a −10..+10 risk score, vol modifiers, and per-component score/weight/contribution/evidence |

Notable logic guard: `detect_failed_break` requires the prior window to be
range-bound (|slope| ≤ 0.08%/bar) — a pullback in a trend is not a failed breakout.

## Dashboard (UI pipeline starts here)

```bash
CONFLUENCE_DATA=synthetic python -m scripts.snapshot   # writes dashboard/data.json
open dashboard/index.html                              # or serve the folder
```

`dashboard/index.html` is a single-file pre-market command surface: regime
verdict + risk-score gauge + component contribution bars, VIX and QQQ level
ladders (rung width = cluster strength, gold = pivots/triggers), tape-character
panel (phase, RSI stack, divergences, SPY check). It reads `data.json` and
falls back to embedded sample data, so it opens standalone.

`scripts/snapshot.py` produces exactly the payload a Next.js `/api/snapshot`
route will serve in the full app — the HTML panels are the component spec for
that migration (one panel ≈ one React component).

## Phase 3 additions

| Component | What it does |
|---|---|
| rotation-mcp | 31-ETF universe; relative perf vs SPY over 1/4/12/24/48w; leading / improving / neutral / deteriorating / lagging |
| screener-mcp | CANSLIM-style checklist (11 filters); canslim_leader / laggard_turn / speculative_momentum / overextended / no_setup |
| fundamentals-mcp | Growth grade, earnings date + in_earnings_window flag (hard composer input); yfinance live / synthetic offline |
| orchestrator/composer.py | Regime gate → rotation → screen → entry/stop/T1/T2 construction → score → validate. Chop = stand aside, with the reason. |
| orchestrator/scoring.py | The PRD's 11-component confidence score; options + liquidity components are labeled Phase 5 placeholders |
| orchestrator/validator.py | Anti-hallucination contract: every setup price must trace to engine evidence (ATR derivations must declare traced inputs) |
| orchestrator/llm.py | Optional Claude-written thesis via the Anthropic SDK (`ANTHROPIC_API_KEY` + `CONFLUENCE_MODEL`); validator applies regardless |

Setup geometry: entry = nearest meaningful resistance cluster (or day-high
breakout at 52-week highs), stop capped at 2×ATR, targets ATR-floor spaced;
gates: T1 R:R ≥ 1.0 (trim), T2 R:R ≥ 2.0 (objective), confidence ≥ 6.0.

Dashboard gains the Sector Rotation table and Setup cards (entry/stop/targets,
confidence, thesis, risk flags, earnings-window badge); a chop regime renders
the stand-aside reason instead of forcing trades.

Reproducibility note: synthetic bars are seeded with sha256, not Python's
process-salted `hash()` — runs are now identical across processes.

## Phase 4 additions — the alert engine

| Component | What it does |
|---|---|
| alerts/predicates.py | JSON predicate trees (all/any/not over level_break, vix pivot, rvol, price checks); every evaluation returns its evidence trail. No LLM in the detection path. |
| alerts/lifecycle.py | The state machine: WATCHING → TRIGGERED → ACTIVE → TRIMMED_T1 → TRAILING → CLOSED, with INVALIDATED / STOPPED / DETERIORATED exits. Triggers must hold (one re-arm, then invalidated); T1 trims and moves the stop to breakeven; trailing clamps to breakeven. |
| alerts/engine.py | Arms composer setups, ticks every bar: market guard (VIX reclaims pivot + index loses weekly pivot → DETERIORATED), persists, fans out to sinks. One broken sink never blocks the others. |
| alerts/store.py | SQLite trades + events (Timescale in production). |
| alerts/sinks.py | Console, JSONL, and webhook (Discord-compatible) delivery, stdlib-only. |
| scripts/alertd.py | Polling daemon: arms the morning game plan, ticks on an interval, optional DISCORD_WEBHOOK_URL. |
| scripts/demo_alerts.py | Scripted lifecycle demo feeding the dashboard: NVDA full winner (trigger → trim → trail → T2), AMD deteriorated when VIX pops over pivot while QQQ loses its weekly pivot. |

ReplayProvider / ScriptedProvider replay bars progressively so the whole alert
path is testable bar by bar. The dashboard gains the Alert Feed panel with
lifecycle badges.

Run it:

```bash
CONFLUENCE_DATA=synthetic python -m scripts.snapshot   # game plan
CONFLUENCE_DATA=synthetic python -m scripts.alertd --interval 5 --ticks 3
python -m scripts.demo_alerts                          # scripted lifecycle demo
```

## Phase 5 additions — the options layer

| Component | What it does |
|---|---|
| engines/options_mcp/greeks.py | Black-Scholes gamma/vanna + expected move, stdlib-only |
| engines/options_mcp/providers.py | Chain abstraction: SyntheticOptions (engineerable walls/IV-rank/spreads) and YFinanceOptions (live; iv_rank honestly None) |
| engines/options_mcp/logic.py | Per-strike GEX ($m / 1% move) and vanna, zero-gamma flip (cumulative-GEX crossing), call/put walls, dealer-zone reading, contract quality, and PRD §13 contract selection |
| orchestrator updates | options_alignment and liquidity score components are now REAL when a chain feed exists (weights restored to 1.1 / 0.8) and degrade gracefully to labeled placeholders when it doesn't |

GEX convention (documented approximation): dealers long calls / short puts —
a positioning estimate, never dealer ground truth.

Contract selection rules: strike at/inside the entry trigger; swing expiry
21–50 DTE; IV rank ≥ 55% → debit spread with the short leg at T2; liquidity
gates OI ≥ 500 and spread ≤ 8% of mid (fallback: stock, with the reason);
expected-move check flags a T1 beyond the contract's 1σ move.

Dashboard gains the Options Positioning panel (GEX-by-strike chart, flip,
walls, dealer-zone reading) and instrument suggestion lines on every setup
card (e.g. `CALL DEBIT SPREAD · 2180 / 2290 · exp 2026-07-11 (31d) · OI 774 ·
spread 2.0%`).

Provider fix worth noting: SyntheticProvider now generates one 800-bar master
series per symbol and every lookback slices its tail — previously different
lookbacks produced different prices for the same symbol, which surfaced the
moment two engines (levels vs options) asked for different histories.

## Phase 6 additions — gateway, Next.js app, chat, composite MCP

| Component | What it does |
|---|---|
| apps/api (FastAPI) | GET /api/health, GET /api/snapshot (TTL-cached, ?refresh=1), POST /api/chat. CORS for localhost:3000. |
| orchestrator/chat.py | Two-mode chat over the engine tool mesh: Anthropic SDK tool-use loop when ANTHROPIC_API_KEY + CONFLUENCE_MODEL are set; a deterministic intent router otherwise that answers the PRD §10 canonical questions straight from engine output (clearly labeled). Degrades to "correct but less fluent", never silence. |
| apps/web (Next.js 14) | The dashboard as a real app: one React server component per panel (RegimeStrip, VixPanel, IndexPanel, TapePanel, OptionsPanel, RotationTable, SetupCards, AlertFeed) sharing the same class names/design system as the static dashboard, plus a client Chat component. Page is force-dynamic and renders a clear "API offline" state. |
| confluence_mcp/server.py | The whole system as ONE MCP server: get_game_plan, get_regime, get_levels, get_setups, get_rotation, get_dealer_zones, ask. Plug into Claude Desktop / Claude Code. |

### Running the full stack

```bash
# 1) backend (synthetic offline world, or omit env for live yfinance)
CONFLUENCE_DATA=synthetic uvicorn apps.api.main:app --port 8000

# 2) frontend
cd apps/web && npm install && npm run dev          # http://localhost:3000
# production: npm run build && npm start

# 3) optional LLM chat
export ANTHROPIC_API_KEY=...   CONFLUENCE_MODEL=<current model>   # docs.claude.com

# 4) the whole system in Claude Desktop / Claude Code
CONFLUENCE_DATA=synthetic python -m confluence_mcp.server
```

Claude Desktop config for the composite server:

```json
{ "mcpServers": { "confluence": {
    "command": "python", "args": ["-m", "confluence_mcp.server"],
    "cwd": "/path/to/confluence",
    "env": { "CONFLUENCE_DATA": "synthetic" } } } }
```

### Monorepo layout

```
confluence/
├── engines/            # 9 deterministic MCP servers + shared core
├── orchestrator/       # composer, scoring, validator, chat, optional LLM
├── alerts/             # predicates, lifecycle state machine, store, sinks
├── apps/api/           # FastAPI gateway
├── apps/web/           # Next.js dashboard + chat
├── confluence_mcp/     # composite MCP server
├── dashboard/          # Phase 2–5 single-file dashboard (still works standalone)
├── scripts/            # snapshot, alertd, demo_alerts
└── tests/              # 89 tests across all six phases
```

## Phase 7 additions — live feed + live dashboard

| Component | What it does |
|---|---|
| CachedProvider | TTL bar cache wrapping any provider — one snapshot no longer hits yfinance dozens of times for the same symbols. Tune with CONFLUENCE_BARS_TTL (default 300s) / CONFLUENCE_QUOTE_TTL (15s). |
| GET /api/quotes | Lightweight spot / change% / RVOL for the ticker strip (defaults QQQ, SPY, ^VIX + any armed symbols). |
| GET /api/stream | Server-sent events: `hello`, `quote` every CONFLUENCE_QUOTE_INTERVAL (15s), and `alert` events from the live alert engine. Keepalives every 30s. |
| POST /api/alerts/arm · /tick · GET /state | Arm the current game plan into the Phase 4 lifecycle engine; ticked automatically by the background pump every CONFLUENCE_ALERT_INTERVAL (60s) while anything is armed. |
| apps/web Live components | LiveTicker (SSE with polling fallback + connection dot), LiveFeed (demo seed + streamed alerts highlighted), ArmButton on the setups panel, SnapshotRefresher (auto router.refresh every 2 min + manual ↻). |

Hardening that came out of making it live: the SQLite store is now
thread-safe (FastAPI sync routes run on a threadpool); the composer gained a
geometry guard so no setup can arm with its stop on the wrong side of spot
(instant-invalidation by construction); and an arm-survival test asserts every
composed setup survives its first tick.

Live-cadence reality check: quotes refresh on the interval, but the bar feed
is still daily yfinance — so triggers/stops evaluate on daily closes. True
intraday alerting needs the 1m/5m streaming ingest from the design doc; the
predicates and state machine are unchanged when that lands.

## Phase 11 — pinned tickers made observable (debugging the loop)

Pinning *worked* but was invisible: a pinned name that screened as `no_setup`
or fell to a quality gate just disappeared, indistinguishable from "the
feature is broken." This phase makes a pin's fate fully traceable.

| Fix | What changed |
|---|---|
| Robust path resolution | watchlist.json is found whether you launch uvicorn from the repo root or elsewhere — searched in `CONFLUENCE_WATCHLIST`, the CWD, then the repo root, with an INFO log naming the file it loaded (or "using defaults"). |
| Startup + health visibility | The terminal prints `data=… · pinned=… · autoarm=…` on boot, and GET /api/health now returns `pinned`, `watchlist_sectors`, and `autoarm_et` so you can confirm config without guessing. |
| Full pinned tracing | Every pin gets a disposition in `funnel.pinned_outcomes`: `"setup"`, or the exact gate that stopped it (screen classification, no level structure, R:R floor, confidence floor, validation). Suppression records carry a `pinned` flag. The dashboard renders a "Pinned tickers" trace under the setups panel. |

Key insight from the debug: pinning bypasses the *rotation* gate, never the
*quality* gates — so a pinned ticker only becomes a card if it also passes the
screen, confidence, and R:R checks. The trace tells you which of those it
missed. To see pinned names set up regardless, combine with
`CONFLUENCE_FORCE_DIRECTION` (test mode) or loosen `CONFLUENCE_MIN_SCORE`.

## Phase 10 additions — pinned tickers + morning automation

| Component | What it does |
|---|---|
| Pinned tickers | A `"_pinned": ["TSLA", ...]` list in watchlist.json. Pinned names are ALWAYS screened, regardless of sector rotation status — the rotation gate is bypassed, the quality gates (screen classification, confidence floor, R:R, geometry) are not. If a pinned name lives under a watchlist sector, it carries that sector's real status; otherwise it gets the PINNED pseudo-sector (rotation score 0.5, gold chip). Setups carry a `pinned` flag; the funnel reports `pinned_candidates`. The chop gate still stands. |
| orchestrator/brief.py | The daily game plan as markdown, rendered from the same snapshot the dashboard consumes (the brief and the board can never disagree). Defensive against partial snapshots. |
| Auto-arm scheduler | Set `CONFLUENCE_AUTOARM_ET=08:30` and the background pump, once per day at/after that ET time: rebuilds the snapshot, arms the game plan, writes `briefs/YYYY-MM-DD.md`, broadcasts a `brief` SSE event, and (if `CONFLUENCE_DISCORD_WEBHOOK` is set) posts the brief to Discord. Tested with injected clocks: fires once, never double-arms, fires again the next day. |

Daily-driver setup: `CONFLUENCE_DATA=yfinance CONFLUENCE_AUTOARM_ET=08:30 uvicorn apps.api.main:app --port 8000` — leave it running and the game plan arms itself before the open.

## Phase 9 additions — the outcome journal

| Component | What it does |
|---|---|
| alerts/journal.py | Stored trades + event trails -> R-multiple outcomes under the exact backtest semantics (half at T1, breakeven, trail; open positions marked to quote, water-mark fallback). Feeds the same calibration report — live and backtest results share one definition of "win". |
| GET /api/journal | rows (per-trade: status pending/open/closed/no_fill, entry, exit/mark, R, confidence, reason) + summary + counts. |
| Persistence | CONFLUENCE_ALERT_DB now defaults to `alerts.db` (a file) so the journal survives restarts, and LiveAlerts re-arms every non-terminal trade from the store on startup — a gateway restart never orphans an open position's monitoring. |
| Dashboard | Journal panel: resolved-trade win rate and average R in the header, last 20 trades in a table with color-coded R. |

## Phase 8 additions — backtest harness + real sector breadth

| Component | What it does |
|---|---|
| backtest/harness.py | Replays history with ReplayProvider: composes setups as-of each step, steps each through the live lifecycle state machine over the actual subsequent bars, and records R-multiple outcomes under live trade-management semantics (half off at T1, breakeven stop, trail). |
| backtest/run.py | CLI: `python -m backtest.run --span 252 --step 5 --horizon 15` (synthetic or live; CONFLUENCE_FORCE_DIRECTION applies). Writes backtest/results.json. |
| Calibration report | Win rate / avg R / expectancy per confidence bucket (does ≥7.5 beat <6.5?), final-state counts, fill rate, and per-component winners-vs-losers edge — the empirical basis for re-tuning WEIGHTS and the gate floors. |
| Regime breadth | The ma_breadth component now uses REAL sector breadth (fraction of the 31-ETF universe above the 21-day MA + leading-vs-lagging tilt) wherever the rotation engine is wired (gateway, snapshot, composite MCP); the MA-proxy remains as the cheap fallback used inside backtests. |

Backtest caveats are first-class in the output: fills at trigger-bar close
(no slippage/commissions), guard levels frozen at compose time, and daily-bar
resolution (the close decides when one bar spans both stop and target).
Treat results as relative calibration (bucket vs bucket, component vs
component), not absolute P&L forecasts.

### What remains before live trading use

Backtest the level/confluence heuristics and tune score weights against
outcomes (every engine output is timestamped for exactly this); swap yfinance
for a real-time feed + streaming ingest for intraday alerting; replace SQLite
with TimescaleDB; harden the gateway (auth, rate limits). And the standing
disclaimer stands: decision support, not investment advice.

---

*Decision-support tooling, not investment advice. Levels are heuristic pattern
detection; validate with backtests before trading against them.*
