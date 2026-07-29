"""Phase 20 — component-weight re-fit under CPCV + walk-forward.

The problem this solves
-----------------------
The scorer's eleven weights were tuned against the *synthetic* world — a random
walk with a fixed drift map, no real VIX dynamics, no genuine rotation, no
earnings. On real SPY the validate_real run showed the consequence: a negative
gross edge (-0.0265R) and several components pointed the wrong way
(vix_alignment -0.269, risk_reward -0.123). The weights were fit to the wrong
distribution.

So we re-fit them to real data. But re-fitting is itself a search over
configurations, and reporting the in-sample performance of the winning weights
is exactly the selection bias that turns a +23% backtest into -22% live. The fit
must therefore be judged **only** on out-of-sample data, and the search must be
penalized for how hard it looked. That is what this module enforces.

The two-stage split
-------------------
This module never runs the composer. It operates on a *cached dataset* of
already-scored setups with known outcomes (built once by scripts/build_dataset.py):
each row is the eleven component values, a timestamp, symbol, direction, and the
realized R net of costs. Re-fitting weights is then just re-weighting a fixed
feature matrix — fast enough to run hundreds of folds.

The honesty guarantees
----------------------
1. **CPCV**: many out-of-sample paths, not one. Weights are fit on training
   blocks and scored on held-out blocks, with purge+embargo so a setup whose
   horizon overlaps the boundary cannot leak. The verdict is the *distribution*
   of path Sharpes — narrow+positive = robust, wide = fragile.
2. **Deflation**: the reported Sharpe is deflated for the number of weight
   vectors tried (Phase 15 DSR), so a lucky search does not read as an edge.
3. **Walk-forward cross-check**: a strict time-ordered fit/test as the final
   sanity pass, because that is the question a skeptic asks — "would it have
   worked in real time?"
4. **Non-negativity + normalization**: weights stay >= 0 and sum-normalized, so
   the re-fit produces a score in the same 0..10 units as today's and cannot
   express "this signal is good when inverted" — an inverted component gets
   weight ~0, which is the honest response to a signal that does not work,
   rather than betting the opposite.

The fit itself is a deterministic coordinate-ascent on out-of-sample mean R,
not a black-box optimizer, so it is reproducible and inspectable.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass, field

import numpy as np

from backtest.statistics import (
    moments, probabilistic_sharpe_ratio, deflated_sharpe_ratio,
    min_track_record_length,
)

# canonical component order — must match orchestrator/scoring.py WEIGHTS keys
COMPONENTS = [
    "vix_alignment", "index_alignment", "options_alignment", "sector_strength",
    "stock_relative_strength", "volume_rvol", "rsi_confirmation",
    "ma_structure", "risk_reward", "liquidity", "catalyst_fundamental",
]

CURRENT_WEIGHTS = {
    "vix_alignment": 1.4, "index_alignment": 1.2, "options_alignment": 1.1,
    "sector_strength": 1.2, "stock_relative_strength": 1.2, "volume_rvol": 1.0,
    "rsi_confirmation": 0.9, "ma_structure": 1.0, "risk_reward": 1.3,
    "liquidity": 0.8, "catalyst_fundamental": 1.0,
}


# ---------------------------------------------------------------------------
# Dataset container
# ---------------------------------------------------------------------------

@dataclass
class Dataset:
    """Cached scored setups. X is (n_rows, n_components) of component values in
    COMPONENTS order; r is realized R net of costs; t is an integer time index
    (sort key) used for purging; meta carries symbol/direction/date per row."""
    X: np.ndarray
    r: np.ndarray
    t: np.ndarray
    meta: list

    @classmethod
    def from_rows(cls, rows: list) -> "Dataset":
        """rows: list of dicts with 'components' (dict of name->value),
        'realized_r' (float, non-None), 't' (sortable), and optional meta."""
        keep = [row for row in rows
                if row.get("realized_r") is not None
                and all(np.isfinite([row["components"].get(c, 0.0)])
                        for c in COMPONENTS)]
        if not keep:
            raise ValueError("no usable rows (need realized_r and components)")
        X = np.array([[float(row["components"].get(c, 0.0)) for c in COMPONENTS]
                      for row in keep], float)
        r = np.array([float(row["realized_r"]) for row in keep], float)
        order = np.argsort([row.get("t", i) for i, row in enumerate(keep)])
        X, r = X[order], r[order]
        t = np.arange(len(keep))
        meta = [{"symbol": keep[i].get("symbol"),
                 "direction": keep[i].get("direction"),
                 "date": keep[i].get("date")} for i in order]
        return cls(X=X, r=r, t=t, meta=meta)

    def __len__(self):
        return len(self.r)


# ---------------------------------------------------------------------------
# Scoring and selection under a weight vector
# ---------------------------------------------------------------------------

def _normalize(w: np.ndarray) -> np.ndarray:
    w = np.clip(w, 0.0, None)
    s = w.sum()
    return w / s if s > 0 else np.ones_like(w) / len(w)


def scores(X: np.ndarray, w: np.ndarray) -> np.ndarray:
    """Per-row score in 0..10, matching scoring.py's raw/total*10 form."""
    return X @ _normalize(w) * 10.0


def selected_mean_r(X: np.ndarray, r: np.ndarray, w: np.ndarray,
                    threshold: float) -> tuple:
    """Mean realized R over rows whose score clears the threshold, and the count.
    This is the objective that matters: the weights change *which setups trade*,
    so we score the population the gate would actually admit, not all rows."""
    sc = scores(X, w)
    mask = sc >= threshold
    if mask.sum() == 0:
        return float("nan"), 0
    return float(r[mask].mean()), int(mask.sum())


# ---------------------------------------------------------------------------
# CPCV splits with purge + embargo
# ---------------------------------------------------------------------------

def cpcv_splits(n: int, n_blocks: int = 8, test_blocks: int = 2,
                horizon: int = 15, embargo: int = 5):
    """Yield (train_idx, test_idx) for every choice of `test_blocks` out of
    `n_blocks` contiguous time blocks, purging training rows whose horizon
    overlaps a test block and embargoing rows just after one.

    Raises ValueError if there are too few rows to form the requested blocks —
    CPCV is meaningless on a handful of samples, and a clear error beats an
    IndexError from an empty block."""
    if n < n_blocks * 2:
        raise ValueError(
            f"need at least {n_blocks * 2} rows for {n_blocks}-block CPCV, "
            f"got {n}. Build a larger dataset (more history / wider watchlist) "
            f"or reduce --blocks.")
    edges = np.linspace(0, n, n_blocks + 1).astype(int)
    blocks = [np.arange(edges[i], edges[i + 1]) for i in range(n_blocks)]
    blocks = [b for b in blocks if b.size > 0]
    if len(blocks) < n_blocks:
        raise ValueError(f"only {len(blocks)} non-empty blocks from {n} rows; "
                         f"reduce --blocks below {len(blocks)}")
    for combo in itertools.combinations(range(n_blocks), test_blocks):
        test = np.concatenate([blocks[b] for b in combo])
        test_set = set(test.tolist())
        train = []
        for i in range(n):
            if i in test_set:
                continue
            # purge: drop train rows within `horizon` before any test block start,
            # embargo: and within `embargo` after any test block end
            near = any(0 <= (blocks[b][0] - i) <= horizon or
                       0 <= (i - blocks[b][-1]) <= embargo for b in combo)
            if not near:
                train.append(i)
        if train and len(test):
            yield np.array(train), test


# ---------------------------------------------------------------------------
# The fit: deterministic coordinate ascent on out-of-sample mean R
# ---------------------------------------------------------------------------

def fit_weights_on(X: np.ndarray, r: np.ndarray, threshold: float,
                   init: np.ndarray | None = None, passes: int = 4,
                   grid: tuple = (0.0, 0.5, 0.8, 1.0, 1.2, 1.5, 2.0),
                   min_selected: int = 5) -> np.ndarray:
    """Coordinate ascent maximizing selected mean R on the given rows. Weights
    are clamped non-negative; a component that only hurts is driven toward 0.
    Deterministic given the same inputs. `search_count` is tracked by the caller
    for deflation."""
    k = X.shape[1]
    w = np.array(init, float) if init is not None else np.ones(k)

    def obj(wv):
        m, cnt = selected_mean_r(X, r, wv, threshold)
        if cnt < min_selected or not math.isfinite(m):
            return -1e9
        return m

    best = obj(w)
    for _ in range(passes):
        improved = False
        for j in range(k):
            base = w.copy()
            local_best, local_w = best, w
            for g in grid:
                cand = base.copy()
                cand[j] = g
                v = obj(cand)
                if v > local_best:
                    local_best, local_w, improved = v, cand, True
            w, best = local_w, local_best
        if not improved:
            break
    return _normalize(w)


@dataclass
class FitResult:
    weights: dict
    oos_paths: list          # per-fold out-of-sample mean R
    oos_trades: list         # per-fold trade counts
    path_sharpe: float
    psr: float
    deflated: dict
    n_folds: int
    n_weight_vectors_tried: int
    walk_forward: dict
    baseline: dict
    verdict: str


def _path_returns(X, r, w, threshold, test_idx):
    sc = scores(X[test_idx], w)
    mask = sc >= threshold
    return r[test_idx][mask]


def cpcv_fit(ds: Dataset, threshold: float = 6.0, n_blocks: int = 8,
             test_blocks: int = 2, horizon: int = 15, embargo: int = 5,
             passes: int = 4) -> FitResult:
    """Fit weights on each CPCV training split, evaluate on the held-out split,
    and judge on the pooled distribution of out-of-sample trade returns."""
    fold_means, fold_counts = [], []
    pooled_oos = []
    search_count = 0
    example_w = None

    for train_idx, test_idx in cpcv_splits(len(ds), n_blocks, test_blocks,
                                           horizon, embargo):
        w = fit_weights_on(ds.X[train_idx], ds.r[train_idx], threshold,
                           init=np.ones(len(COMPONENTS)), passes=passes)
        search_count += 1
        example_w = w
        oos = _path_returns(ds.X, ds.r, w, threshold, test_idx)
        if oos.size >= 3:
            fold_means.append(float(oos.mean()))
            fold_counts.append(int(oos.size))
            pooled_oos.extend(oos.tolist())

    # Final weights: fit once on ALL data (for deployment), but the honest
    # performance number is the OOS distribution above, never this fit's own R.
    final_w = fit_weights_on(ds.X, ds.r, threshold,
                             init=np.ones(len(COMPONENTS)), passes=passes)
    weights = {c: round(float(w), 4) for c, w in zip(COMPONENTS, final_w)}

    pooled = np.array(pooled_oos, float)
    if pooled.size >= 3 and pooled.std(ddof=1) > 0:
        m = moments(pooled)
        path_sharpe = m.sharpe
        psr = probabilistic_sharpe_ratio(pooled, 0.0)
        deflated = deflated_sharpe_ratio(
            pooled, n_trials=max(2, search_count),
            trial_sharpe_variance=(np.var(fold_means, ddof=1)
                                   if len(fold_means) > 1 else 0.0))
        deflated = {k: (round(v, 4) if isinstance(v, float) else v)
                    for k, v in deflated.items()}
    else:
        path_sharpe, psr, deflated = float("nan"), float("nan"), {}

    wf = _walk_forward(ds, threshold, horizon, embargo, passes)
    base = _baseline(ds, threshold)

    return FitResult(
        weights=weights,
        oos_paths=[round(x, 4) for x in fold_means],
        oos_trades=fold_counts,
        path_sharpe=round(path_sharpe, 4) if math.isfinite(path_sharpe) else None,
        psr=round(psr, 4) if math.isfinite(psr) else None,
        deflated=deflated,
        n_folds=len(fold_means),
        n_weight_vectors_tried=search_count + 1,
        walk_forward=wf,
        baseline=base,
        verdict=_verdict(path_sharpe, psr, deflated, wf, base, pooled),
    )


def _walk_forward(ds: Dataset, threshold, horizon, embargo, passes,
                  splits: int = 4) -> dict:
    """Strict time-ordered check: fit on [0, cut), test on [cut+embargo, next).
    The complement to CPCV — answers 'would it have worked in real time?'"""
    n = len(ds)
    if n < 40:
        return {"available": False, "reason": "too few rows for walk-forward"}
    edges = np.linspace(0, n, splits + 1).astype(int)
    oos = []
    for i in range(1, splits):
        cut = edges[i]
        train = np.arange(0, cut - horizon)              # purge the tail
        test = np.arange(cut + embargo, edges[i + 1])
        if len(train) < 20 or len(test) < 3:
            continue
        w = fit_weights_on(ds.X[train], ds.r[train], threshold,
                           init=np.ones(len(COMPONENTS)), passes=passes)
        seg = _path_returns(ds.X, ds.r, w, threshold, test)
        if seg.size:
            oos.extend(seg.tolist())
    if len(oos) < 3:
        return {"available": False, "reason": "walk-forward produced too few OOS trades"}
    arr = np.array(oos, float)
    return {"available": True, "n": int(arr.size),
            "avg_r": round(float(arr.mean()), 4),
            "win_rate": round(float((arr > 0).mean()), 4),
            "psr": round(probabilistic_sharpe_ratio(arr, 0.0), 4)
            if arr.std(ddof=1) > 0 else None}


def _baseline(ds: Dataset, threshold: float) -> dict:
    """Performance of the CURRENT weights on this dataset, for comparison."""
    w = np.array([CURRENT_WEIGHTS[c] for c in COMPONENTS], float)
    m, cnt = selected_mean_r(ds.X, ds.r, w, threshold)
    return {"weights": "current", "selected_avg_r": round(m, 4)
            if math.isfinite(m) else None, "selected_trades": cnt}


def _verdict(path_sharpe, psr, deflated, wf, base, pooled) -> str:
    if not (pooled.size >= 3 and math.isfinite(path_sharpe)):
        return "INCONCLUSIVE — too few out-of-sample trades to judge"
    dsr = deflated.get("dsr")
    parts = []
    if psr is not None and psr >= 0.95:
        parts.append("OOS PSR>=0.95")
    else:
        parts.append(f"OOS PSR={round(psr,3)} (<0.95)")
    if dsr is not None:
        parts.append(f"DSR={dsr}" + (" survives" if dsr >= 0.95 else " weak"))
    if wf.get("available"):
        wf_ok = (wf.get("psr") or 0) >= 0.9 and (wf.get("avg_r") or -1) > 0
        parts.append("walk-forward agrees" if wf_ok else "walk-forward disagrees")
    strong = (psr or 0) >= 0.95 and (dsr or 0) >= 0.95 and \
             wf.get("available") and (wf.get("avg_r") or -1) > 0
    head = ("RE-FIT IS TRUSTWORTHY" if strong
            else "DO NOT DEPLOY THESE WEIGHTS — did not clear OOS bar")
    return head + " | " + "; ".join(parts)


def render_fit(fr: FitResult) -> str:
    lines = [
        "component weight re-fit (CPCV + walk-forward)",
        f"  folds with OOS trades: {fr.n_folds}   "
        f"weight vectors tried: {fr.n_weight_vectors_tried}",
        f"  OOS path Sharpe: {fr.path_sharpe}   PSR(>0): {fr.psr}",
    ]
    if fr.deflated.get("dsr") is not None:
        lines.append(f"  Deflated Sharpe: {fr.deflated['dsr']}")
    if fr.oos_paths:
        arr = np.array(fr.oos_paths)
        lines.append(f"  per-fold OOS avg-R: min={arr.min():.3f} "
                     f"median={np.median(arr):.3f} max={arr.max():.3f}")
    wf = fr.walk_forward
    if wf.get("available"):
        lines.append(f"  walk-forward: n={wf['n']} avg_R={wf['avg_r']} "
                     f"PSR={wf['psr']}")
    lines.append(f"  baseline (current weights) selected avg-R: "
                 f"{fr.baseline.get('selected_avg_r')}")
    lines.append("  proposed weights:")
    for c in COMPONENTS:
        cur = CURRENT_WEIGHTS[c]
        new = fr.weights[c]
        arrow = "→" if abs(new - cur / sum(CURRENT_WEIGHTS.values())) > 0.01 else " "
        lines.append(f"    {c:<26} {new:.3f}")
    lines.append(f"  -> {fr.verdict}")
    return "\n".join(lines)
