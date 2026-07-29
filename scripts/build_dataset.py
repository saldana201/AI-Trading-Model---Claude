"""Phase 20 Stage 1 — build the cached outcome dataset for the weight re-fit.

This is the slow half that needs data access, so it runs on your machine and
writes a cache the fast half (backtest.weight_fit) consumes. It replays the
composer across the full watchlist in BOTH directions, and for every setup it
would have generated it records:

  - the eleven component values (the features to re-weight),
  - the realized R net of costs (the label),
  - symbol, direction, and the compose timestamp (for time-ordered purging).

Why both directions: the validate_real run was SPY long-only, and the inverted
vix_alignment finding could be a long-only artifact. Fitting across the whole
watchlist and both sides is what tells you whether the inversion is real signal
or a narrow-sample fluke.

Run (from repo root, on your machine):

    CONFLUENCE_DATA=yfinance python -m scripts.build_dataset --span 500 \
        --out backtest/weight_dataset.json

Then fit (fast, anywhere):

    python -m scripts.fit_weights --dataset backtest/weight_dataset.json
"""

from __future__ import annotations

import argparse
import json

from backtest.harness import Backtest
from backtest.costs import CostModel, cost_in_r, apply_cost
from backtest.run import composer_factory_for
from scripts.snapshot import build_provider


def build_rows(span=500, step=5, horizon=15, with_options=False,
               directions=("long", "short"), cost_model=None) -> list:
    """Replay the composer both directions and emit one row per filled setup."""
    provider, source = build_provider()
    cost_model = cost_model or CostModel()
    factory = composer_factory_for(source, with_options)

    rows = []
    diag = {}
    for direction in directions:
        bt = Backtest(provider, factory, span_bars=span, step_bars=step,
                      horizon_bars=horizon, cost_model=cost_model)
        # force each direction so both sides of the book are scanned
        rep = bt.run(force_direction=direction) if _run_takes_force(bt) \
            else _run_forced(bt, direction)
        outs = rep["outcomes"]
        states = {}
        for o in outs:
            states[o.get("final_state", "?")] = states.get(
                o.get("final_state", "?"), 0) + 1
        filled = [o for o in outs if o.get("realized_r") is not None]
        diag[direction] = {
            "compose_points": rep.get("compose_points"),
            "no_trade_points": rep.get("no_trade_points"),
            "setups": len(outs), "filled": len(filled),
            "final_states": states}
        print(f"[dataset] {direction:>5}: {len(outs)} setups, {len(filled)} filled, "
              f"states={states}")
        for o in filled:
            comps = o.get("components") or {}
            rows.append({
                "components": comps,
                "realized_r": o["realized_r"],
                "gross_r": o.get("gross_r"),
                "t": o.get("as_of"),
                "symbol": o.get("symbol"),
                "direction": o.get("direction", direction),
                "date": o.get("as_of"),
            })
    # stable integer time index from the sortable as_of strings
    rows.sort(key=lambda r: str(r["t"]))
    for i, r in enumerate(rows):
        r["t"] = i
    return rows, diag


def _run_takes_force(bt) -> bool:
    import inspect
    return "force_direction" in inspect.signature(bt.run).parameters


def _run_forced(bt, direction: str):
    """Fallback when Backtest.run has no force_direction: set config gate."""
    import os
    prev = os.environ.get("CONFLUENCE_FORCE_DIRECTION")
    os.environ["CONFLUENCE_FORCE_DIRECTION"] = direction
    try:
        return bt.run()
    finally:
        if prev is None:
            os.environ.pop("CONFLUENCE_FORCE_DIRECTION", None)
        else:
            os.environ["CONFLUENCE_FORCE_DIRECTION"] = prev


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--span", type=int, default=500)
    ap.add_argument("--step", type=int, default=5)
    ap.add_argument("--horizon", type=int, default=15)
    ap.add_argument("--with-options", action="store_true")
    ap.add_argument("--long-only", action="store_true",
                    help="scan longs only (default scans both directions)")
    ap.add_argument("--slippage-bps", type=float, default=5.0)
    ap.add_argument("--chop-soft", action="store_true",
                    help="apply chop_mode=soft IN MEMORY for this build only "
                         "(never writes confluence.json). Use to build the "
                         "chop_soft dataset for the edge comparison.")
    ap.add_argument("--out", type=str, default="backtest/weight_dataset.json")
    args = ap.parse_args()

    directions = ("long",) if args.long_only else ("long", "short")
    cost_model = CostModel(slippage_bps=args.slippage_bps)

    if args.chop_soft:
        from config import update_config, reset_cache
        reset_cache()
        update_config({"gates": {"chop_mode": "soft"}}, persist=False)
        print("[dataset] chop_mode=soft applied IN MEMORY (confluence.json "
              "untouched)")

    provider, source = build_provider()
    print(f"[dataset] data source: {source}   "
          f"(set CONFLUENCE_DATA=yfinance for real data)")
    if source == "synthetic":
        print("[dataset] NOTE: synthetic data — fine for a wiring test, but the "
              "re-fit must be built on real data to mean anything.")
    print(f"[dataset] replaying {', '.join(directions)} over {args.span} bars…")

    rows, diag = build_rows(args.span, args.step, args.horizon,
                            args.with_options, directions, cost_model)
    by_dir = {}
    for r in rows:
        by_dir[r["direction"]] = by_dir.get(r["direction"], 0) + 1
    with open(args.out, "w") as fh:
        json.dump({"rows": rows, "meta": {
            "span": args.span, "step": args.step, "horizon": args.horizon,
            "directions": list(directions), "n_rows": len(rows),
            "by_direction": by_dir, "source": source, "diagnostics": diag}},
            fh, indent=2, default=str)
    print(f"[dataset] {len(rows)} filled setups ({by_dir}) -> {args.out}")

    if len(rows) < 60:
        print(f"\n[dataset] WARNING: only {len(rows)} rows — the fit will be "
              f"weak or impossible.\n[dataset] Where rows were lost:")
        for d, info in diag.items():
            nofill = info["final_states"].get("NO_FILL", 0)
            print(f"    {d:>5}: {info['setups']} setups composed, "
                  f"{nofill} never filled, {info['filled']} usable "
                  f"(no-trade gate hit {info['no_trade_points']}x)")
        print("[dataset] Fixes, in order of likelihood:\n"
              "    1. increase --span (e.g. 750 or 1000) for more history;\n"
              "    2. if one direction is ~0, that side rarely triggers in this "
              "period — expected, not a bug;\n"
              "    3. high NO_FILL means entry triggers rarely hit within the "
              "horizon — raise --horizon or we address fill realism next.")


if __name__ == "__main__":
    main()
