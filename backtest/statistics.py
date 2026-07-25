"""Phase 15 — backtest statistical rigor (López de Prado-grade validation).

The Phase 8 harness answers "what happened." This module answers the harder
question the literature insists on: *would it survive selection bias and
non-normal returns, or is it an artifact?* Every function here is deterministic
and pure-numpy — no scipy, no new dependency — so it slots under the same
glass-box rule as the engines: the math is auditable and testable, and the
orchestrator/LLM never touches it.

What it adds, and why each matters for this system specifically:

- **Probabilistic Sharpe Ratio (PSR)** — the probability the true Sharpe of a
  return stream exceeds a benchmark, *corrected for skew and kurtosis*. R-multiple
  distributions are violently non-normal (a capped downside near −1R, a long right
  tail from runners), so a raw Sharpe overstates confidence. PSR is the honest read.

- **Minimum Track Record Length (MinTRL)** — how many trades you'd need before a
  Sharpe is statistically distinguishable from the benchmark at a chosen
  confidence. Answers "is 40 filled setups enough to trust this bucket?"

- **Deflated Sharpe Ratio (DSR)** — PSR after deflating for the number of
  configurations you tried. This is the direct defense against the exact failure
  mode Confluence is exposed to: every time a score weight or gate threshold is
  tuned against `results.json`, that's another trial, and the best-looking result
  is selection-biased upward. DSR discounts it.

- **Bootstrap resampling** — distribution of avg-R, win-rate, and profit factor
  under trade-order/resample perturbation, for drawdown and stability bands.

- **Purge + embargo helpers** — index-level tools so overlapping-horizon setups
  (a 15-bar trade composed every 5 bars overlaps its neighbors) don't leak across
  a train/test boundary when cross-validating weight choices.

References: Bailey & López de Prado, "The Deflated Sharpe Ratio" (JPM 2014);
"The Probabilistic Sharpe Ratio" (2012); *Advances in Financial Machine
Learning* (2018), ch. 7 (purge/embargo) and ch. 14 (backtest statistics).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

_EULER = 0.5772156649015329


def _json_safe(obj):
    """Recursively replace inf / -inf / nan with None so the block survives
    Starlette's JSONResponse (json.dumps with allow_nan=False). MinTRL returns
    +inf when there's no edge, profit_factor is inf with no losers, and bootstrap
    can yield nan on degenerate resamples — all legitimate values that are simply
    not JSON-compliant floats. None reads correctly downstream as 'n/a'."""
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    return obj


# ---------------------------------------------------------------------------
# Normal CDF / inverse-CDF (pure, so scipy stays out of requirements.txt)
# ---------------------------------------------------------------------------

def norm_cdf(x: float) -> float:
    """Standard normal CDF via the error function (stdlib math.erf)."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def norm_ppf(p: float) -> float:
    """Inverse standard normal CDF (Acklam's rational approximation,
    absolute error < 1.15e-9). Valid on the open interval (0, 1)."""
    if not (0.0 < p < 1.0):
        raise ValueError("norm_ppf requires 0 < p < 1")
    a = (-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00)
    b = (-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01)
    c = (-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00)
    d = (7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00)
    plow, phigh = 0.02425, 1 - 0.02425
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
               ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    if p > phigh:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
               ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    q = p - 0.5
    r = q * q
    return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / \
           (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)


# ---------------------------------------------------------------------------
# Moments and Sharpe
# ---------------------------------------------------------------------------

@dataclass
class Moments:
    n: int
    mean: float
    std: float
    skew: float      # Fisher (0 for normal)
    kurt: float      # non-excess (3 for normal)
    sharpe: float    # per-trade, non-annualized


def moments(returns) -> Moments:
    r = np.asarray(returns, dtype=float)
    r = r[np.isfinite(r)]
    n = r.size
    if n < 2:
        raise ValueError("need at least 2 returns")
    mean = float(r.mean())
    std = float(r.std(ddof=1))
    if std == 0.0:
        return Moments(n, mean, 0.0, 0.0, 3.0, 0.0)
    z = (r - mean) / std
    skew = float((z ** 3).mean())
    kurt = float((z ** 4).mean())     # non-excess
    return Moments(n, mean, std, skew, kurt, mean / std)


def _psr_from_moments(m: Moments, sr_benchmark: float) -> float:
    """Core PSR given precomputed moments and a benchmark Sharpe."""
    if m.std == 0.0:
        return float("nan")
    denom = math.sqrt(max(1e-12,
                          1.0 - m.skew * m.sharpe
                          + (m.kurt - 1.0) / 4.0 * m.sharpe ** 2))
    return norm_cdf((m.sharpe - sr_benchmark) * math.sqrt(m.n - 1) / denom)


def probabilistic_sharpe_ratio(returns, sr_benchmark: float = 0.0) -> float:
    """P(true Sharpe > sr_benchmark), skew/kurtosis-adjusted. In [0, 1]."""
    return _psr_from_moments(moments(returns), sr_benchmark)


def min_track_record_length(returns, sr_benchmark: float = 0.0,
                            confidence: float = 0.95) -> float:
    """Trades needed for observed Sharpe to beat the benchmark at `confidence`.
    Returns +inf when the observed Sharpe does not exceed the benchmark."""
    m = moments(returns)
    if m.sharpe <= sr_benchmark or m.std == 0.0:
        return float("inf")
    z = norm_ppf(confidence)
    adj = 1.0 - m.skew * m.sharpe + (m.kurt - 1.0) / 4.0 * m.sharpe ** 2
    return 1.0 + adj * (z / (m.sharpe - sr_benchmark)) ** 2


def deflated_sharpe_ratio(returns, n_trials: int,
                          trial_sharpe_variance: float | None = None,
                          all_trial_returns: list | None = None) -> dict:
    """DSR: PSR of the *selected* strategy against the Sharpe you'd expect the
    best of `n_trials` independent noise strategies to hit by luck.

    Supply the deflation input one of two ways:
      - all_trial_returns: list of return-arrays (one per configuration tried);
        the variance of their Sharpes and the winner are derived here, and
        `returns` may be omitted (the best trial is used).
      - trial_sharpe_variance: variance of Sharpes across trials, if you only
        kept the summary. `returns` must be the selected strategy's stream.

    Returns dict(dsr, expected_max_sharpe, observed_sharpe, n_trials).
    """
    if all_trial_returns:
        srs = np.array([moments(r).sharpe for r in all_trial_returns
                        if np.asarray(r, float).size >= 2])
        n_trials = max(n_trials, srs.size)
        trial_sharpe_variance = float(srs.var(ddof=1)) if srs.size > 1 else 0.0
        best_idx = int(np.argmax(srs))
        sel = all_trial_returns[best_idx]
    else:
        if trial_sharpe_variance is None:
            raise ValueError("provide all_trial_returns or trial_sharpe_variance")
        sel = returns

    m = moments(sel)
    N = max(2, int(n_trials))
    var = max(0.0, float(trial_sharpe_variance))
    # Expected maximum of N iid standard-normal Sharpes (Gumbel approximation),
    # scaled by the observed cross-trial Sharpe dispersion.
    expected_max = math.sqrt(var) * (
        (1 - _EULER) * norm_ppf(1 - 1.0 / N)
        + _EULER * norm_ppf(1 - 1.0 / (N * math.e)))
    dsr = _psr_from_moments(m, expected_max)
    return {"dsr": dsr,
            "expected_max_sharpe": expected_max,
            "observed_sharpe": m.sharpe,
            "n_trials": N}


# ---------------------------------------------------------------------------
# Profit factor & bootstrap
# ---------------------------------------------------------------------------

def profit_factor(returns) -> float:
    r = np.asarray(returns, float)
    gains = r[r > 0].sum()
    losses = -r[r < 0].sum()
    if losses == 0:
        return float("inf") if gains > 0 else float("nan")
    return float(gains / losses)


@dataclass
class BootstrapBands:
    metric: str
    point: float
    mean: float
    p05: float
    p50: float
    p95: float
    prob_positive: float


def bootstrap_metric(returns, metric: str = "avg_r", n_resamples: int = 2000,
                     seed: int = 0) -> BootstrapBands:
    """Resample trades with replacement to get a sampling distribution for a
    metric. `metric` in {avg_r, win_rate, profit_factor}. Gives the drawdown/
    stability bands the plain report can't: a positive point estimate whose 5th
    percentile is deeply negative is fragile."""
    r = np.asarray(returns, float)
    r = r[np.isfinite(r)]
    if r.size < 2:
        raise ValueError("need at least 2 returns to bootstrap")
    rng = np.random.default_rng(seed)

    def _calc(x):
        if metric == "avg_r":
            return float(x.mean())
        if metric == "win_rate":
            return float((x > 0).mean())
        if metric == "profit_factor":
            pf = profit_factor(x)
            return pf if math.isfinite(pf) else float("nan")
        raise ValueError(f"unknown metric {metric!r}")

    idx = rng.integers(0, r.size, size=(n_resamples, r.size))
    samples = np.array([_calc(r[row]) for row in idx])
    samples = samples[np.isfinite(samples)]
    threshold = 1.0 if metric == "profit_factor" else 0.0
    point = _calc(r)
    if samples.size == 0:                    # e.g. profit_factor with no losers
        nan = float("nan")
        return BootstrapBands(metric, point, nan, nan, nan, nan,
                              prob_positive=float("nan"))
    return BootstrapBands(
        metric=metric,
        point=point,
        mean=float(samples.mean()),
        p05=float(np.percentile(samples, 5)),
        p50=float(np.percentile(samples, 50)),
        p95=float(np.percentile(samples, 95)),
        prob_positive=float((samples > threshold).mean()),
    )


# ---------------------------------------------------------------------------
# Purge + embargo (index-level; for CV over weight/threshold choices)
# ---------------------------------------------------------------------------

def purge_embargo_split(n_samples: int, test_start: int, test_end: int,
                        horizon: int, embargo: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """Train/test index split with purging and embargo (LdP AFML ch.7).

    A setup composed at index i "uses" bars out to i+horizon, so any training
    sample whose evaluation window overlaps the test block leaks. Purge removes
    train samples within `horizon` before test_start; embargo additionally drops
    `embargo` samples after test_end. `test_start`/`test_end` are inclusive.
    Returns (train_idx, test_idx)."""
    all_idx = np.arange(n_samples)
    test = all_idx[test_start:test_end + 1]
    purge_lo = test_start - horizon
    embargo_hi = test_end + embargo
    train_mask = (all_idx < purge_lo) | (all_idx > embargo_hi)
    return all_idx[train_mask], test


# ---------------------------------------------------------------------------
# Report block appended to the Phase 8 report
# ---------------------------------------------------------------------------

def rigor_block(realized_r: list, n_trials: int = 1,
                trial_sharpe_variance: float | None = None,
                all_trial_returns: list | None = None,
                confidence: float = 0.95, seed: int = 0) -> dict:
    """Compute the full Phase 15 rigor summary from a list of realized R
    outcomes (None entries — unfilled setups — are dropped). Safe on tiny/degenerate
    samples: returns {available: False, reason} rather than raising."""
    r = np.asarray([x for x in realized_r if x is not None], float)
    r = r[np.isfinite(r)]
    if r.size < 3:
        return {"available": False,
                "reason": f"only {r.size} filled outcomes (need >= 3)"}
    if r.std(ddof=1) == 0.0:
        return {"available": False, "reason": "zero variance in outcomes"}

    m = moments(r)
    out = {
        "available": True,
        "n_filled": int(m.n),
        "sharpe_per_trade": round(m.sharpe, 4),
        "skew": round(m.skew, 4),
        "kurtosis": round(m.kurt, 4),
        "profit_factor": round(profit_factor(r), 4),
        "psr_vs_zero": round(probabilistic_sharpe_ratio(r, 0.0), 4),
        "min_track_record_length": round(min_track_record_length(r, 0.0, confidence), 1),
        "confidence": confidence,
    }
    want_dsr = n_trials > 1 or trial_sharpe_variance is not None or all_trial_returns
    if want_dsr and trial_sharpe_variance is None and not all_trial_returns:
        # DSR needs the Sharpe dispersion ACROSS the configurations you tried,
        # which a single run can't observe. Record intent + how to supply it,
        # rather than a scary error, and fall back to the un-deflated PSR.
        out["deflated_sharpe"] = {
            "skipped": True, "n_trials": int(n_trials),
            "reason": "no cross-trial Sharpe variance supplied; DSR needs the "
                      "spread of Sharpes across the configs you tuned. Pass "
                      "trial_sharpe_variance (or all_trial_returns) to deflate. "
                      "Until then, read psr_vs_zero as an UPPER bound."}
    elif want_dsr:
        try:
            d = deflated_sharpe_ratio(
                r, n_trials, trial_sharpe_variance=trial_sharpe_variance,
                all_trial_returns=all_trial_returns)
            out["deflated_sharpe"] = {k: (round(v, 4) if isinstance(v, float) else v)
                                      for k, v in d.items()}
        except Exception as exc:                       # never break the report
            out["deflated_sharpe"] = {"error": str(exc)}
    try:
        out["bootstrap"] = {
            m2: bootstrap_metric(r, m2, seed=seed).__dict__
            for m2 in ("avg_r", "win_rate", "profit_factor")
        }
    except Exception as exc:
        out["bootstrap"] = {"error": str(exc)}
    out["interpretation"] = _interpret(out)
    return _json_safe(out)


def _interpret(block: dict) -> str:
    psr = block.get("psr_vs_zero", 0.0)
    dsr = block.get("deflated_sharpe", {}).get("dsr")
    verdict = []
    if psr >= 0.95:
        verdict.append("PSR>=0.95: edge over zero is statistically credible")
    elif psr >= 0.75:
        verdict.append("PSR 0.75-0.95: suggestive, not conclusive")
    else:
        verdict.append("PSR<0.75: not distinguishable from no edge")
    if dsr is not None:
        if dsr >= 0.95:
            verdict.append("DSR>=0.95: survives selection-bias deflation")
        elif dsr >= 0.5:
            verdict.append("DSR 0.5-0.95: weakened once trials are counted")
        else:
            verdict.append("DSR<0.5: likely a selection artifact — do not promote")
    return "; ".join(verdict)


def render_rigor(block: dict) -> str:
    if not block.get("available"):
        return f"rigor: unavailable ({block.get('reason')})"

    def _fmt(v, spec="", na="n/a"):
        return na if v is None else format(v, spec)

    lines = [
        f"rigor: n={block['n_filled']} sharpe/trade={_fmt(block['sharpe_per_trade'])} "
        f"skew={_fmt(block['skew'])} kurt={_fmt(block['kurtosis'])} "
        f"pf={_fmt(block['profit_factor'])}",
        f"  PSR(>0)={_fmt(block['psr_vs_zero'])}  "
        f"MinTRL@{int(block['confidence']*100)}%={_fmt(block['min_track_record_length'])}",
    ]
    dblk = block.get("deflated_sharpe", {})
    if "dsr" in dblk:
        lines.append(f"  DSR={_fmt(dblk['dsr'])} (obs SR {_fmt(dblk['observed_sharpe'])} vs "
                     f"expected-max {_fmt(dblk['expected_max_sharpe'])} over "
                     f"{dblk['n_trials']} trials)")
    elif dblk.get("skipped"):
        lines.append(f"  DSR skipped ({dblk['n_trials']} trials declared, no "
                     f"cross-trial variance) — treat PSR as an upper bound")
    if "bootstrap" in block and isinstance(block["bootstrap"], dict) \
            and "avg_r" in block["bootstrap"]:
        b = block["bootstrap"]["avg_r"]
        lines.append(f"  bootstrap avg_R: p05={_fmt(b['p05'], '.3f')} "
                     f"p50={_fmt(b['p50'], '.3f')} p95={_fmt(b['p95'], '.3f')} "
                     f"P(>0)={_fmt(b['prob_positive'], '.3f')}")
    lines.append(f"  -> {block['interpretation']}")
    return "\n".join(lines)
