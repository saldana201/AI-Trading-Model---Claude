"""Phase 24 — expand the watchlist universe.

Why this and not another gate tweak
-----------------------------------
The funnel on real data is:

    197 compose points -> 31 setups -> 8 filled trades      (MinTRL needs 27+)

Every gate we tuned (chop, R:R, pre-entry invalidation) moved that by single
digits, because none of them was the binding constraint. The constraint is the
universe: 33 unique tickers at ~2.2 per sector. The rotation engine activates
roughly 9 sectors, so a compose point sees ~20 candidates — and after screen,
gates, and fills, 8 trades survive across 1000 bars.

Sample size is the only lever with the leverage to matter. Roughly 5x the names
gives roughly 5x the setups, which is the difference between "8 trades, cannot
conclude anything" and "100+ trades, PSR/DSR mean something."

Why a curated static map, not live ETF holdings
-----------------------------------------------
yfinance does not expose ETF constituents reliably, and scraping holdings pages
adds a fragile network dependency to a core config path. The membership of these
large-cap sector ETFs is stable enough that a curated map is the honest,
reproducible choice — and it is a plain JSON file you can edit.

What this does NOT do
---------------------
It does not touch `_pinned`, and it MERGES rather than replaces, so hand-picked
names survive. It also does not claim these are exact ETF holdings — they are
liquid, representative large/mid-caps for each sector theme. Liquidity matters
because the options engine needs real chains and the cost model needs tight
spreads.

Run:
    python -m scripts.expand_watchlist --dry-run      # show the diff
    python -m scripts.expand_watchlist                # write watchlist.json
    python -m scripts.expand_watchlist --per-sector 8 # cap names per sector
"""

from __future__ import annotations

import argparse
import json
import os
import shutil

# Liquid, representative names per sector theme. Ordered roughly by
# size/liquidity so --per-sector truncation keeps the most tradeable.
UNIVERSE: dict[str, list[str]] = {
    "SMH": ["NVDA", "AVGO", "AMD", "MU", "TSM", "QCOM", "INTC", "ADI", "KLAC",
            "LRCX", "AMAT", "NXPI", "MRVL", "ON", "MCHP", "AAOI"],
    "SOXX": ["NVDA", "AVGO", "AMD", "TSM", "QCOM", "TXN", "ADI", "KLAC",
             "LRCX", "AMAT", "MRVL", "MPWR", "SWKS", "TER"],
    "IGV": ["CRM", "NOW", "PLTR", "MSFT", "ORCL", "ADBE", "INTU", "PANW",
            "SNOW", "DDOG", "CRWD", "WDAY", "TEAM", "ZS", "MDB", "NET"],
    "XLK": ["MSFT", "AAPL", "ORCL", "NVDA", "AVGO", "CRM", "ACN", "ADBE",
            "AMD", "CSCO", "IBM", "INTU", "NOW", "TXN", "QCOM"],
    "MAGS": ["META", "GOOGL", "AMZN", "AAPL", "MSFT", "NVDA", "TSLA"],
    "XLF": ["JPM", "GS", "BAC", "WFC", "MS", "C", "SCHW", "BLK", "AXP",
            "SPGI", "CB", "PGR", "COF", "USB"],
    "XLV": ["LLY", "UNH", "JNJ", "ABBV", "MRK", "TMO", "ABT", "PFE", "AMGN",
            "DHR", "BSX", "ISRG", "VRTX", "REGN", "GILD"],
    "XLE": ["XOM", "CVX", "COP", "EOG", "SLB", "MPC", "PSX", "VLO", "OXY",
            "WMB", "KMI", "HAL", "DVN", "FANG"],
    "XOP": ["FANG", "DVN", "APA", "OVV", "MTDR", "SM", "CHRD", "MUR", "CTRA",
            "MRO", "PR", "AR"],
    "NLR": ["CEG", "VST", "NRG", "TLN", "BWXT", "SMR", "LEU", "OKLO"],
    "URA": ["CCJ", "LEU", "UEC", "DNN", "NXE", "UUUU", "SMR", "OKLO"],
    "URNM": ["CCJ", "UEC", "DNN", "NXE", "UUUU", "LEU", "SMR"],
    "GRID": ["ETN", "VRT", "PWR", "HUBB", "AME", "EMR", "ROK", "GEV", "NVT"],
    "PAVE": ["PWR", "ETN", "URI", "VMC", "MLM", "NUE", "CAT", "DE", "EMR",
             "FAST", "GVA", "ACM"],
    "ARKQ": ["OUST", "TSLA", "PATH", "TER", "AVAV", "KTOS", "TRMB", "MTLS"],
    "BTC": ["BTC-USD", "MSTR", "COIN", "MARA", "RIOT", "CLSK", "HUT"],
    "ETH": ["ETH-USD", "COIN", "BMNR"],
}


def load_json(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    with open(path) as fh:
        return json.load(fh)


def expand(current: dict, per_sector: int | None = None,
           only: list[str] | None = None) -> tuple[dict, dict]:
    """Merge UNIVERSE into `current`. Returns (new_watchlist, per-sector added)."""
    out = {k: list(v) for k, v in current.items()}
    added: dict[str, list[str]] = {}

    for etf, names in UNIVERSE.items():
        if only and etf not in only:
            continue
        existing = list(out.get(etf, []))
        merged = list(existing)
        for t in names:
            if t not in merged:
                merged.append(t)
        if per_sector:
            # keep every pre-existing name, then fill up to the cap
            keep = [t for t in merged if t in existing]
            fill = [t for t in merged if t not in existing]
            merged = keep + fill[:max(0, per_sector - len(keep))]
        new_only = [t for t in merged if t not in existing]
        if new_only:
            added[etf] = new_only
        out[etf] = merged
    return out, added


def stats(wl: dict) -> dict:
    sectors = [k for k in wl if not k.startswith("_")]
    slots = sum(len(wl[k]) for k in sectors)
    uniq = {t for k in sectors for t in wl[k]}
    return {"sectors": len(sectors), "slots": slots, "unique": len(uniq),
            "avg_per_sector": round(slots / max(1, len(sectors)), 1)}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--path", default="watchlist.json")
    ap.add_argument("--per-sector", type=int, default=None,
                    help="cap names per sector (existing names always kept)")
    ap.add_argument("--only", nargs="*", default=None,
                    help="expand only these sector ETFs")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the diff, write nothing")
    ap.add_argument("--no-backup", action="store_true")
    args = ap.parse_args()

    current = load_json(args.path)
    if not current:
        print(f"[expand] {args.path} not found or empty — nothing to merge into.")
        return

    before = stats(current)
    new, added = expand(current, args.per_sector, args.only)
    after = stats(new)

    print(f"[expand] before: {before['unique']} unique tickers across "
          f"{before['sectors']} sectors (avg {before['avg_per_sector']}/sector)")
    for etf in sorted(added):
        print(f"    {etf:<6} +{len(added[etf]):<3} {', '.join(added[etf])}")
    print(f"[expand] after:  {after['unique']} unique tickers "
          f"(avg {after['avg_per_sector']}/sector)  "
          f"= {after['unique'] / max(1, before['unique']):.1f}x")

    pinned = current.get("_pinned")
    if pinned:
        print(f"[expand] _pinned untouched: {pinned}")

    if args.dry_run:
        print("\n[expand] dry run — nothing written. Drop --dry-run to apply.")
        return

    if not args.no_backup and os.path.exists(args.path):
        shutil.copy(args.path, args.path + ".bak")
        print(f"[expand] backup -> {args.path}.bak")

    with open(args.path, "w") as fh:
        json.dump(new, fh, indent=2, sort_keys=True)
    print(f"[expand] wrote {args.path}")
    print("\n[expand] NEXT: more names means more setups, but a bigger universe "
          "is also a bigger search — re-run validate_real and treat the result "
          "with the SAME rigor bar (PSR/DSR). More trades makes the statistics "
          "meaningful; it does not by itself make the edge real.")


if __name__ == "__main__":
    main()
