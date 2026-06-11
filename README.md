# Confluence — Phases 1–5: engines, orchestrator, alerts, options, dashboard

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

## Next (Phase 6)

Migrate the dashboard into the Next.js monorepo (`/api/snapshot` route + one
React component per panel), add the chat route over the MCP tool mesh, and
expose the whole system as a composite `confluence-mcp` server.

---

*Decision-support tooling, not investment advice. Levels are heuristic pattern
detection; validate with backtests before trading against them.*
