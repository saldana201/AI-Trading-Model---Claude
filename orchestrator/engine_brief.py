"""Phase 31 — the engine brief: facts first, no synthesis.

What changed and why
--------------------
Phases 15-28 measured the composed-setup product on 506 real trades and it lost
to the index on every axis (+37.4% vs QQQ +111.7%, -33.0% vs -22.8% drawdown,
Sharpe 0.55 vs 1.00). Component edges collapse to ~0 at adequate sample size.

What did NOT fail is the engine layer. Fractal support/resistance clusters, VIX
pivots and term structure, gamma walls and the zero-gamma flip, GARCH volatility
forecasts, RVOL phase classification, sector rotation state — these are
deterministic, testable, reproducible facts. They are exactly what a
discretionary trader wants on the screen. The failure was the leap from those
facts to "take this trade, confidence 8.2."

So this module inverts the product. Instead of engines feeding a setup composer
whose output you are asked to trust, it returns everything the engines know
about one symbol, each item tagged with the method that produced it and the bar
it was computed from — and stops there. No score. No direction. No suggestion.

That restraint is the point, so it is enforced rather than merely intended:
`assert_no_recommendation()` scans the payload for advisory language and raises
if any appears. A brief that starts recommending is a bug.
"""

from __future__ import annotations

from typing import Any

# Words that would signal the brief has drifted back into advice.
_ADVISORY = ("buy", "sell", "should ", "recommend", "we suggest",
             "take this trade", "enter now", "target price")


def _safe(fn, *a, **kw) -> Any:
    """Engines degrade to a stated error rather than breaking the brief.
    A missing engine reads as 'unavailable', never as silence."""
    try:
        return fn(*a, **kw)
    except Exception as exc:
        return {"available": False, "error": f"{type(exc).__name__}: {exc}"}


def build_brief(symbol: str, engines: dict) -> dict:
    """Everything the engines know about `symbol`, facts only.

    `engines` is a dict of already-constructed engines, any of which may be
    absent: vix, levels, volume, momentum, regime, rotation, volatility,
    options, fundamentals, screener.
    """
    sym = symbol.upper()
    out: dict[str, Any] = {
        "symbol": sym,
        "kind": "engine_brief",
        "contains_recommendation": False,
        "note": ("Deterministic engine output only. No score, no direction, no "
                 "suggested trade. Every value carries the method that produced "
                 "it. Interpretation is yours."),
        "engines": {},
    }
    e = out["engines"]

    if "levels" in engines:
        e["levels"] = _safe(engines["levels"].get_levels, sym)
    if "vix" in engines:
        e["vix"] = {"levels": _safe(engines["vix"].get_levels),
                    "alignment": _safe(engines["vix"].get_alignment, sym)}
    if "volume" in engines:
        e["volume"] = {"rvol": _safe(engines["volume"].get_rvol, sym),
                       "phase": _safe(engines["volume"].get_phase, sym)}
    if "momentum" in engines:
        e["momentum"] = {"rsi_stack": _safe(engines["momentum"].get_rsi_stack, sym),
                         "divergences": _safe(engines["momentum"].get_divergences, sym)}
    if "regime" in engines:
        e["regime"] = _safe(engines["regime"].get_regime)
    if "rotation" in engines:
        e["rotation"] = _safe(engines["rotation"].get_leaderboard)
    if "volatility" in engines:
        e["volatility"] = {
            "forecast": _safe(engines["volatility"].get_forecast, sym, 21),
            "realized": _safe(engines["volatility"].get_realized, sym),
            "cone": _safe(engines["volatility"].get_cone, sym),
        }
    if "options" in engines:
        o = engines["options"]
        e["options"] = {"dealer_zones": _safe(o.get_dealer_zones, sym),
                        "gex_profile": _safe(o.get_gex_profile, sym)}
    if "fundamentals" in engines:
        e["fundamentals"] = _safe(engines["fundamentals"].get_snapshot, sym)
    if "screener" in engines:
        scr = _safe(engines["screener"].screen, [sym])
        if isinstance(scr, dict):
            rows = scr.get("results") or scr.get("candidates") or []
            e["screen"] = next((r for r in rows if r.get("symbol") == sym), scr)
        else:
            e["screen"] = scr

    out["available_engines"] = sorted(e.keys())
    out["unavailable"] = sorted(
        k for k, v in e.items()
        if isinstance(v, dict) and v.get("available") is False)
    return out


def assert_no_recommendation(brief: dict) -> None:
    """Guard the contract. The brief exists to report facts; if advisory
    language appears it means a synthesis layer leaked back in.

    Scans string VALUES only — key names like `contains_recommendation` are
    metadata about the guard itself, not content, and scanning the serialized
    blob made them false-positive.
    """
    hits: list[tuple] = []
    disclaimer = brief.get("note", "")

    def walk(node, path="") -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, f"{path}.{k}")
        elif isinstance(node, (list, tuple)):
            for i, v in enumerate(node):
                walk(v, f"{path}[{i}]")
        elif isinstance(node, str):
            if node == disclaimer:      # our own "no suggested trade" line
                return
            low = node.lower()
            for w in _ADVISORY:
                if w in low:
                    hits.append((path, w, node[:80]))

    walk(brief)
    if hits:
        detail = "; ".join(f"{p}: {w!r}" for p, w, _ in hits[:5])
        raise AssertionError(
            f"engine brief contains advisory language ({detail}) — it must "
            "report facts only")


def render_brief(brief: dict) -> str:
    """Compact human-readable brief for chat and CLI."""
    lines = [f"{brief['symbol']} — engine brief (facts only, no recommendation)"]
    e = brief.get("engines", {})

    lv = e.get("levels") or {}
    if isinstance(lv, dict) and lv.get("levels"):
        top = lv["levels"][:6]
        lines.append("  levels: " + ", ".join(
            f"{x.get('level')}({x.get('kind','?')})" for x in top))

    vx = (e.get("vix") or {})
    if isinstance(vx.get("levels"), dict):
        vl = vx["levels"]
        al = vx.get("alignment") or {}
        lines.append(f"  vix: spot={vl.get('spot')} pivot={vl.get('pivot')} "
                     f"alignment={al.get('state','?')}")

    vo = (e.get("volume") or {})
    if isinstance(vo.get("rvol"), dict):
        lines.append(f"  volume: rvol={vo['rvol'].get('rvol')} "
                     f"phase={(vo.get('phase') or {}).get('phase','?')}")

    mo = (e.get("momentum") or {})
    stack = ((mo.get("rsi_stack") or {}).get("stack")) or []
    if stack:
        parts = [f"{r.get('timeframe')}:{r.get('rsi')}" for r in stack[:5]]
        ob = sum(1 for r in stack if r.get("zone") == "overbought")
        os_ = sum(1 for r in stack if r.get("zone") == "oversold")
        lines.append(f"  momentum: {' '.join(parts)} "
                     f"({ob} overbought, {os_} oversold)")
        div = (mo.get("divergences") or {})
        flags = [k for k in ("bearish", "bullish")
                 if (div.get(k) or div.get(f"{k}_divergence"))]
        if flags:
            lines.append(f"    divergences: {', '.join(flags)}")

    rg = e.get("regime")
    if isinstance(rg, dict):
        lines.append(f"  regime: {rg.get('regime')} risk_score={rg.get('risk_score')}")

    vl2 = (e.get("volatility") or {}).get("forecast")
    if isinstance(vl2, dict) and vl2.get("available"):
        f = vl2["forecast"]
        lines.append(f"  volatility: 21d forecast="
                     f"{f.get('horizon_annualized_vol')} "
                     f"next_day={f.get('next_day_annualized_vol')} "
                     f"half_life={f.get('half_life_days')}d")

    op = (e.get("options") or {}).get("dealer_zones")
    if isinstance(op, dict):
        lines.append(f"  options: flip={op.get('zero_gamma')} "
                     f"call_wall={op.get('call_wall')} put_wall={op.get('put_wall')}")

    fu = e.get("fundamentals")
    if isinstance(fu, dict) and fu.get("symbol"):
        lines.append(f"  fundamentals: earnings={fu.get('earnings_date')} "
                     f"sector={fu.get('sector')}")

    if brief.get("unavailable"):
        lines.append(f"  unavailable: {', '.join(brief['unavailable'])}")
    lines.append("  (interpretation is yours — this system's composed setups "
                 "underperformed buy-and-hold; see /api/benchmark-context)")
    return "\n".join(lines)
