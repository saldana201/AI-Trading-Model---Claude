"""Pre-fetch fundamentals for every watchlist ticker, once, with pacing.

The backtest calls get_snapshot per candidate per compose point. Uncached and
unpaced against a 143-ticker watchlist that is tens of thousands of Yahoo
requests — which throttles into curl-28 timeouts mid-run, and (worse) makes the
backtest non-deterministic because different symbols fail on each attempt.

Run this once before a backtest session:
    python -m scripts.warm_cache
    python -m scripts.warm_cache --refresh      # ignore existing cache
"""
from __future__ import annotations
import argparse, json, os, sys, time

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--watchlist", default="watchlist.json")
    ap.add_argument("--sleep", type=float, default=0.6,
                    help="seconds between requests (pacing to avoid throttling)")
    ap.add_argument("--refresh", action="store_true", help="ignore existing cache")
    args = ap.parse_args()

    from engines.fundamentals_mcp.logic import YFinanceFundamentals
    if args.refresh:
        YFinanceFundamentals._MEM = {}
        YFinanceFundamentals._DISK_LOADED = True

    with open(args.watchlist) as fh:
        wl = json.load(fh)
    syms = sorted({t for k, v in wl.items() if not k.startswith("_") for t in v})

    f = YFinanceFundamentals()
    cached = set(YFinanceFundamentals._MEM)
    todo = [s for s in syms if s not in cached] if not args.refresh else syms
    print(f"[warm] {len(syms)} tickers, {len(syms)-len(todo)} already cached, "
          f"fetching {len(todo)} (~{len(todo)*args.sleep/60:.1f} min at "
          f"{args.sleep}s pacing)")

    ok = fail = 0
    for i, s in enumerate(todo, 1):
        try:
            snap = f.get_snapshot(s)
            got = snap.get("sector") or snap.get("forward_pe")
            ok += 1 if got else 0
            fail += 0 if got else 1
            mark = "." if got else "x"
        except Exception:
            fail += 1; mark = "!"
        sys.stdout.write(mark); sys.stdout.flush()
        if i % 50 == 0:
            sys.stdout.write(f" {i}/{len(todo)}\n"); f.flush()
        time.sleep(args.sleep)
    f.flush()
    print(f"\n[warm] done: {ok} with data, {fail} empty/failed")
    print(f"[warm] cache -> {f.cache_path}")
    if fail:
        print("[warm] empty entries are cached too, so the run stays "
              "deterministic. Re-run with --refresh later to retry them.")

if __name__ == "__main__":
    main()
