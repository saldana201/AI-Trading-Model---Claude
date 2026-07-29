"""Phase 26 — the benchmark that decides it: vs buy-and-hold, and long vs short.

+0.287R/trade over 2022-2026 is only meaningful if it beats holding the index
over the same window. That period was a large-cap tech bull market, so a
long-biased strategy is swimming downstream. This is the comparison StockBench
found most LLM trading agents fail.

Also splits long vs short: if the short book is a drag, the "edge" is a
long-only edge wearing a two-sided costume.

Caveat on the return conversion: R-multiples -> portfolio return assumes fixed
fractional risk per trade, ignores overlap and compounding. It is an
order-of-magnitude comparison, not an equity curve.

Run:
    CONFLUENCE_DATA=yfinance python -m scripts.benchmark --span 1000 --chop-soft
"""
from __future__ import annotations
import argparse, os
import numpy as np
from backtest.harness import Backtest
from backtest.costs import CostModel
from backtest.run import composer_factory_for
from scripts.snapshot import build_provider
from engines.shared.providers import BarRequest
from backtest.statistics import probabilistic_sharpe_ratio, moments

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--span", type=int, default=1000)
    ap.add_argument("--step", type=int, default=5)
    ap.add_argument("--horizon", type=int, default=15)
    ap.add_argument("--chop-soft", action="store_true")
    ap.add_argument("--risk-pct", type=float, default=1.0,
                    help="%% of account risked per trade, for the R->return conversion")
    ap.add_argument("--bench", nargs="*", default=["SPY", "QQQ"])
    args = ap.parse_args()

    if args.chop_soft:
        from config import update_config, reset_cache
        reset_cache(); update_config({"gates": {"chop_mode": "soft"}}, persist=False)

    provider, source = build_provider()
    from scripts._fingerprint import emit
    emit(provider, "QQQ", args.span); print()
    factory = composer_factory_for(source, False)
    by_dir = {}
    for d in ("long", "short"):
        prev = os.environ.get("CONFLUENCE_FORCE_DIRECTION")
        os.environ["CONFLUENCE_FORCE_DIRECTION"] = d
        try:
            rep = Backtest(provider, factory, span_bars=args.span,
                           step_bars=args.step, horizon_bars=args.horizon,
                           cost_model=CostModel()).run()
        finally:
            if prev is None: os.environ.pop("CONFLUENCE_FORCE_DIRECTION", None)
            else: os.environ["CONFLUENCE_FORCE_DIRECTION"] = prev
        by_dir[d] = [float(o["realized_r"]) for o in rep["outcomes"]
                     if o.get("realized_r") is not None]

    print("DIRECTION SPLIT")
    allr = []
    for d, rs in by_dir.items():
        allr += rs
        if len(rs) >= 3:
            a = np.array(rs)
            print(f"  {d:<6} n={len(rs):<4} avg_R={a.mean():+.4f} "
                  f"win={(a>0).mean():.3f} totalR={a.sum():+.1f} "
                  f"PSR={probabilistic_sharpe_ratio(a,0.0):.4f}")
    a = np.array(allr)
    total_r = a.sum()
    notional = total_r * (args.risk_pct / 100.0) * 100.0
    print(f"\n  COMBINED n={len(a)} avg_R={a.mean():+.4f} totalR={total_r:+.1f}")
    print(f"  notional return at {args.risk_pct}%/trade: {notional:+.0f}% "
          f"(no compounding/overlap)")

    print("\nBUY-AND-HOLD, SAME WINDOW")
    for sym in args.bench:
        try:
            b = provider.get_bars(BarRequest(sym, "1d", args.span + 5))
            b = b.tail(args.span)
            ret = (float(b["close"].iloc[-1]) / float(b["close"].iloc[0]) - 1) * 100
            print(f"  {sym:<5} {ret:+.1f}%  ({len(b)} bars)")
        except Exception as e:
            print(f"  {sym:<5} unavailable ({e})")

    print("\n  -> If notional return does not clearly exceed buy-and-hold, the "
          "system is not adding value over holding the index — regardless of "
          "how good the per-trade stats look.")

if __name__ == "__main__":
    main()
