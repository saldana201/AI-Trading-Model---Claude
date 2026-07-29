"""Phase 20b — gate funnel diagnostic.

The dataset builder revealed the real bottleneck: over 1000 bars the composer
produced only ~13 setups because the no-trade gate fired 69 times. This script
answers the necessary follow-up — *which* gate, and how often — so the fix
targets the actual constriction instead of guessing.

It replays the composer across history exactly as the dataset builder does, but
instead of keeping setups it tallies, at every compose point:

  - the regime label the regime engine assigned (risk_on / chop / ...),
  - whether the chop gate short-circuited the whole compose,
  - how many candidates survived each subsequent stage (rotation, screen, gate),

so the output is a stage-by-stage funnel: where, exactly, candidates die.

Run:
    CONFLUENCE_DATA=yfinance python -m scripts.gate_funnel --span 1000
"""

from __future__ import annotations

import argparse
from collections import Counter

from engines.shared.providers import ReplayProvider
from backtest.run import composer_factory_for
from scripts.snapshot import build_provider


def diagnose(span=1000, step=5, directions=("long", "short")) -> dict:
    provider, source = build_provider()
    factory = composer_factory_for(source, with_options=False)

    result = {"source": source, "span": span, "by_direction": {}}
    for direction in directions:
        import os
        prev = os.environ.get("CONFLUENCE_FORCE_DIRECTION")
        os.environ["CONFLUENCE_FORCE_DIRECTION"] = direction
        try:
            replay = ReplayProvider(provider, start_offset=span)
            composer = factory(replay)
            regimes = Counter()
            no_trade = 0
            compose_points = 0
            setups_total = 0
            passed_screen_total = 0
            candidate_total = 0
            zero_after_screen = 0
            suppression = Counter()

            n = replay.total_bars() if hasattr(replay, "total_bars") else span
            for _ in range(span):
                if not replay.advance():
                    break
                try:
                    plan = composer.compose()
                except Exception:
                    continue
                compose_points += 1
                reg = (plan.get("regime") or {}).get("regime", "?")
                regimes[reg] += 1
                if plan.get("no_trade"):
                    no_trade += 1
                    continue
                fn = plan.get("funnel") or {}
                candidate_total += fn.get("candidate_stocks", 0)
                passed = fn.get("passed_screen", 0)
                passed_screen_total += passed
                s = len(plan.get("setups") or [])
                setups_total += s
                if passed > 0 and s == 0:
                    zero_after_screen += 1
                # tally WHY screen-passers were suppressed — the exit door
                for sup in (plan.get("suppressed") or []):
                    reason = str(sup.get("reason", "?"))
                    key = _reason_bucket(reason)
                    suppression[key] += 1
        finally:
            if prev is None:
                os.environ.pop("CONFLUENCE_FORCE_DIRECTION", None)
            else:
                os.environ["CONFLUENCE_FORCE_DIRECTION"] = prev

        result["by_direction"][direction] = {
            "compose_points": compose_points,
            "regime_distribution": dict(regimes),
            "no_trade_shortcircuits": no_trade,
            "no_trade_pct": round(100 * no_trade / max(compose_points, 1), 1),
            "avg_candidates_when_traded": round(
                candidate_total / max(compose_points - no_trade, 1), 1),
            "avg_passed_screen_when_traded": round(
                passed_screen_total / max(compose_points - no_trade, 1), 1),
            "points_with_screen_hits_but_zero_setups": zero_after_screen,
            "suppression_reasons": dict(suppression.most_common()),
            "total_setups": setups_total,
        }
    return result


def _reason_bucket(reason: str) -> str:
    """Collapse the free-text suppression reason into the gate that caused it."""
    r = reason.lower()
    if "r:r" in r or "risk_reward" in r or "floor" in r and "confidence" not in r:
        return "R:R below floor"
    if "confidence" in r and "floor" in r:
        return "confidence below floor"
    if "level structure" in r:
        return "no usable level structure"
    if "evidence validation" in r:
        return "failed evidence validation"
    if "screen classified" in r:
        return "pinned filtered by screen"
    return "other"


def render(d: dict) -> str:
    lines = [f"gate funnel — source={d['source']} span={d['span']}", ""]
    for direction, r in d["by_direction"].items():
        lines.append(f"[{direction}]  {r['compose_points']} compose points")
        lines.append(f"  regime mix: {r['regime_distribution']}")
        lines.append(f"  no-trade short-circuits: {r['no_trade_shortcircuits']} "
                     f"({r['no_trade_pct']}% of compose points)")
        lines.append(f"  when it DID trade: avg {r['avg_candidates_when_traded']} "
                     f"candidates, {r['avg_passed_screen_when_traded']} passed screen")
        lines.append(f"  screen-hit-but-no-setup points: "
                     f"{r['points_with_screen_hits_but_zero_setups']}")
        if r.get("suppression_reasons"):
            lines.append("  WHY screen-passers were rejected:")
            for reason, cnt in r["suppression_reasons"].items():
                lines.append(f"      {cnt:>5}  {reason}")
        lines.append(f"  total setups produced: {r['total_setups']}")
        lines.append("")
    # verdict — look at the dominant suppression reason, not just no-trade %
    agg = Counter()
    for r in d["by_direction"].values():
        for reason, cnt in (r.get("suppression_reasons") or {}).items():
            agg[reason] += cnt
    worst_gate = max(d["by_direction"].values(), key=lambda r: r["no_trade_pct"])
    top_reason = agg.most_common(1)[0] if agg else None

    lines.append("DIAGNOSIS:")
    if worst_gate["no_trade_pct"] > 30:
        lines.append(f"  • chop/regime gate removes {worst_gate['no_trade_pct']}% "
                     f"of compose points before any stock is examined.")
    if top_reason:
        reason, cnt = top_reason
        lines.append(f"  • of candidates that pass the screen, the #1 killer is "
                     f"'{reason}' ({cnt} rejections).")
        if reason == "confidence below floor":
            lines.append("    -> This is the SYNTHETIC-TUNED SCORE. The score "
                         "floor plus mis-signed weights reject real setups. "
                         "Fix: lower min_score AND re-fit weights (Phase 20).")
        elif reason == "R:R below floor":
            lines.append("    -> The R:R floor is too strict for real level "
                         "geometry. Fix: lower gates.min_rr_t1/t2, or the levels "
                         "engine is placing targets too close.")
        elif reason == "no usable level structure":
            lines.append("    -> The levels engine can't build entry/stop/target "
                         "geometry on real bars for most names. Fix: inspect "
                         "_construct on real data.")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--span", type=int, default=1000)
    ap.add_argument("--step", type=int, default=5)
    ap.add_argument("--long-only", action="store_true")
    args = ap.parse_args()
    directions = ("long",) if args.long_only else ("long", "short")
    print(render(diagnose(args.span, args.step, directions)))


if __name__ == "__main__":
    main()
