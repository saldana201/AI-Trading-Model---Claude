"""Phase 20d (rewritten, safe) — lever sweep, one lever per run.

The previous version had two serious bugs: it called update_config with the
default persist=True (writing to your confluence.json on every lever), and it
mutated global config in a loop without a clean reset, which could thrash for
hours. This version fixes both:

  - persist=False ALWAYS — it never touches your config file;
  - reset_cache() before every measurement, so levers can't contaminate;
  - ONE lever per invocation (--lever NAME), so a slow run is bounded and you
    see progress; nothing runs for hours behind your back;
  - a --max-points cap and progress dots so you always know it's alive.

Usage — run each lever you care about, compare the printed setup counts:

    CONFLUENCE_DATA=yfinance python -m scripts.lever_sweep --lever baseline --span 500
    CONFLUENCE_DATA=yfinance python -m scripts.lever_sweep --lever chop_soft --span 500
    CONFLUENCE_DATA=yfinance python -m scripts.lever_sweep --list

Start with --span 500 (faster). baseline first, then chop_soft — the delta
between those two is the answer to 'is the chop gate the real constraint?'.
"""

from __future__ import annotations

import argparse
import sys

from engines.shared.providers import ReplayProvider
from backtest.run import composer_factory_for
from scripts.snapshot import build_provider
from config import update_config, reset_cache


LEVERS = {
    "baseline": {},
    "chop_soft": {"gates": {"chop_mode": "soft"}},
    "rr_t2_1.5": {"risk": {"min_rr_t2": 1.5}},
    "geom": {"setup": {"max_stop_atr": 1.5, "t2_atr": 3.0}},
    "min_score_5": {"risk": {"min_score": 5.0}},
    "chop_soft+rr_1.5": {"gates": {"chop_mode": "soft"},
                         "risk": {"min_rr_t2": 1.5}},
    "all": {"gates": {"chop_mode": "soft"},
            "risk": {"min_rr_t2": 1.5, "min_score": 5.0},
            "setup": {"max_stop_atr": 1.5, "t2_atr": 3.0}},
}


def measure(lever: str, span: int, directions, max_points: int) -> dict:
    patch = LEVERS[lever]
    provider, source = build_provider()

    per_dir = {}
    for d in directions:
        # clean slate, then apply the patch in-memory only (never persisted)
        reset_cache()
        if patch:
            update_config(patch, persist=False)
        import os
        os.environ["CONFLUENCE_FORCE_DIRECTION"] = d

        replay = ReplayProvider(provider, start_offset=span)
        composer = composer_factory_for(source, False)(replay)
        setups = no_trade = points = 0
        limit = min(span, max_points)
        for i in range(limit):
            if not replay.advance():
                break
            p = composer.compose()
            points += 1
            if p.get("no_trade"):
                no_trade += 1
            setups += len(p.get("setups") or [])
            if points % 25 == 0:
                sys.stderr.write(".")
                sys.stderr.flush()
        per_dir[d] = {"points": points, "no_trade": no_trade, "setups": setups}
        sys.stderr.write(f" [{d}] {setups} setups\n")

    reset_cache()   # leave global state clean
    total = sum(v["setups"] for v in per_dir.values())
    return {"lever": lever, "patch": patch, "source": source,
            "total_setups": total, "by_direction": per_dir}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--lever", type=str, default="baseline",
                    help=f"one of: {', '.join(LEVERS)}")
    ap.add_argument("--span", type=int, default=500)
    ap.add_argument("--max-points", type=int, default=500,
                    help="hard cap on compose points, so a run is always bounded")
    ap.add_argument("--long-only", action="store_true")
    ap.add_argument("--list", action="store_true", help="list levers and exit")
    args = ap.parse_args()

    if args.list:
        for name, patch in LEVERS.items():
            print(f"  {name:<20} {patch}")
        return
    if args.lever not in LEVERS:
        print(f"unknown lever {args.lever!r}; choose from: {', '.join(LEVERS)}")
        return

    directions = ("long",) if args.long_only else ("long", "short")
    print(f"[sweep] lever={args.lever}  span={args.span}  "
          f"(config changes are in-memory only, your confluence.json is untouched)")
    r = measure(args.lever, args.span, directions, args.max_points)
    print(f"\n[sweep] {args.lever}: {r['total_setups']} total setups  "
          f"{ {k: v['setups'] for k, v in r['by_direction'].items()} }")
    nt = sum(v["no_trade"] for v in r["by_direction"].values())
    print(f"[sweep] no-trade short-circuits: {nt}")
    print(f"[sweep] patch applied (not saved): {r['patch']}")


if __name__ == "__main__":
    main()
