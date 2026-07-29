# Phase 17 — Transaction costs and slippage

Completes Stage 1. Every R-multiple the harness reported before this was
**gross** — no commission, no slippage, no bid-ask. That is the approximation
that turned FinMem's +23.26% into −22.04% in the FINSABER replication.

## Files
| File | Change |
|---|---|
| `backtest/costs.py` | **new** — `CostModel`, `cost_in_r()`, `apply_cost()`, `cost_sensitivity()`, `render_costs()` |
| `backtest/harness.py` | `Outcome` carries `instrument`, `spread_pct`, `gross_r`, `cost_r`; `realized_r` is now **net**; `report()` gains a `costs` block |
| `backtest/run.py` | cost CLI flags + `--with-options` to wire the options engine |
| `tests/test_phase17.py` | **new** — 24 tests |

## Two things the audit found
1. **`instrument` was dropped from backtest outcomes**, and the backtest factory
   never wired the options engine — so the backtest validated *share* trades
   while the live system routes nearly everything to **call debit spreads**.
   `--with-options` closes that gap (synthetic only; yfinance has no historical
   chains).
2. **Options cost is dominated by the bid-ask**, and `options_mcp` already
   computes `spread_pct` per contract. The model consumes that real engine
   number and only falls back to a default when it is absent — and says which.

## Why costs are expressed in R
Friction is fixed in dollars, so it scales inversely with stop width. Same
10bps slippage:

| stop | risk | drag |
|---|---|---|
| 90 | 10.0pt | 0.021R |
| 96 | 4.0pt | 0.053R |
| 98 | 2.0pt | 0.105R |
| 99 | 1.0pt | 0.210R |

The tight-stop, high-R:R setups that score best are exactly the ones friction
hurts most. A flat "subtract 5 bps" model hides this entirely.

## The sign-flip check
`cost_sensitivity()` reports avg net R at 0×/0.5×/1×/2×/3× modeled cost, the
breakeven drag, headroom, and the headline boolean `sign_flip_under_costs`.
A real +0.10R edge dies at a 10% option spread:

```
liquid 2%      drag 0.033R  net +0.0670R  survives (3.03x headroom)
wide 10%       drag 0.113R  net -0.0130R  SIGN FLIP
```

**Promotion rule:** never promote a configuration whose sign flips, and treat
headroom under 2× as fragile.

## Run
```bash
python -m backtest.run --with-options                    # costs on (default)
python -m backtest.run --no-costs                        # pre-Phase-17 gross
python -m backtest.run --slippage-bps 10 --option-spread-pct 0.08
```

## Honest limits
- The options cost assumes **debit ≈ dollar risk** for a defined-risk spread
  (the harness prices stock geometry, not option P&L). Every result relying on
  it lists that in `assumptions`.
- Costs are applied as an R-drag; the simulated *fill price* is still the
  trigger-bar close, so path effects of a worse fill are not modeled.
- The live journal is gross by construction; its `costs` block reports
  unavailable rather than faking a zero-cost verdict.
