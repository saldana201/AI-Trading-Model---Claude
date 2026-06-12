"""regime-mcp core logic (design doc §4.7, PRD §1).

A rules-first composite over the other engines. Each component scores
-2..+2 with a fixed weight; the weighted sum scales to a -10..+10 risk-on
score, and every component's contribution is reported — the regime is
reproducible bar by bar, never an LLM judgment.

Phase 2 scope: daily-resolution regime (risk_on / risk_off / chop) plus
volatility modifiers. Intraday trend-day / mean-reversion classification
and sector breadth arrive with rotation-mcp in Phase 3.
"""

from __future__ import annotations

from ..shared.indicators import rsi
from ..shared.levels import ma_status, weekly_pivot_levels
from ..shared.providers import BarRequest, DataProvider
from ..vix_mcp.logic import compute_vix_levels, classify_alignment, VIX_SYMBOL
from ..volume_mcp.logic import classify_phase

ALIGNMENT_SCORE = {
    "confirming_bullish": 2.0, "diverging_supportive": 1.0, "neutral_chop": 0.0,
    "diverging_warning": -1.0, "confirming_bearish": -2.0,
}
PHASE_SCORE = {
    "mark_up": 2.0, "accumulation": 1.0, "failed_breakdown": 1.0,
    "consolidation": 0.0, "failed_breakout": -1.0, "distribution": -1.0,
    "exhaustion": -1.5, "mark_down": -2.0,
}
WEIGHTS = {
    "vix_alignment": 2.5,
    "vix_vs_pivot": 1.5,
    "index_structure": 2.0,
    "volume_phase": 1.5,
    "momentum": 1.5,
    "ma_breadth": 1.0,
}
MAX_RAW = sum(2.0 * w for w in WEIGHTS.values())  # all components peg at ±2


def _index_structure_score(daily, weekly_levels) -> tuple[float, dict]:
    spot = float(daily["close"].iloc[-1])
    pivot = weekly_levels["weekly_pivot"]
    mas = {m["ma"]: m for m in ma_status(daily)}
    score = 0.0
    score += 1.0 if spot > pivot else -1.0
    if 21 in mas:
        score += 1.0 if mas[21]["state"] == "above" else -1.0
    return max(-2.0, min(2.0, score)), {
        "spot": round(spot, 2), "weekly_pivot": pivot,
        "above_weekly_pivot": spot > pivot,
        "ma21_state": mas.get(21, {}).get("state"),
    }


def _momentum_score(daily) -> tuple[float, dict]:
    series = rsi(daily["close"]).dropna()
    val = float(series.iloc[-1])
    if val >= 60:
        s = 1.0 + (1.0 if val >= 70 else 0.0)
    elif val <= 40:
        s = -1.0 - (1.0 if val <= 30 else 0.0)
    else:
        s = 0.0
    return s, {"daily_rsi": round(val, 1)}


def _sector_breadth_score(rotation_engine) -> tuple[float, dict]:
    """Real breadth from the 31-ETF rotation universe: fraction above the
    21-day MA, tilted by the leading-vs-lagging count."""
    board = rotation_engine.get_leaderboard()
    rows = [e for e in board["etfs"] if e.get("ma21") in ("above", "below")]
    if not rows:
        return 0.0, {"source": "sector_universe", "note": "no usable rows"}
    frac = sum(e["ma21"] == "above" for e in rows) / len(rows)
    statuses = [e["status"] for e in rows]
    tilt = (statuses.count("leading") - statuses.count("lagging")
            - statuses.count("deteriorating") * 0.5) / max(len(rows), 1)
    score = (frac - 0.5) * 3.2 + tilt * 1.6
    return round(max(-2.0, min(2.0, score)), 2), {
        "source": "sector_universe", "etfs": len(rows),
        "fraction_above_ma21": round(frac, 2),
        "leading": statuses.count("leading"),
        "improving": statuses.count("improving"),
        "deteriorating": statuses.count("deteriorating"),
        "lagging": statuses.count("lagging"),
    }


def _breadth_score(symbol_dailies: dict) -> tuple[float, dict]:
    """MA-stack proxy fallback when no rotation engine is wired in
    (e.g. cheap backtest passes)."""
    checks, above = 0, 0
    detail = {}
    for sym, daily in symbol_dailies.items():
        states = {m["ma"]: m["state"] for m in ma_status(daily)}
        for ma in (21, 50, 200):
            if ma in states:
                checks += 1
                above += states[ma] == "above"
        detail[sym] = states
    frac = above / checks if checks else 0.5
    return round((frac - 0.5) * 4, 2), {"fraction_above_mas": round(frac, 2), "detail": detail}


def compute_regime(provider: DataProvider, index_symbols=("QQQ", "SPY"),
                   rotation_engine=None) -> dict:
    vix = provider.get_bars(BarRequest(VIX_SYMBOL, "1d", 180))
    dailies = {s: provider.get_bars(BarRequest(s, "1d", 400)) for s in index_symbols}
    primary = dailies[index_symbols[0]]

    vix_levels = compute_vix_levels(vix)
    alignment = classify_alignment(primary, vix, vix_levels)

    components = []

    def add(name, score, evidence):
        score = max(-2.0, min(2.0, score))
        components.append({
            "name": name, "score": round(score, 2), "weight": WEIGHTS[name],
            "contribution": round(score * WEIGHTS[name], 2), "evidence": evidence,
        })

    add("vix_alignment", ALIGNMENT_SCORE[alignment["state"]],
        {"state": alignment["state"], **alignment["evidence"]})

    below = vix_levels.get("spot_vs_pivot") == "below"
    add("vix_vs_pivot", 1.5 if below else -1.5,
        {"spot": vix_levels["spot"], "pivot": vix_levels["pivot"],
         "spot_vs_pivot": vix_levels["spot_vs_pivot"]})

    s, ev = _index_structure_score(primary, weekly_pivot_levels(primary))
    add("index_structure", s, {"symbol": index_symbols[0], **ev})

    phase = classify_phase(primary)
    add("volume_phase", PHASE_SCORE.get(phase["phase"], 0.0),
        {"phase": phase["phase"], **phase["evidence"]})

    s, ev = _momentum_score(primary)
    add("momentum", s, ev)

    if rotation_engine is not None:
        s, ev = _sector_breadth_score(rotation_engine)
    else:
        s, ev = _breadth_score(dailies)
    add("ma_breadth", s, ev)

    raw = sum(c["contribution"] for c in components)
    risk_score = round(raw / MAX_RAW * 10, 1)

    regime = "risk_on" if risk_score >= 3 else "risk_off" if risk_score <= -3 else "chop"

    vix_5d_chg = float(vix["close"].iloc[-1] / vix["close"].iloc[-6] - 1) * 100
    modifiers = []
    if vix_5d_chg > 15:
        modifiers.append("vol_expansion")
    elif vix_5d_chg < -12:
        modifiers.append("vol_compression")

    return {
        "regime": regime,
        "risk_score": risk_score,
        "modifiers": modifiers,
        "vix_5d_change_pct": round(vix_5d_chg, 1),
        "components": components,
        "primary_index": index_symbols[0],
        "computed_at": str(primary.index[-1]),
        "not_yet_classified": (
            {"trend_day_vs_mean_reversion":
                 "requires intraday bars (streaming ingest)"}
            if rotation_engine is not None else
            {"trend_day_vs_mean_reversion":
                 "requires intraday bars (streaming ingest)",
             "sector_breadth": "rotation engine not wired into this instance"}),
    }


class RegimeEngine:
    def __init__(self, provider: DataProvider, rotation_engine=None):
        self.provider = provider
        self.rotation = rotation_engine

    def get_regime(self) -> dict:
        return compute_regime(self.provider, rotation_engine=self.rotation)
