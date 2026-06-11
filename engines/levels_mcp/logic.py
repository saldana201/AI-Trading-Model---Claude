"""levels-mcp core logic (design doc §4.2).

Produces the full level set for an index or stock: day levels, weekly pivots,
ATR outliers, fractal support/resistance clusters, MA reclaim/loss status,
RVOL — every level a typed record with method + timestamp. Also exposes the
check_level_break primitive for the future alert engine.
"""

from __future__ import annotations

import pandas as pd

from ..shared.fractals import find_fractals, cluster_levels
from ..shared.levels import (
    weekly_pivot_levels, outlier_levels, day_levels, ma_status, rvol,
    check_level_break,
)
from ..shared.providers import BarRequest, DataProvider


def _typed_levels(symbol: str, named: dict[str, float | None], method: str,
                  computed_at: str) -> list[dict]:
    out = []
    for kind, price in named.items():
        if price is None:
            continue
        out.append({
            "symbol": symbol, "level": price, "kind": kind,
            "method": method, "timeframe": "1d", "computed_at": computed_at,
        })
    return out


def compute_symbol_levels(symbol: str, daily: pd.DataFrame,
                          fractal_window: int = 90) -> dict:
    computed_at = str(daily.index[-1])
    spot = round(float(daily["close"].iloc[-1]), 2)

    dl = day_levels(daily)
    wl = weekly_pivot_levels(daily)
    ol = outlier_levels(daily)

    bars = daily.tail(fractal_window)
    clusters = cluster_levels(find_fractals(bars, wing=2), n_bars=len(bars))
    sr = [c.to_dict() | {"symbol": symbol, "method": "fractal_cluster",
                         "computed_at": computed_at} for c in clusters]

    # Trigger candidates: strongest cluster above / below spot.
    above = [c for c in clusters if c.price > spot]
    below = [c for c in clusters if c.price < spot]
    bullish_trigger = round(max(above, key=lambda c: c.strength).price, 2) if above else None
    bearish_trigger = round(max(below, key=lambda c: c.strength).price, 2) if below else None

    levels = (
        _typed_levels(symbol, dl | {"gap": None}, "session", computed_at)
        + _typed_levels(symbol, wl, "weekly_pivot", computed_at)
        + _typed_levels(symbol, {k: ol[k] for k in ("outlier_upside", "outlier_downside")},
                        "atr_extension", computed_at)
        + _typed_levels(symbol, {"bullish_trigger": bullish_trigger,
                                 "bearish_trigger": bearish_trigger},
                        "fractal_cluster", computed_at)
    )

    return {
        "symbol": symbol,
        "spot": spot,
        "computed_at": computed_at,
        "rvol_20d": rvol(daily, 20),
        "rvol_50d": rvol(daily, 50),
        "session": dl,
        "weekly": wl,
        "outliers": ol,
        "bullish_trigger": bullish_trigger,
        "bearish_trigger": bearish_trigger,
        "chop_zone": ([bearish_trigger, bullish_trigger]
                      if bullish_trigger and bearish_trigger else None),
        "moving_averages": ma_status(daily),
        "fractal_clusters": sr,
        "levels": levels,
    }


class LevelsEngine:
    def __init__(self, provider: DataProvider, lookback_days: int = 400):
        self.provider = provider
        self.lookback = lookback_days

    def _daily(self, symbol: str) -> pd.DataFrame:
        return self.provider.get_bars(BarRequest(symbol, "1d", self.lookback))

    def get_levels(self, symbol: str) -> dict:
        return compute_symbol_levels(symbol, self._daily(symbol))

    def check_break(self, symbol: str, level: float, direction: str) -> dict:
        result = check_level_break(self._daily(symbol), level, direction)
        result["symbol"] = symbol
        return result
