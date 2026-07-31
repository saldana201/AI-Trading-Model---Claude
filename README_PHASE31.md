# Phase 31 — Engine-first interface

Built on GitHub `35be6f7 (phase 30)`, verified 354 tests green before starting.
Now **366 tests**.

## What changed
The composed-setup product lost to buy-and-hold (+37.4% vs QQQ +111.7%, deeper
drawdown, worse Sharpe). The **engines** did not fail — fractal S/R clusters, VIX
pivots, gamma walls, GARCH vol, RVOL phase, rotation state are deterministic,
testable facts. So the product inverts: engines become the front door.

## New MCP tools on `confluence-mcp`
| tool | returns |
|---|---|
| `engine_brief(symbol)` | **everything** all 10 engines know about one symbol |
| `get_vix()` | pivot, fractal targets, term structure |
| `get_volume(symbol)` | RVOL + Wyckoff phase |
| `get_momentum(symbol)` | RSI stack + divergences with pivot pairs |
| `get_fundamentals(symbol)` | growth, margins, valuation, **earnings date** |

Previously only 6 of 10 engines were exposed; VIX, volume, momentum, screener
and fundamentals were unreachable from MCP.

## Sample output
```
NVDA — engine brief (facts only, no recommendation)
  levels: 147.45(high_of_day), 146.74(prior_day_high), 143.82(weekly_pivot)
  vix: spot=11.41 pivot=11.96 alignment=confirming_bullish
  volume: rvol=None phase=mark_up
  momentum: monthly:100.0 weekly:94.6 daily:81.9 (5 overbought, 0 oversold)
  regime: risk_on risk_score=6.3
  volatility: 21d forecast=0.177 next_day=0.177 half_life=0.47d
  options: flip=None call_wall=155.0 put_wall=140.0
  fundamentals: earnings=2026-09-07 sector=Technology
  (interpretation is yours — composed setups underperformed buy-and-hold)
```

## The restraint is enforced, not intended
`assert_no_recommendation()` walks the payload and raises if advisory language
appears ("buy", "should", "recommend", "take this trade"...). A brief that starts
recommending is a bug, and the test suite defends that contract.

It scans string **values** only — scanning serialized JSON made the metadata key
`contains_recommendation` false-positive on every brief. That bug was caught on
the first real run.

## Engines degrade, never go silent
Any engine that raises is reported as `{"available": false, "error": ...}` and
listed under `unavailable`. A missing engine reads as missing, not as absence of
signal.

## Usage
Point Claude Desktop / Claude Code at `confluence-mcp` and ask:
"What do the engines say about NVDA?" → one `engine_brief` call, facts back,
interpretation yours.
