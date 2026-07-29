# Phase 20 — Component-weight re-fit under CPCV + walk-forward

## Why
The `validate_real` run exposed the root cause: the scorer's weights were tuned
on the **synthetic** world (random walk, no real VIX/rotation/earnings), so on
real SPY several components were mis-signed — `vix_alignment −0.269`,
`risk_reward −0.123` — and the gross edge was negative. This phase re-fits the
weights to **real** data without repeating the overfitting mistake.

## The overfitting trap, and how this avoids it
Re-fitting weights is a search over configurations. Reporting the in-sample
performance of the winning weights is exactly what turns +23% into −22%. So the
fit is judged **only** out-of-sample:

- **CPCV** — many held-out paths (not one), with purge+embargo so a setup's
  horizon can't leak across the boundary. Verdict is the *distribution* of path
  Sharpes.
- **Deflated Sharpe** — discounts for the number of weight vectors searched.
- **Walk-forward** — strict time-ordered cross-check ("would it have worked
  live?").
- **Non-negativity + normalization** — an inverted component gets weight ~0
  (the honest response), never a bet on the inverse; the score stays in 0..10.

## Proof it works (from the test suite)
On planted data (one good component, one inverted, rest noise):
```
vix_alignment      0.000   <- inverted component correctly zeroed
sector_strength    0.571   <- real signal up-weighted
baseline avg-R 0.016 -> OOS 0.35   PSR 1.0  DSR 1.0  walk-forward agrees
-> RE-FIT IS TRUSTWORTHY
```
On **pure noise** — the critical honesty test:
```
OOS PSR 0.99   <- looks like an edge!
DSR 0.0        <- but deflation (29 vectors tried) catches it
-> DO NOT DEPLOY THESE WEIGHTS
```
PSR alone would have fooled you; the Deflated Sharpe caught the selection bias.
That's the entire rigor stack earning its keep.

## Two-stage workflow (both on your machine)
```bash
# Stage 1 — build the cached dataset (slow, needs data). Both directions.
CONFLUENCE_DATA=yfinance python -m scripts.build_dataset --span 500 \
    --out backtest/weight_dataset.json

# Stage 2 — fit + validate (fast). Dry run first.
python -m scripts.fit_weights --dataset backtest/weight_dataset.json

# Only if the verdict is TRUSTWORTHY, write the weights into confluence.json:
python -m scripts.fit_weights --dataset backtest/weight_dataset.json --write
```
`--write` refuses unless the re-fit cleared the OOS bar. That refusal is the
safeguard working, not a failure. The weights land in `scoring.weights`, which
the scorer already reads via the config layer — no code change to deploy.

## What to look at in the output
1. **per-fold OOS avg-R spread** — narrow + positive = robust; wide = fragile.
2. **DSR** — the number that matters most; < 0.95 means the search found noise.
3. **walk-forward agrees / disagrees** — the skeptic's check.
4. **baseline vs proposed** — is the re-fit actually better than today's weights?
5. **which components go to ~0** — that is the direct read on `vix_alignment`:
   if it zeroes across the full watchlist both directions, the inversion is real,
   not a SPY-long artifact.

## Honest limits
- The fit maximizes selected mean R; it does not yet optimize the *gate
  threshold* jointly (held fixed at --threshold). A follow-up could co-fit both.
- CPCV assumes the feature→outcome relationship is stationary across the window;
  a structural regime change inside the sample weakens that.
- Non-negativity means a genuinely contrarian signal (good when inverted) is
  zeroed rather than flipped — by design, because flipping a weight is a much
  stronger claim that needs its own evidence.
