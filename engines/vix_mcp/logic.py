"""vix-mcp core logic (design doc §4.1).

Pivot = the fractal level cluster nearest VIX spot.
Upside targets 1/2 = next clusters above spot; downside targets 1/2 = next below.
Alignment classifies VIX vs index price action into the five PRD states.
"""

from __future__ import annotations

import pandas as pd

from ..shared.fractals import (
    find_fractals, cluster_levels, nearest_cluster, clusters_above, clusters_below,
)
from ..shared.providers import BarRequest, DataProvider

VIX_SYMBOL = "^VIX"


def compute_vix_levels(vix_daily: pd.DataFrame, window_sessions: int = 60) -> dict:
    bars = vix_daily.tail(window_sessions)
    spot = float(bars["close"].iloc[-1])
    fr = find_fractals(bars, wing=2)
    # VIX trades in points, so use a wider tolerance than equities (~1.5%).
    clusters = cluster_levels(fr, n_bars=len(bars), tolerance_pct=0.015)

    pivot = nearest_cluster(clusters, spot)
    up = clusters_above(clusters, spot if pivot is None else max(spot, pivot.price), 2)
    down = clusters_below(clusters, spot if pivot is None else min(spot, pivot.price), 2)

    def px(c):
        return round(c.price, 2) if c else None

    return {
        "symbol": VIX_SYMBOL,
        "spot": round(spot, 2),
        "pivot": px(pivot),
        "spot_vs_pivot": (
            None if pivot is None else
            "below" if spot < pivot.price else "above" if spot > pivot.price else "at"
        ),
        "upside_target_1": px(up[0]) if len(up) > 0 else None,
        "upside_target_2": px(up[1]) if len(up) > 1 else None,
        "downside_target_1": px(down[0]) if len(down) > 0 else None,
        "downside_target_2": px(down[1]) if len(down) > 1 else None,
        "clusters": [c.to_dict() for c in clusters],
        "computed_at": str(bars.index[-1]),
        "window_sessions": len(bars),
    }


def classify_alignment(index_daily: pd.DataFrame, vix_daily: pd.DataFrame,
                       vix_levels: dict, lookback: int = 3) -> dict:
    """Map VIX/index co-movement to the PRD's five alignment states."""
    idx_now = float(index_daily["close"].iloc[-1])
    idx_then = float(index_daily["close"].iloc[-1 - lookback])
    vix_now = float(vix_daily["close"].iloc[-1])
    vix_then = float(vix_daily["close"].iloc[-1 - lookback])

    idx_up = idx_now > idx_then
    vix_up = vix_now > vix_then
    pivot = vix_levels.get("pivot")
    below_pivot = pivot is not None and vix_now < pivot

    if idx_up and vix_up:
        state = "diverging_warning"        # price up, vol bid: trap/chop risk
    elif idx_up and not vix_up and below_pivot:
        state = "confirming_bullish"
    elif not idx_up and vix_up and not below_pivot:
        state = "confirming_bearish"
    elif not idx_up and not vix_up:
        state = "diverging_supportive"     # price soft but vol bleeding out
    else:
        state = "neutral_chop"

    return {
        "state": state,
        "evidence": {
            "index_change_pct": round((idx_now / idx_then - 1) * 100, 2),
            "vix_change_pct": round((vix_now / vix_then - 1) * 100, 2),
            "vix_spot": round(vix_now, 2),
            "vix_pivot": pivot,
            "vix_below_pivot": below_pivot,
            "lookback_days": lookback,
        },
    }


class VixEngine:
    def __init__(self, provider: DataProvider, window_sessions: int = 60):
        self.provider = provider
        self.window = window_sessions

    def get_levels(self) -> dict:
        vix = self.provider.get_bars(BarRequest(VIX_SYMBOL, "1d", 180))
        return compute_vix_levels(vix, self.window)

    def get_alignment(self, symbol: str = "QQQ") -> dict:
        vix = self.provider.get_bars(BarRequest(VIX_SYMBOL, "1d", 180))
        idx = self.provider.get_bars(BarRequest(symbol, "1d", 180))
        levels = compute_vix_levels(vix, self.window)
        result = classify_alignment(idx, vix, levels)
        result["index_symbol"] = symbol
        result["vix_levels"] = {k: levels[k] for k in (
            "spot", "pivot", "spot_vs_pivot",
            "upside_target_1", "upside_target_2",
            "downside_target_1", "downside_target_2",
        )}
        return result
