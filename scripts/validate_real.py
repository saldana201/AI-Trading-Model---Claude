"""Step B — point the whole rigor stack at real market data.

Everything built in Phases 15-18 is machinery for detecting a *weak* edge. So
far it has only run against the synthetic world, where the edge is inflated
(~11x cost headroom) and none of the guards ever bite. This script is the
moment of truth: same harness, real bars, costs on, deflation on.

Run (from the repo root):

    CONFLUENCE_DATA=yfinance python -m scripts.validate_real
    CONFLUENCE_DATA=yfinance python -m scripts.validate_real --span 500 --trials 8

`--trials` matters. Set it to the number of distinct weight/threshold
configurations you have tried against this data over the project's life. If you
have tuned five times and kept the best, that is five trials, and the Deflated
Sharpe Ratio should know. Understating it is how a backtest flatters itself.

What to look for, in order of severity:

  1. sign_flip_under_costs = True   -> stop. The edge is gross-only.
  2. cost headroom < 2x             -> fragile to worse fills or wider spreads.
  3. PSR < 0.95                     -> not statistically distinguishable from no edge.
  4. n_filled < MinTRL              -> not enough trades to know yet, either way.
  5. bootstrap p05 deeply negative  -> the average hides a wide, ugly tail.

A result that fails these is not a failure of the run. It is the system telling
you something true that the pre-Phase-15 reports could not express.
"""

from __future__ import annotations

import argparse
import json
import os

from backtest.harness import Backtest, render_text
from backtest.costs import CostModel
from backtest.run import composer_factory_for
from scripts.snapshot import build_provider


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--span", type=int, default=400, help="bars of history")
    ap.add_argument("--step", type=int, default=5, help="compose every N bars")
    ap.add_argument("--horizon", type=int, default=15, help="max bars per trade")
    ap.add_argument("--trials", type=int, default=1,
                    help="configurations you have tried against this data")
    ap.add_argument("--trial-sharpe-variance", type=float, default=None,
                    help="variance of Sharpes across those configs, if known")
    ap.add_argument("--slippage-bps", type=float, default=5.0)
    ap.add_argument("--commission-per-share", type=float, default=0.005)
    ap.add_argument("--option-spread-pct", type=float, default=None)
    ap.add_argument("--with-options", action="store_true",
                    help="attach the options engine (synthetic chains only — "
                         "yfinance has no historical chains, so on real price "
                         "data this models today's chain against past bars)")
    ap.add_argument("--chop-soft", action="store_true",
                    help="apply chop_mode=soft in memory for this run only")
    ap.add_argument("--preentry", type=str, default=None,
                    choices=["stop", "none", "wide"],
                    help="pre-entry invalidation mode, in memory for this run: "
                         "stop=legacy (setup abandoned at the stop), "
                         "none=never abandon pre-entry, "
                         "wide=abandon 1 ATR beyond the stop")
    ap.add_argument("--json", type=str, default=None, help="write results here")
    args = ap.parse_args()

    _patch = {}
    if args.chop_soft:
        _patch.setdefault("gates", {})["chop_mode"] = "soft"
    if args.preentry:
        _patch.setdefault("gates", {})["preentry_invalidation"] = args.preentry
    if _patch:
        from config import update_config, reset_cache
        reset_cache()
        update_config(_patch, persist=False)
        print(f"[validate] applied IN MEMORY (config untouched): {_patch}")

    source_env = os.environ.get("CONFLUENCE_DATA", "yfinance")
    provider, source = build_provider()
    from scripts._fingerprint import emit
    emit(provider, "QQQ", args.span)
    print(f"[validate] data source: {source} (CONFLUENCE_DATA={source_env})")
    if source == "synthetic":
        print("[validate] WARNING: this is the synthetic world. The edge here is "
              "inflated and the guards will not bite. Set CONFLUENCE_DATA=yfinance "
              "for a real answer.")

    cost_model = CostModel(
        slippage_bps=args.slippage_bps,
        commission_per_share=args.commission_per_share,
        option_spread_pct=args.option_spread_pct,
    )

    bt = Backtest(provider, composer_factory_for(source, args.with_options),
                  span_bars=args.span, step_bars=args.step,
                  horizon_bars=args.horizon, n_trials=args.trials,
                  trial_sharpe_variance=args.trial_sharpe_variance,
                  cost_model=cost_model)
    rep = bt.run()

    print()
    print(render_text(rep))
    print()
    print(_verdict(rep))

    if args.json:
        with open(args.json, "w") as fh:
            json.dump(rep, fh, indent=2, default=str)
        print(f"\n[validate] full results -> {args.json}")


def _verdict(rep: dict) -> str:
    """A single readout, so the answer is not buried in the numbers."""
    costs = rep.get("costs") or {}
    rigor = rep.get("rigor") or {}
    fails, warns = [], []

    if costs.get("available"):
        if costs.get("sign_flip_under_costs"):
            fails.append("EDGE DIES UNDER COSTS — gross positive, net negative")
        head = costs.get("cost_headroom_x")
        if head is not None and head < 2:
            warns.append(f"thin cost headroom ({head}x)")

    if rigor.get("available"):
        psr = rigor.get("psr_vs_zero")
        if psr is not None and psr < 0.95:
            fails.append(f"PSR {psr} < 0.95 — not distinguishable from no edge")
        trl = rigor.get("min_track_record_length")
        n = rigor.get("n_filled")
        if trl is not None and n is not None and n < trl:
            warns.append(f"only {n} trades vs MinTRL {trl} — too early to judge")
        dsr = (rigor.get("deflated_sharpe") or {}).get("dsr")
        if dsr is not None and dsr < 0.95:
            fails.append(f"DSR {dsr} < 0.95 — weak once trials are counted")
        elif (rigor.get("deflated_sharpe") or {}).get("skipped"):
            warns.append("DSR not computed — PSR is an upper bound only")
        boot = ((rigor.get("bootstrap") or {}).get("avg_r") or {})
        if boot.get("p05") is not None and boot["p05"] < 0:
            warns.append(f"bootstrap 5th pct avg-R is {boot['p05']:.3f} (negative)")
    else:
        fails.append(f"rigor unavailable: {rigor.get('reason')}")

    lines = ["=" * 68]
    if fails:
        lines.append("VERDICT: DO NOT PROMOTE THIS CONFIGURATION")
        lines += [f"  FAIL  {f}" for f in fails]
    else:
        lines.append("VERDICT: survives the checks")
    lines += [f"  warn  {w}" for w in warns]
    if not fails and not warns:
        lines.append("  no warnings")
    lines.append("=" * 68)
    return "\n".join(lines)


if __name__ == "__main__":
    main()
