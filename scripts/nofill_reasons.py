"""Phase 22b — why setups don't fill, from GROUND TRUTH.

Three times now a hand-written probe has disagreed with the backtest, because
the probe reimplemented the fill rule and the reimplementation drifted from the
real state machine. This script does not reimplement anything. It runs the
ACTUAL Backtest, then reads the `exit_reason` the engine already records on
every outcome, and tallies it.

Whatever this says is what the system actually does — there is no second
implementation to be wrong.

Key thing it surfaces: in alerts/lifecycle.step(), the FIRST pre-entry check is
`against(stop)` — if price closes through the stop side before the entry trigger
fires, the trade goes to INVALIDATED, which realized_r_from_events maps to
NO_FILL. So a "no fill" can mean two very different things:

  - "never triggered"                     -> price never reached the entry
  - "price moved through the stop side"   -> price went the WRONG WAY first

Those need opposite fixes. The first says move the entry closer; the second says
the stop is too close to price relative to the trigger, so normal noise takes
out the stop before the setup ever arms.

Run:
    CONFLUENCE_DATA=yfinance python -m scripts.nofill_reasons --span 1000 --chop-soft
"""

from __future__ import annotations

import argparse
import os
from collections import Counter

from backtest.harness import Backtest
from backtest.costs import CostModel
from backtest.run import composer_factory_for
from scripts.snapshot import build_provider


def bucket(reason: str) -> str:
    r = (reason or "").lower()
    if "never triggered" in r:
        return "never reached the entry trigger"
    if "stop side before entry" in r:
        return "price hit the STOP side before entry"
    if "invalidat" in r:
        return "invalidated pre-entry (other)"
    return f"other: {reason[:60]}"


def analyze(span=1000, step_bars=5, horizon=15, chop_soft=False,
            directions=("long", "short")) -> dict:
    if chop_soft:
        from config import update_config, reset_cache
        reset_cache()
        update_config({"gates": {"chop_mode": "soft"}}, persist=False)

    provider, source = build_provider()
    factory = composer_factory_for(source, False)
    out = {"source": source, "span": span, "horizon": horizon,
           "chop_soft": chop_soft, "by_direction": {}}

    for d in directions:
        prev = os.environ.get("CONFLUENCE_FORCE_DIRECTION")
        os.environ["CONFLUENCE_FORCE_DIRECTION"] = d
        try:
            bt = Backtest(provider, factory, span_bars=span,
                          step_bars=step_bars, horizon_bars=horizon,
                          cost_model=CostModel())
            rep = bt.run()
        finally:
            if prev is None:
                os.environ.pop("CONFLUENCE_FORCE_DIRECTION", None)
            else:
                os.environ["CONFLUENCE_FORCE_DIRECTION"] = prev

        outs = rep["outcomes"]
        nofill = [o for o in outs if o.get("final_state") == "NO_FILL"]
        reasons = Counter(bucket(o.get("exit_reason", "")) for o in nofill)
        filled = [o for o in outs if o.get("realized_r") is not None]
        out["by_direction"][d] = {
            "setups": len(outs),
            "filled": len(filled),
            "fill_rate": round(len(filled) / len(outs), 3) if outs else None,
            "no_fill": len(nofill),
            "no_fill_reasons": dict(reasons.most_common()),
            "final_states": dict(Counter(o.get("final_state") for o in outs)),
        }
    return out


def render(d: dict) -> str:
    lines = [f"NO_FILL ground truth — source={d['source']} span={d['span']} "
             f"horizon={d['horizon']} chop_soft={d['chop_soft']}", ""]
    agg = Counter()
    for direction, r in d["by_direction"].items():
        lines.append(f"[{direction}] {r['setups']} setups, {r['filled']} filled "
                     f"(rate {r['fill_rate']}), {r['no_fill']} NO_FILL")
        for reason, cnt in r["no_fill_reasons"].items():
            pct = cnt / r["no_fill"] * 100 if r["no_fill"] else 0
            lines.append(f"    {cnt:>4} ({pct:>4.0f}%)  {reason}")
            agg[reason] += cnt
        lines.append(f"    states: {r['final_states']}")
        lines.append("")

    if agg:
        top, cnt = agg.most_common(1)[0]
        total = sum(agg.values())
        lines.append(f"DIAGNOSIS: the dominant NO_FILL cause is "
                     f"'{top}' ({cnt}/{total} = {cnt/total:.0%}).")
        if "STOP side" in top:
            lines.append(
                "  -> Price goes the WRONG WAY before the setup arms. The stop "
                "sits close enough to spot that ordinary noise takes it out "
                "before the entry trigger fires. This is a GEOMETRY problem, not "
                "a horizon or trigger-distance problem.\n"
                "     Fixes to test (each changes the strategy, so measure edge "
                "after):\n"
                "       (a) don't invalidate pre-entry on a stop touch — only "
                "invalidate after entry;\n"
                "       (b) place the pre-entry invalidation level further away "
                "than the post-entry stop;\n"
                "       (c) enter on a pullback TO the level instead of waiting "
                "for a break above it.")
        elif "never reached" in top:
            lines.append(
                "  -> Price simply never gets to the entry. Move the trigger "
                "closer (entry_buffer_atr) or lengthen the horizon.")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--span", type=int, default=1000)
    ap.add_argument("--step", type=int, default=5)
    ap.add_argument("--horizon", type=int, default=15)
    ap.add_argument("--chop-soft", action="store_true")
    ap.add_argument("--long-only", action="store_true")
    args = ap.parse_args()
    directions = ("long",) if args.long_only else ("long", "short")
    print(render(analyze(args.span, args.step, args.horizon,
                         args.chop_soft, directions)))


if __name__ == "__main__":
    main()
