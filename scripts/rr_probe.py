"""Phase 20c — R:R geometry probe.

The gate funnel localized the bottleneck to 'R:R below floor' (2,155 rejections
vs 259 for confidence). That means real setups are being built, but their
entry/stop/target geometry doesn't clear min_rr_t2=2.0. This probe reports the
actual distribution of constructed R:R so the fix is evidence-based:

  - if most setups cluster just under 2.0 -> the floor is slightly too strict;
  - if R:R is all over and often < 1 -> the geometry constants are wrong (stop
    too wide relative to targets), i.e. the levels/setup ATR multiples were
    tuned on synthetic trends and don't fit real structure;
  - it also reports how many setups WOULD pass at candidate lower floors, so you
    can see the setups-recovered tradeoff before changing anything.

Run:
    CONFLUENCE_DATA=yfinance python -m scripts.rr_probe --span 1000
"""

from __future__ import annotations

import argparse
import os
from statistics import median, quantiles

from engines.shared.providers import ReplayProvider
from backtest.run import composer_factory_for
from scripts.snapshot import build_provider


def probe(span=1000, directions=("long", "short")) -> dict:
    provider, source = build_provider()
    factory = composer_factory_for(source, with_options=False)
    out = {"source": source, "span": span, "by_direction": {}}

    for direction in directions:
        prev = os.environ.get("CONFLUENCE_FORCE_DIRECTION")
        os.environ["CONFLUENCE_FORCE_DIRECTION"] = direction
        try:
            replay = ReplayProvider(provider, start_offset=span)
            composer = factory(replay)
            rr_t1, rr_t2, stop_atrs = [], [], []
            for _ in range(span):
                if not replay.advance():
                    break
                try:
                    plan = composer.compose()
                except Exception:
                    continue
                # constructed-but-suppressed setups carry their R:R in the reason;
                # accepted setups carry it directly. Pull from both.
                for s in (plan.get("setups") or []):
                    if s.get("risk_reward_t1") is not None:
                        rr_t1.append(s["risk_reward_t1"])
                        rr_t2.append(s["risk_reward_t2"])
                for sup in (plan.get("suppressed") or []):
                    r = _parse_rr(sup.get("reason", ""))
                    if r:
                        rr_t1.append(r[0])
                        rr_t2.append(r[1])
        finally:
            if prev is None:
                os.environ.pop("CONFLUENCE_FORCE_DIRECTION", None)
            else:
                os.environ["CONFLUENCE_FORCE_DIRECTION"] = prev

        out["by_direction"][direction] = _summarize(rr_t1, rr_t2)
    return out


def _parse_rr(reason: str):
    """Extract (t1, t2) from 'R:R T1 1.3 / T2 1.7 below 1.0/2.0 floors'."""
    import re
    m = re.search(r"R:R T1 ([\d.]+) / T2 ([\d.]+)", reason)
    if m:
        return float(m.group(1)), float(m.group(2))
    return None


def _summarize(rr_t1, rr_t2) -> dict:
    if not rr_t2:
        return {"available": False, "reason": "no constructed setups"}
    def stats(xs):
        xs = sorted(xs)
        q = quantiles(xs, n=4) if len(xs) >= 4 else [xs[0], median(xs), xs[-1]]
        return {"n": len(xs), "min": round(min(xs), 2), "p25": round(q[0], 2),
                "median": round(median(xs), 2), "p75": round(q[-1], 2),
                "max": round(max(xs), 2)}
    # setups recovered at candidate lower T2 floors (T1 floor held at 1.0)
    recovery = {}
    for floor in (2.0, 1.75, 1.5, 1.3, 1.2, 1.0):
        passed = sum(1 for a, b in zip(rr_t1, rr_t2) if a >= 1.0 and b >= floor)
        recovery[floor] = passed
    return {"available": True, "t1": stats(rr_t1), "t2": stats(rr_t2),
            "pass_at_t2_floor": recovery}


def render(d: dict) -> str:
    lines = [f"R:R geometry — source={d['source']} span={d['span']}", ""]
    for direction, r in d["by_direction"].items():
        lines.append(f"[{direction}]")
        if not r.get("available"):
            lines.append(f"  {r.get('reason')}"); lines.append(""); continue
        t1, t2 = r["t1"], r["t2"]
        lines.append(f"  R:R T1  n={t1['n']:>4}  min={t1['min']} p25={t1['p25']} "
                     f"median={t1['median']} p75={t1['p75']} max={t1['max']}")
        lines.append(f"  R:R T2  n={t2['n']:>4}  min={t2['min']} p25={t2['p25']} "
                     f"median={t2['median']} p75={t2['p75']} max={t2['max']}")
        lines.append("  setups passing at each T2 floor (T1>=1.0):")
        base = r["pass_at_t2_floor"][2.0]
        for floor, cnt in r["pass_at_t2_floor"].items():
            mult = f"  ({cnt/base:.1f}x)" if base else ""
            lines.append(f"      T2>={floor}: {cnt}{mult}")
        lines.append("")

    # verdict
    any_dir = next((r for r in d["by_direction"].values()
                    if r.get("available")), None)
    if any_dir:
        med = any_dir["t2"]["median"]
        if med >= 2.0:
            lines.append("DIAGNOSIS: median R:R T2 clears 2.0 — the floor isn't "
                         "the main problem; the losses are in the tail. Look at "
                         "why specific names fall short, or lower the floor "
                         "modestly to recover the near-misses.")
        elif med >= 1.5:
            lines.append(f"DIAGNOSIS: median R:R T2 is {med} — just under the 2.0 "
                         "floor. The geometry is close but the floor rejects the "
                         "middle of the distribution. Lowering min_rr_t2 to ~1.5 "
                         "recovers most setups; validate that the edge survives "
                         "the looser floor (run validate_real after).")
        else:
            lines.append(f"DIAGNOSIS: median R:R T2 is only {med} — the geometry "
                         "itself is the problem, not just the floor. Stops are "
                         "too wide relative to targets. The setup ATR multiples "
                         "(stop_atr/max_stop_atr vs t2_atr) were tuned on "
                         "synthetic trends. Widen t2_atr or tighten max_stop_atr, "
                         "then re-probe.")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--span", type=int, default=1000)
    ap.add_argument("--long-only", action="store_true")
    args = ap.parse_args()
    directions = ("long",) if args.long_only else ("long", "short")
    print(render(probe(args.span, directions)))


if __name__ == "__main__":
    main()
