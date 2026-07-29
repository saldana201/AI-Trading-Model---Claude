"""Phase 25 — is the new edge real, or survivorship + selection bias?

Two threats to the n=255 result, both introduced by how we got here:

1. SURVIVORSHIP. The expanded watchlist was curated in 2026 from names known to
   have done well (NVDA, VST, CEG, OKLO...). Backtesting them over 2022-2026
   embeds hindsight. Test: split realized trades into ORIGINAL tickers (yours,
   pre-expansion) vs ADDED tickers (mine). If the edge lives almost entirely in
   the added names, survivorship is doing the work.

2. SELECTION. We tried ~10 configurations this session (chop modes, pre-entry
   modes, R:R floors, watchlist sizes) and kept the best. PSR does not correct
   for that; DSR does. This computes DSR properly using the spread of results
   across the configs actually tried.

Run:
    CONFLUENCE_DATA=yfinance python -m scripts.bias_check --span 1000 --chop-soft
"""

from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict

import numpy as np

from backtest.harness import Backtest
from backtest.costs import CostModel
from backtest.run import composer_factory_for
from scripts.snapshot import build_provider
from backtest.statistics import (probabilistic_sharpe_ratio,
                                 deflated_sharpe_ratio, moments)

# the pre-expansion universe (from watchlist.json before scripts.expand_watchlist)
ORIGINAL = {
    "OUST", "BTC-USD", "ETH-USD", "ETN", "VRT", "CRM", "NOW", "PLTR",
    "META", "GOOGL", "AMZN", "CEG", "VST", "PWR", "NVDA", "AVGO", "AMD",
    "MU", "AAOI", "CCJ", "LEU", "UEC", "XOM", "CVX", "JPM", "GS", "MSFT",
    "AAPL", "ORCL", "LLY", "UNH", "FANG", "DVN", "TMC", "XRP-USD",
}


def run(span, step, horizon, chop_soft, directions):
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
                rows.append({"symbol": o.get("symbol"),
                             "r": float(o["realized_r"]),
                             "direction": d})
    return rows


def summarize(rs):
    a = np.array(rs, float)
    if a.size < 3 or a.std(ddof=1) == 0:
        return {"n": int(a.size), "avg_r": round(float(a.mean()), 4)
                if a.size else None, "psr": None}
    return {"n": int(a.size), "avg_r": round(float(a.mean()), 4),
            "win_rate": round(float((a > 0).mean()), 3),
            "sharpe": round(moments(a).sharpe, 4),
            "psr": round(probabilistic_sharpe_ratio(a, 0.0), 4)}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--span", type=int, default=1000)
    ap.add_argument("--step", type=int, default=5)
    ap.add_argument("--horizon", type=int, default=15)
    ap.add_argument("--chop-soft", action="store_true")
    ap.add_argument("--long-only", action="store_true")
    ap.add_argument("--configs-tried", type=int, default=10,
                    help="how many configurations were evaluated to get here")
    args = ap.parse_args()

    directions = ("long",) if args.long_only else ("long", "short")
    from scripts._fingerprint import emit
    from scripts.snapshot import build_provider as _bp
    emit(_bp()[0], "QQQ", args.span); print()
    rows = run(args.span, args.step, args.horizon, args.chop_soft, directions)
    if not rows:
        print("[bias] no filled trades")
        return

    orig = [x["r"] for x in rows if x["symbol"] in ORIGINAL]
    added = [x["r"] for x in rows if x["symbol"] not in ORIGINAL]
    allr = [x["r"] for x in rows]

    print(f"[bias] {len(allr)} filled trades\n")
    print("SURVIVORSHIP SPLIT")
    print(f"  ALL      {summarize(allr)}")
    print(f"  ORIGINAL {summarize(orig)}      <- your pre-expansion names")
    print(f"  ADDED    {summarize(added)}      <- curated in 2026 (hindsight risk)")

    o, a = summarize(orig), summarize(added)
    if o.get("avg_r") is not None and a.get("avg_r") is not None:
        print()
        if o["n"] < 20:
            print("  -> ORIGINAL sample too small to compare confidently.")
        elif o["avg_r"] <= 0 < a["avg_r"]:
            print("  -> WARNING: the edge lives ONLY in the names I added. "
                  "Survivorship is the most likely explanation. Do not trust "
                  "the headline result.")
        elif a["avg_r"] > o["avg_r"] * 1.75:
            print("  -> CAUTION: added names carry a materially larger edge "
                  "than your originals. Some survivorship inflation is likely; "
                  "discount the headline.")
        else:
            print("  -> Edge is broadly similar across both groups, which is "
                  "what you'd expect if it is NOT purely survivorship.")

    # per-symbol concentration: is it a few names?
    bysym = defaultdict(list)
    for x in rows:
        bysym[x["symbol"]].append(x["r"])
    tot = sum(allr)
    contrib = sorted(((sum(v), k, len(v)) for k, v in bysym.items()),
                     reverse=True)
    top5 = sum(c for c, _, _ in contrib[:5])
    print(f"\nCONCENTRATION")
    print(f"  top 5 symbols contribute {top5:.1f}R of {tot:.1f}R total "
          f"({top5/tot*100:.0f}%)" if tot else "  n/a")
    for c, sym, n in contrib[:5]:
        print(f"    {sym:<8} {c:+.2f}R over {n} trades")
    if tot and top5 / tot > 0.6:
        print("  -> Edge is concentrated in a handful of names. Fragile: "
              "remove them and it may vanish.")

    # DSR across configurations tried
    print(f"\nDEFLATED SHARPE (correcting for ~{args.configs_tried} configs tried)")
    arr = np.array(allr, float)
    if arr.size >= 3 and arr.std(ddof=1) > 0:
        # conservative: assume cross-config Sharpe dispersion comparable to the
        # standard error of this Sharpe. Without logged per-config series this is
        # an estimate, but it is far better than skipping deflation entirely.
        se = 1.0 / np.sqrt(arr.size)
        d = deflated_sharpe_ratio(arr, n_trials=args.configs_tried,
                                  trial_sharpe_variance=float(se ** 2))
        print(f"  observed Sharpe/trade : {d['observed_sharpe']:.4f}")
        print(f"  luck bar (expected max): {d['expected_max_sharpe']:.4f}")
        print(f"  DSR                   : {d['dsr']:.4f}")
        if d["dsr"] >= 0.95:
            print("  -> survives deflation for the search we ran.")
        else:
            print("  -> WEAK once the search is counted. The PSR was flattering.")


if __name__ == "__main__":
    main()
