"""Phase 27 — walk-forward stability: does the edge hold across time?

What this tests, and what it honestly cannot
--------------------------------------------
Every configuration choice we made (chop_soft, the expanded watchlist,
pre-entry mode) was informed by results computed over the FULL span. So no
segment of this data is a pristine holdout — the last 250 bars influenced our
decisions just as much as the first 250. Claiming otherwise would be dishonest.

What this CAN do is answer the next-best question: **is the edge stable across
time, or does it live in one favourable stretch?** An edge that appears in every
sub-period is far more likely to be structural. An edge concentrated in one
block is a regime artifact wearing a 486-trade costume.

It slices one backtest run by trade date into consecutive blocks and reports the
edge in each, alongside the index return over the same block — so you can see
whether the system holds up when the market was flat or falling, not just when
it ran.

Run:
    CONFLUENCE_DATA=yfinance python -m scripts.walk_forward --span 1000 --chop-soft --blocks 4
"""

from __future__ import annotations

import argparse
import os

import numpy as np

from backtest.harness import Backtest
from backtest.costs import CostModel
from backtest.run import composer_factory_for
from scripts.snapshot import build_provider
from engines.shared.providers import BarRequest
from backtest.statistics import probabilistic_sharpe_ratio, moments


def collect(span, step, horizon, chop_soft, directions):
    if chop_soft:
        from config import update_config, reset_cache
        reset_cache()
        update_config({"gates": {"chop_mode": "soft"}}, persist=False)
    provider, source = build_provider()
    factory = composer_factory_for(source, False)
    rows = []
    for d in directions:
        prev = os.environ.get("CONFLUENCE_FORCE_DIRECTION")
        os.environ["CONFLUENCE_FORCE_DIRECTION"] = d
        try:
            rep = Backtest(provider, factory, span_bars=span, step_bars=step,
                           horizon_bars=horizon, cost_model=CostModel()).run()
        finally:
            if prev is None:
                os.environ.pop("CONFLUENCE_FORCE_DIRECTION", None)
            else:
                os.environ["CONFLUENCE_FORCE_DIRECTION"] = prev
        for o in rep["outcomes"]:
            if o.get("realized_r") is not None:
                rows.append({"as_of": str(o.get("as_of")),
                             "r": float(o["realized_r"]),
                             "direction": d,
                             "symbol": o.get("symbol")})
    rows.sort(key=lambda x: x["as_of"])
    return rows, provider


def stats(rs):
    a = np.array(rs, float)
    if a.size < 3 or a.std(ddof=1) == 0:
        return None
    return {"n": int(a.size), "avg_r": float(a.mean()),
            "win": float((a > 0).mean()), "total_r": float(a.sum()),
            "psr": float(probabilistic_sharpe_ratio(a, 0.0)),
            "sharpe": float(moments(a).sharpe)}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--span", type=int, default=1000)
    ap.add_argument("--step", type=int, default=5)
    ap.add_argument("--horizon", type=int, default=15)
    ap.add_argument("--blocks", type=int, default=4)
    ap.add_argument("--chop-soft", action="store_true")
    ap.add_argument("--long-only", action="store_true")
    ap.add_argument("--bench", default="QQQ")
    ap.add_argument("--risk-pct", type=float, default=1.0)
    args = ap.parse_args()

    directions = ("long",) if args.long_only else ("long", "short")
    rows, provider = collect(args.span, args.step, args.horizon,
                             args.chop_soft, directions)
    from scripts._fingerprint import emit
    emit(provider, args.bench, args.span)
    print()
    if len(rows) < args.blocks * 5:
        print(f"[wf] only {len(rows)} trades — too few to slice into "
              f"{args.blocks} blocks")
        return

    # index bars for per-block benchmark
    try:
        b = provider.get_bars(BarRequest(args.bench, "1d", args.span + 5)).tail(args.span)
        bench_dates = [str(x) for x in b.index]
        bench_close = b["close"].astype(float).tolist()
    except Exception:
        bench_dates, bench_close = [], []

    def bench_return(d0, d1):
        if not bench_dates:
            return None
        try:
            i0 = next(i for i, d in enumerate(bench_dates) if d >= d0)
            i1 = max(i for i, d in enumerate(bench_dates) if d <= d1)
            if i1 <= i0:
                return None
            return (bench_close[i1] / bench_close[i0] - 1) * 100
        except (StopIteration, ValueError):
            return None

    edges = np.linspace(0, len(rows), args.blocks + 1).astype(int)
    print(f"[wf] {len(rows)} trades sliced into {args.blocks} time blocks "
          f"(benchmark: {args.bench})\n")
    print(f"  {'block':<7}{'period':<26}{'n':>5}{'avg_R':>9}{'win':>7}"
          f"{'totR':>8}{'PSR':>8}{'notional':>10}{'bench':>9}")

    per_block = []
    for i in range(args.blocks):
        seg = rows[edges[i]:edges[i + 1]]
        if not seg:
            continue
        st = stats([x["r"] for x in seg])
        d0, d1 = seg[0]["as_of"][:10], seg[-1]["as_of"][:10]
        br = bench_return(seg[0]["as_of"], seg[-1]["as_of"])
        if st:
            notional = st["total_r"] * args.risk_pct
            per_block.append((st, br, notional))
            bs = f"{br:+.1f}%" if br is not None else "n/a"
            print(f"  {i+1:<7}{d0}..{d1:<12}{st['n']:>5}{st['avg_r']:>+9.3f}"
                  f"{st['win']:>7.3f}{st['total_r']:>+8.1f}{st['psr']:>8.3f}"
                  f"{notional:>+9.0f}%{bs:>9}")

    # verdict
    print()
    if per_block:
        avgs = [s["avg_r"] for s, _, _ in per_block]
        pos = sum(1 for a in avgs if a > 0)
        psrs = [s["psr"] for s, _, _ in per_block]
        print(f"  blocks with positive edge: {pos}/{len(avgs)}")
        print(f"  avg_R range: {min(avgs):+.3f} to {max(avgs):+.3f}")
        beat = [1 for s, br, nt in per_block if br is not None and nt > br]
        if any(br is not None for _, br, _ in per_block):
            print(f"  blocks beating {args.bench}: {len(beat)}/"
                  f"{sum(1 for _, br, _ in per_block if br is not None)}")
        print()
        if pos == len(avgs) and min(psrs) > 0.8:
            print("  -> STABLE: positive in every block. The edge is not confined "
                  "to one favourable stretch, which is the strongest evidence "
                  "available short of true out-of-sample data.")
        elif pos >= len(avgs) - 1:
            print("  -> MOSTLY STABLE: positive in all but one block. Reasonable, "
                  "but check what happened in the weak block — that regime is "
                  "where this system struggles.")
        else:
            print("  -> UNSTABLE: the edge appears in some periods and not "
                  "others. The headline number is a blend of a good regime and "
                  "a bad one; treat the full-sample result as unreliable.")
        print("\n  NOTE: every config choice was made using this full sample, so "
              "no block here is a true holdout. This measures STABILITY, not "
              "out-of-sample performance. The only clean test is forward paper "
              "trading on data that does not exist yet.")


if __name__ == "__main__":
    main()
