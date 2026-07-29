"""Phase 28 — the last fair test: risk-adjusted return and drawdown.

The raw-return comparison says the system loses: +53% notional vs QQQ +113.5%.
But that compares a roughly market-neutral book (243 long / 242 short, each
capped at 1R) against a 100%-long index that ate its full 2022 drawdown. Raw
return is the wrong axis for that comparison; risk-adjusted return is the right
one.

This builds an equity curve from realized trades and reports max drawdown,
Sharpe, Sortino and Calmar against the benchmark's own. If the book delivers
+52.7R with a shallow drawdown while QQQ took a deep one, that is a genuinely
different product that can be run at higher risk-per-trade. If the drawdown is
deep too, the answer is simply no.

Honest limits of this measurement
---------------------------------
- Equity is marked at trade EXIT, so this is realized-trade drawdown. Open
  positions moving against you between entry and exit are invisible. True
  drawdown is therefore WORSE than reported here — treat these numbers as a
  floor, not an estimate.
- Fixed fractional risk per trade, no compounding within a day, and no cap on
  concurrent positions. Real capital constraints would bind.
- Overlapping trades are summed on their exit day, which understates
  intra-period volatility.

Run:
    CONFLUENCE_DATA=yfinance python -m scripts.risk_adjusted --span 1000 --chop-soft
"""

from __future__ import annotations

import argparse
import os
from collections import defaultdict

import numpy as np

from backtest.harness import Backtest
from backtest.costs import CostModel
from backtest.run import composer_factory_for
from scripts.snapshot import build_provider
from engines.shared.providers import BarRequest

TRADING_DAYS = 252


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
                rows.append({"as_of": str(o.get("as_of"))[:10],
                             "r": float(o["realized_r"]),
                             "bars_held": int(o.get("bars_held") or 0),
                             "direction": d})
    return rows, provider


def metrics(daily_returns: np.ndarray, equity: np.ndarray) -> dict:
    r = daily_returns[np.isfinite(daily_returns)]
    if r.size < 10:
        return {}
    mu, sd = float(r.mean()), float(r.std(ddof=1))
    downside = r[r < 0]
    dsd = float(downside.std(ddof=1)) if downside.size > 1 else 0.0
    peak = np.maximum.accumulate(equity)
    dd = (equity - peak) / np.where(peak == 0, 1, peak)
    max_dd = float(dd.min()) * 100
    years = max(r.size / TRADING_DAYS, 1e-9)
    total = float(equity[-1] / equity[0] - 1) * 100
    cagr = ((equity[-1] / equity[0]) ** (1 / years) - 1) * 100
    return {
        "total_return_pct": round(total, 1),
        "cagr_pct": round(cagr, 1),
        "max_drawdown_pct": round(max_dd, 1),
        "sharpe": round(mu / sd * np.sqrt(TRADING_DAYS), 3) if sd > 0 else None,
        "sortino": round(mu / dsd * np.sqrt(TRADING_DAYS), 3) if dsd > 0 else None,
        "calmar": round(cagr / abs(max_dd), 3) if max_dd < 0 else None,
        "days": int(r.size),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--span", type=int, default=1000)
    ap.add_argument("--step", type=int, default=5)
    ap.add_argument("--horizon", type=int, default=15)
    ap.add_argument("--chop-soft", action="store_true")
    ap.add_argument("--risk-pct", type=float, default=1.0)
    ap.add_argument("--bench", nargs="*", default=["QQQ", "SPY"])
    ap.add_argument("--long-only", action="store_true")
    args = ap.parse_args()

    directions = ("long",) if args.long_only else ("long", "short")
    rows, provider = collect(args.span, args.step, args.horizon,
                             args.chop_soft, directions)
    from scripts._fingerprint import emit
    emit(provider, args.bench[0], args.span)
    print()
    if len(rows) < 20:
        print(f"[risk] only {len(rows)} trades — not enough for a curve")
        return

    # calendar from the benchmark, so strategy and benchmark share an axis
    b = provider.get_bars(BarRequest(args.bench[0], "1d", args.span + 5)).tail(args.span)
    cal = [str(x)[:10] for x in b.index]
    pos = {d: i for i, d in enumerate(cal)}

    # attribute each trade's R to its EXIT day
    by_day = defaultdict(float)
    unplaced = 0
    for x in rows:
        i = pos.get(x["as_of"])
        if i is None:
            unplaced += 1
            continue
        j = min(i + max(x["bars_held"], 1), len(cal) - 1)
        by_day[cal[j]] += x["r"]

    frac = args.risk_pct / 100.0
    eq = [1.0]
    daily = []
    for d in cal:
        ret = by_day.get(d, 0.0) * frac
        daily.append(ret)
        eq.append(eq[-1] * (1 + ret))
    eq = np.array(eq[1:])
    daily = np.array(daily)

    strat = metrics(daily, eq)
    print(f"STRATEGY  ({len(rows)} trades, {args.risk_pct}% risk/trade, "
          f"{unplaced} unplaced)")
    for k, v in strat.items():
        print(f"    {k:<20} {v}")

    # concurrency: how much capital was actually at risk at once
    open_count = np.zeros(len(cal), dtype=int)
    for x in rows:
        i = pos.get(x["as_of"])
        if i is None:
            continue
        j = min(i + max(x["bars_held"], 1), len(cal) - 1)
        open_count[i:j + 1] += 1
    peak = int(open_count.max())
    print(f"    {'peak_open_positions':<20} {peak}")
    print(f"    {'peak_capital_at_risk':<20} {peak * args.risk_pct:.1f}% "
          f"of account")
    if peak * args.risk_pct > 20:
        print(f"    !! {peak} concurrent positions at {args.risk_pct}% each "
              f"means {peak * args.risk_pct:.0f}% of the account at risk "
              f"simultaneously. The reported drawdown does NOT reflect this — "
              f"a correlated move against a full book is the real tail risk.")

    print("\nBENCHMARK (buy & hold, same window)")
    bench_metrics = {}
    for sym in args.bench:
        try:
            bb = provider.get_bars(BarRequest(sym, "1d", args.span + 5)).tail(args.span)
            c = bb["close"].astype(float).to_numpy()
            dr = np.diff(c) / c[:-1]
            m = metrics(dr, c[1:])
            bench_metrics[sym] = m
            print(f"  {sym}")
            for k, v in m.items():
                print(f"    {k:<20} {v}")
        except Exception as e:
            print(f"  {sym}: unavailable ({e})")

    # verdict
    print("\nRISK-ADJUSTED VERDICT")
    q = bench_metrics.get(args.bench[0], {})
    if strat and q:
        s_sh, b_sh = strat.get("sharpe"), q.get("sharpe")
        s_dd, b_dd = strat.get("max_drawdown_pct"), q.get("max_drawdown_pct")
        s_cal, b_cal = strat.get("calmar"), q.get("calmar")
        print(f"  Sharpe   strategy {s_sh}  vs  {args.bench[0]} {b_sh}")
        print(f"  MaxDD    strategy {s_dd}%  vs  {args.bench[0]} {b_dd}%")
        print(f"  Calmar   strategy {s_cal}  vs  {args.bench[0]} {b_cal}")
        print()
        if s_sh and b_sh and s_sh > b_sh and s_dd and b_dd and abs(s_dd) < abs(b_dd):
            print("  -> BETTER RISK-ADJUSTED on these numbers: shallower "
                  "realized-trade drawdown and higher Sharpe than the index.")
            print("     DO NOT read this as a licence to size up. The drawdown "
                  "here counts only CLOSED trades — every adverse move while a "
                  "position was open is invisible, and concurrent positions are "
                  "uncapped. Real drawdown is materially worse, so any implied "
                  "leverage multiple from these figures is fiction.")
            if strat.get("sharpe", 0) > 3:
                print("     A Sharpe above 3 from a daily-bar swing system is "
                      "not credible on its own — treat it as a sign the equity "
                      "construction is flattering (lumpy exit-day marking "
                      "understates volatility), not as a discovery.")
        elif s_sh and b_sh and s_sh > b_sh:
            print("  -> Higher Sharpe but not a shallower drawdown. Modest "
                  "improvement; sizing up is limited by the drawdown.")
        else:
            print("  -> NOT better risk-adjusted either. The index wins on both "
                  "return and risk. This system does not currently justify "
                  "itself over buying the index.")
    print("\n  NOTE: equity is marked at trade EXIT, so open-position drawdown "
          "is invisible. True drawdown is WORSE than shown — a floor, not an "
          "estimate.")


if __name__ == "__main__":
    main()
