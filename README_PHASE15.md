# Phase 15 — Backtest statistical rigor

**What it does.** Adds a López de Prado-grade validation layer on top of the
Phase 8 harness so you can tell an *edge* from an *artifact*. No new dependency
(pure numpy — the normal CDF/inverse-CDF are implemented in-module), and it's
purely additive: every existing Phase 8 report key is unchanged, with a new
`rigor` block alongside them.

## Files

| File | Change |
|---|---|
| `backtest/statistics.py` | **new** — PSR, DSR, MinTRL, profit factor, bootstrap bands, purge/embargo, and the `rigor_block()` / `render_rigor()` report helpers |
| `backtest/harness.py` | `report()` gains `n_trials` / `trial_sharpe_variance`; emits `rep["rigor"]`; `render_text()` prints it; `Backtest.__init__` accepts the trial args and threads them through `run()` |
| `backtest/run.py` | new `--trials` flag |
| `tests/test_phase15.py` | **new** — 24 tests (analytic properties + report integration + graceful degradation) |

## The metrics, and why each is here

- **PSR — Probabilistic Sharpe Ratio** `psr_vs_zero`. P(true Sharpe > 0),
  corrected for the skew and fat tails of an R-multiple distribution. A raw
  Sharpe over capped-downside / long-right-tail returns is optimistic; PSR isn't.
  Rule of thumb: promote a change only if PSR ≥ 0.95.

- **MinTRL — Minimum Track Record Length.** How many filled setups you need
  before a Sharpe is believable at 95%. If a confidence bucket has fewer trades
  than its MinTRL, you don't yet have the evidence to trust it.

- **DSR — Deflated Sharpe Ratio.** PSR after discounting for *how many
  configurations you tried*. This is the one that matters most for Confluence:
  every time you re-tune a score weight or gate threshold against `results.json`
  and keep the best, you've introduced selection bias. See "Using DSR correctly."

- **Bootstrap bands.** Resamples trades 2,000× to give 5th/50th/95th-percentile
  bands and P(metric > 0) for avg-R, win-rate, and profit factor. A positive
  point estimate whose p05 is deeply negative is fragile, not an edge.

- **Purge + embargo** (`purge_embargo_split`). Index-level helper for when you
  cross-validate weight choices: a 15-bar-horizon setup composed every 5 bars
  overlaps its neighbors, so a naive train/test split leaks. Purge drops the
  pre-test overlap; embargo drops a buffer after the test block.

## Using DSR correctly

A single backtest run **cannot** compute DSR by itself — DSR needs the *spread
of Sharpes across the different configurations you tried*, which only you know
across runs. So:

- `--trials N` alone records intent and prints `DSR skipped … treat PSR as an
  upper bound`. This is deliberate, not a bug.
- To actually deflate, collect the per-config Sharpes (or their return streams)
  as you tune, then call the report with `trial_sharpe_variance=` (the variance
  of those Sharpes) or `all_trial_returns=` (the list of return arrays). The
  cleanest workflow: keep each run's `overall` R series, and once you've tried a
  handful of configs, feed them all to `deflated_sharpe_ratio(...,
  all_trial_returns=[...])` to see whether your best result survives.

```python
from backtest.statistics import deflated_sharpe_ratio
# streams = list of realized-R arrays, one per weight/threshold config you tried
d = deflated_sharpe_ratio(None, n_trials=len(streams), all_trial_returns=streams)
print(d["dsr"], d["expected_max_sharpe"])   # DSR < 0.5 => likely a selection artifact
```

## Run it

```bash
CONFLUENCE_DATA=synthetic CONFLUENCE_FORCE_DIRECTION=long \
  python -m backtest.run --span 252 --step 5 --horizon 15 --trials 1

python -m pytest tests/test_phase15.py -q      # 24 tests
python -m pytest tests/ -q                      # full suite, still green
```

## Honest limits (unchanged from Phase 8, plus new ones)

- These statistics inherit every Phase 8 approximation: daily bars, fills at
  trigger-bar close, no slippage/commissions, frozen guard levels. A high PSR on
  a cost-free backtest is still cost-free — Stage 1's next piece (transaction-cost
  knobs) is where a sign-flip under costs should auto-fail a config.
- PSR/DSR assume returns are IID enough for the moment estimates to mean
  something; heavily autocorrelated overlapping trades weaken that (mitigate via
  the purge/embargo split when cross-validating).
- DSR's expected-max-Sharpe uses the standard Gumbel approximation and assumes
  the trials are the relevant independent search space; if you tried far more
  informal variations than you logged, the true deflation is larger.
