# Phase 19 — VRP wired into contract selection + real-data validation

## A. The volatility engine is no longer an orphan

`select_contract` chose single-leg vs debit spread from **`iv_rank` alone**.
It now consults the variance risk premium too.

| iv_rank says | VRP says | Result |
|---|---|---|
| spread | rich | spread (agree) |
| single leg | cheap | single leg (agree) |
| **spread** | **cheap** | **single leg — VRP overrides** |
| **single leg** | **rich** | **spread — VRP overrides** |
| either | slightly rich / fair / slightly cheap | defers to iv_rank |

**Why VRP wins a disagreement:** `iv_rank` asks "is IV high for this name,
against its own history?" VRP asks "is IV high against the volatility likely to
be *realized*?" Only the second determines whether you are overpaying. A name at
the 62nd IV percentile with forecast RV of 42% is **cheap** — buying a spread
there finances away convexity that is on sale.

**Why equivocal VRP defers:** a ratio near 1.0 is not a view. Overriding on it
would manufacture confidence from noise.

Every decision records both signals and which one decided:

```json
"structure_decision": {
  "iv_rank": 0.62, "iv_rank_says": "spread",
  "vrp": {"verdict": "cheap", "ratio": 0.71, "forecast_vol": 0.42},
  "vrp_says": "single_leg",
  "decided_by": "variance_risk_premium (overrode iv_rank)"
}
```

`vrp=None` reproduces pre-Phase-19 behaviour exactly — all 317 tests pass.

## B. `scripts/validate_real.py` — the moment of truth

Everything in Phases 15–18 detects a *weak* edge. It has only run on synthetic
data, where the edge is inflated (~11× cost headroom) and **no guard ever
bites**. This script points the whole stack at real bars:

```bash
CONFLUENCE_DATA=yfinance python -m scripts.validate_real --span 500 --trials 8
```

`--trials` is the number of weight/threshold configurations you have tried
against this data over the project's life. Understating it is how a backtest
flatters itself.

It prints a single verdict instead of burying the answer:

```
====================================================================
VERDICT: DO NOT PROMOTE THIS CONFIGURATION
  FAIL  EDGE DIES UNDER COSTS — gross positive, net negative
  warn  only 34 trades vs MinTRL 121 — too early to judge
====================================================================
```

Severity order: sign-flip under costs → headroom < 2× → PSR < 0.95 →
n < MinTRL → bootstrap p05 negative.

**A failing result is not a failed run.** It is the system telling you something
true that the pre-Phase-15 reports could not express.

## Known limitation
yfinance has no historical option chains. On real price data, `--with-options`
models *today's* chain against past bars. Options cost realism is only
achievable on synthetic chains until a historical options feed exists.
