# Phase 18 — Volatility engine (GARCH(1,1) + realized vol)

First Stage 2 forecasting engine. Deterministic math in an engine, LLM stays out.

## The gap it closes
`options_mcp.select_contract` picks single-leg vs debit spread from **`iv_rank`
alone** — a percentile of implied vol against *its own history*. That answers
"is IV high for this name?" It cannot answer the question that actually decides
whether an option is expensive: **is IV high relative to the volatility that
will actually be realized?**

That gap is the variance risk premium. A name can sit at the 62nd IV percentile
and still be *cheap* if forecast realized vol is running higher.

```
IV rank 0.62 on every setup — "high". Is IV actually rich?

sym         IV   fcst RV   ratio  verdict
AVGO     0.300     0.175    1.72  rich
PLTR     0.301     0.170    1.77  rich
NVDA     0.302     0.177    1.70  rich
```

Here it confirms the spread choice **and supplies the reason**. On real data it
will sometimes disagree — that is the point.

## Files
| File | Purpose |
|---|---|
| `engines/volatility_mcp/logic.py` | estimators, GARCH(1,1), forecast, vol cone, VRP, `VolatilityEngine` |
| `engines/volatility_mcp/server.py` | standalone `volatility-mcp` server |
| `confluence_mcp/server.py` | two new tools on the composite server |
| `tests/test_phase18.py` | 29 tests |

## No new dependencies
The GARCH fit is a **deterministic variance-targeted grid MLE with a free-omega
polish** — pure numpy, no `arch`, no `scipy`. Reproducible bar-for-bar (no
random starts, no optimizer nondeterminism), which is what makes backtesting
this engine meaningful.

Validated against `arch` 8.0.0 on simulated GARCH(1,1) paths (reference only,
not shipped):

| true α/β | mine α/β | arch α/β | next-day vol rel. diff |
|---|---|---|---|
| 0.080/0.900 | 0.077/0.909 | 0.077/0.904 | 2.59% |
| 0.150/0.800 | 0.169/0.767 | 0.175/0.771 | 3.03% |
| 0.050/0.930 | 0.064/0.891 | 0.057/0.896 | 2.64% |

## Estimators, and when each is right
- **close_to_close** — default. The only one of the three that captures
  overnight gap risk, which is exactly the risk a swing option carries.
- **parkinson** — high/low; ~5× more efficient, but blind to gaps, so it
  *understates* gappy names.
- **garman_klass** — full OHLC; more efficient still, same gap blind spot.
- **EWMA(0.94)** — RiskMetrics, for fast reaction to shocks.

## Tools
```
get_realized_vol(symbol)
get_vol_forecast(symbol, horizon_days=21)
get_vol_cone(symbol)
compare_iv_to_forecast(symbol, implied_vol, dte=30)   # implied_vol as decimal
```

Every output carries `method` + `computed_at`, so the anti-hallucination
validator can trace any quoted number back to the bar that produced it.

## Honest limits
- GARCH(1,1) with Gaussian errors understates tail risk; real returns are
  fat-tailed. Treat the forecast as a central estimate, not a bound.
- The forecast is **conditional on no regime break** — it will not anticipate a
  vol shock, only respond after one.
- VRP verdict bands are deliberately wide. This is a decision aid on top of a
  confluence gate, not a standalone vol-arbitrage signal.
- Needs ≥80 daily bars to fit; degrades with a stated reason below that.
