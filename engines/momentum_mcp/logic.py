"""momentum-mcp core logic (design doc §4.4, PRD §5).

RSI across monthly/weekly/daily (plus 1h/30m when intraday bars exist), and
divergence detection anchored to price fractal pivots — output always cites
the pivot pairs used, so a thesis can quote them.
"""

from __future__ import annotations

import pandas as pd

from ..shared.indicators import rsi, resample_ohlcv
from ..shared.fractals import find_fractals
from ..shared.providers import BarRequest, DataProvider


def _zone(value: float) -> str:
    if value >= 70:
        return "overbought"
    if value <= 30:
        return "oversold"
    return "neutral"


def rsi_snapshot(bars: pd.DataFrame, timeframe: str, period: int = 14) -> dict | None:
    if len(bars) < period + 4:
        return None
    series = rsi(bars["close"], period).dropna()
    if len(series) < 4:
        return None
    now, then = float(series.iloc[-1]), float(series.iloc[-4])
    return {
        "timeframe": timeframe,
        "rsi": round(now, 1),
        "zone": _zone(now),
        "direction": "rising" if now > then + 0.5 else "falling" if now < then - 0.5 else "flat",
        "as_of": str(series.index[-1]),
    }


def find_divergences(bars: pd.DataFrame, timeframe: str = "1d",
                     period: int = 14, wing: int = 2) -> list[dict]:
    """Pair the last two price fractal pivots with RSI at the same bars.

    Price HH + RSI LH  -> bearish divergence
    Price LL + RSI HL  -> bullish divergence
    """
    series = rsi(bars["close"], period)
    fr = find_fractals(bars, wing=wing)
    out: list[dict] = []

    def last_two(kind: str):
        ks = [f for f in fr if f.kind == kind]
        return ks[-2:] if len(ks) >= 2 else None

    highs = last_two("high")
    if highs:
        a, b = highs
        ra, rb = float(series.iloc[a.bar_index]), float(series.iloc[b.bar_index])
        if b.price > a.price and rb < ra - 1.0:
            out.append({
                "type": "bearish_divergence", "timeframe": timeframe,
                "pivots": [
                    {"time": str(a.timestamp), "price": round(a.price, 2), "rsi": round(ra, 1)},
                    {"time": str(b.timestamp), "price": round(b.price, 2), "rsi": round(rb, 1)},
                ],
            })
    lows = last_two("low")
    if lows:
        a, b = lows
        ra, rb = float(series.iloc[a.bar_index]), float(series.iloc[b.bar_index])
        if b.price < a.price and rb > ra + 1.0:
            out.append({
                "type": "bullish_divergence", "timeframe": timeframe,
                "pivots": [
                    {"time": str(a.timestamp), "price": round(a.price, 2), "rsi": round(ra, 1)},
                    {"time": str(b.timestamp), "price": round(b.price, 2), "rsi": round(rb, 1)},
                ],
            })
    return out


class MomentumEngine:
    def __init__(self, provider: DataProvider, lookback_days: int = 500):
        self.provider = provider
        self.lookback = lookback_days

    def get_rsi_stack(self, symbol: str) -> dict:
        daily = self.provider.get_bars(BarRequest(symbol, "1d", self.lookback))
        stack = []
        for tf, bars in (
            ("monthly", resample_ohlcv(daily, "ME")),
            ("weekly", resample_ohlcv(daily, "W-FRI")),
            ("daily", daily),
        ):
            snap = rsi_snapshot(bars, tf)
            if snap:
                stack.append(snap)
        try:
            m30 = self.provider.get_bars(BarRequest(symbol, "30m", 59))
            for tf, bars in (("1h", resample_ohlcv(m30, "1h")), ("30m", m30)):
                snap = rsi_snapshot(bars, tf)
                if snap:
                    stack.append(snap)
        except Exception:
            pass  # intraday feed optional in Phase 2
        return {"symbol": symbol, "stack": stack}

    def get_divergences(self, symbol: str) -> dict:
        daily = self.provider.get_bars(BarRequest(symbol, "1d", self.lookback))
        return {"symbol": symbol,
                "divergences": find_divergences(daily.tail(120), "1d"),
                "computed_at": str(daily.index[-1])}
