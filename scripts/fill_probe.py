"""Phase 22 — fill-rate diagnostic.

The investigation has converged on one wall: ~2/3 of composed setups never fill.
28 usable trades over 1000 bars is too few to fit, re-weight, or validate. The
entry is a breakout trigger ("break and hold above level X"), so a setup fills
only if price reaches the trigger within the horizon. This probe measures the
two things that determine whether that happens:

  1. how far the trigger sits above (long) / below (short) the price at compose
     time, as a fraction of ATR — a trigger 2 ATR away rarely fills in 15 bars;
  2. for the ones that DO fill, how many bars it took — if fills cluster at bar
     12-15, the horizon is the binding constraint; if triggers are 2+ ATR away,
     the trigger placement is.

It replays the composer, and for every setup checks — using the SAME forward
bars the backtest sees — whether and when price first touched the trigger. No
gates changed; this is pure measurement so the fix (widen horizon vs move
trigger vs loosen the hold condition) is chosen from evidence.

Run:
    CONFLUENCE_DATA=yfinance python -m scripts.fill_probe --span 1000 --horizon 15
"""

from __future__ import annotations

import argparse
import os
from collections import Counter

import numpy as np

from engines.shared.providers import ReplayProvider, BarRequest
from backtest.run import composer_factory_for
from scripts.snapshot import build_provider


def probe(span=1000, horizon=15, directions=("long", "short")) -> dict:
    provider, source = build_provider()
    factory = composer_factory_for(source, False)
    out = {"source": source, "span": span, "horizon": horizon, "by_direction": {}}

    for direction in directions:
        prev = os.environ.get("CONFLUENCE_FORCE_DIRECTION")
        os.environ["CONFLUENCE_FORCE_DIRECTION"] = direction
        # chop_soft so we actually get setups to measure
        from config import update_config, reset_cache
        reset_cache()
        update_config({"gates": {"chop_mode": "soft"}}, persist=False)
        try:
            base = provider  # full history for forward lookups
            replay = ReplayProvider(provider, start_offset=span)
            composer = factory(replay)

            trigger_dist_atr = []     # (trigger - price)/atr at compose
            fill_bars = []            # bars-to-fill for those that filled
            n_setups = 0
            n_touched = 0
            n_filled = 0
            step_idx = 0
            full = {}                 # symbol -> full bar frame (cached)

            for _ in range(span):
                if not replay.advance():
                    break
                step_idx += 1
                plan = composer.compose()
                for s in (plan.get("setups") or []):
                    n_setups += 1
                    sym = s["symbol"]
                    entry = s["entry_trigger"]
                    stop = s["stop"]
                    atr = max(abs(entry - stop) * 0.8, 1e-6)
                    # price the composer saw = last close of the replay's CURRENT
                    # view (this is exactly what compose used).
                    view = replay.get_bars(BarRequest(sym, "1d", span + 260))
                    if view is None or len(view) < 1:
                        continue
                    price = float(view["close"].iloc[-1])
                    dist = (entry - price) / atr if direction == "long" \
                        else (price - entry) / atr
                    trigger_dist_atr.append(dist)
                    # forward bars for the fill check: the full frame's rows AFTER
                    # the current view. The view has `vlen` bars; the full frame's
                    # bar vlen (0-indexed) is the first forward bar.
                    if sym not in full:
                        full[sym] = base.get_bars(
                            BarRequest(sym, "1d", span + horizon + 260))
                    fb = full[sym]
                    # align by the view's LAST TIMESTAMP into the full frame,
                    # so differing lookback lengths can't cause an off-by-N.
                    last_ts = view.index[-1]
                    pos = fb.index.get_indexer([last_ts])
                    asof = int(pos[0]) if pos[0] != -1 else len(view) - 1
                    # TWO conditions, to expose the gap:
                    #  - touch: high>=entry (long) — intraday reach
                    #  - fill:  close>entry (long) — the engine's real requirement
                    # (the backtest hardcodes rvol=99 so only close matters there)
                    touched_at = filled_at = None
                    for k in range(1, horizon + 1):
                        j = asof + k
                        if j >= len(fb):
                            break
                        hi = float(fb["high"].iloc[j])
                        lo = float(fb["low"].iloc[j])
                        cl = float(fb["close"].iloc[j])
                        touch = (hi >= entry) if direction == "long" else (lo <= entry)
                        fill = (cl > entry) if direction == "long" else (cl < entry)
                        if touch and touched_at is None:
                            touched_at = k
                        if fill:
                            filled_at = k
                            break
                    if touched_at is not None:
                        n_touched += 1
                    if filled_at is not None:
                        n_filled += 1
                        fill_bars.append(filled_at)
        finally:
            reset_cache()
            if prev is None:
                os.environ.pop("CONFLUENCE_FORCE_DIRECTION", None)
            else:
                os.environ["CONFLUENCE_FORCE_DIRECTION"] = prev

        out["by_direction"][direction] = _summ(
            trigger_dist_atr, fill_bars, n_setups, n_touched, n_filled, horizon)
    return out


def _summ(dist, fills, n_setups, n_touched, n_filled, horizon) -> dict:
    if n_setups == 0:
        return {"available": False, "reason": "no setups composed"}
    d = np.array(dist) if dist else np.array([0.0])
    res = {
        "available": True,
        "setups": n_setups,
        "touched": n_touched,
        "touch_rate": round(n_touched / n_setups, 3),
        "filled": n_filled,
        "fill_rate": round(n_filled / n_setups, 3),
        "trigger_distance_atr": {
            "median": round(float(np.median(d)), 3),
            "p25": round(float(np.percentile(d, 25)), 3),
            "p75": round(float(np.percentile(d, 75)), 3),
            "pct_within_1_atr": round(float((d <= 1.0).mean()), 3),
        },
    }
    if fills:
        f = np.array(fills)
        res["fill_timing"] = {
            "median_bars": float(np.median(f)),
            "pct_by_bar_5": round(float((f <= 5).mean()), 3),
            "pct_by_bar_10": round(float((f <= 10).mean()), 3),
            "pct_in_last_third": round(
                float((f > horizon * 2 / 3).mean()), 3),
        }
    return res


def render(d: dict) -> str:
    lines = [f"fill probe — source={d['source']} span={d['span']} "
             f"horizon={d['horizon']}", ""]
    for direction, r in d["by_direction"].items():
        lines.append(f"[{direction}]")
        if not r.get("available"):
            lines.append(f"  {r['reason']}"); lines.append(""); continue
        lines.append(f"  touch rate (price reaches trigger): {r['touch_rate']} "
                     f"({r['touched']}/{r['setups']})")
        lines.append(f"  FILL rate (closes beyond & holds): {r['fill_rate']} "
                     f"({r['filled']}/{r['setups']})")
        td = r["trigger_distance_atr"]
        lines.append(f"  trigger distance (ATR): median={td['median']} "
                     f"p25={td['p25']} p75={td['p75']}  "
                     f"within 1 ATR: {td['pct_within_1_atr']:.0%}")
        if "fill_timing" in r:
            ft = r["fill_timing"]
            lines.append(f"  when filled: median bar {ft['median_bars']}  "
                         f"by bar 5: {ft['pct_by_bar_5']:.0%}  "
                         f"by bar 10: {ft['pct_by_bar_10']:.0%}  "
                         f"in last third: {ft['pct_in_last_third']:.0%}")
        lines.append("")

    # verdict
    any_dir = next((r for r in d["by_direction"].values() if r.get("available")), None)
    if any_dir:
        touch = any_dir["touch_rate"]
        fill = any_dir["fill_rate"]
        gap = touch - fill
        if gap > 0.3:
            lines.append(f"DIAGNOSIS: price REACHES the trigger {touch:.0%} of the "
                         f"time but only CLOSES beyond it {fill:.0%} — a {gap:.0%} "
                         "gap. The 'break and hold (close beyond trigger)' rule is "
                         "the real fill constraint, not trigger distance or the "
                         "horizon. Options: (a) fill on an intraday touch instead "
                         "of a close, (b) use a limit entry AT the level rather "
                         "than a breakout-and-close, (c) accept the lower fill "
                         "rate as the cost of confirmation. Each is a real "
                         "strategy choice — measure the edge of filled trades "
                         "under each before deciding.")
        elif fill < 0.5:
            lines.append(f"DIAGNOSIS: fill rate {fill:.0%} and touch rate is "
                         "similar — price genuinely doesn't reach these triggers "
                         "often. Move entries closer or use pullback entries.")
        else:
            lines.append(f"DIAGNOSIS: fill rate {fill:.0%} is reasonable.")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--span", type=int, default=1000)
    ap.add_argument("--horizon", type=int, default=15)
    ap.add_argument("--long-only", action="store_true")
    args = ap.parse_args()
    directions = ("long",) if args.long_only else ("long", "short")
    print(render(probe(args.span, args.horizon, directions)))


if __name__ == "__main__":
    main()
