"""volume-mcp core logic (design doc §4.3, PRD §4).

Classifies a symbol's price-volume state into the PRD's phases:
accumulation / mark_up / distribution / mark_down / consolidation /
exhaustion / failed_breakout / failed_breakdown — always with the evidence
that produced the call.
"""

from __future__ import annotations

import pandas as pd

from ..shared.indicators import slope_pct, range_position
from ..shared.fractals import atr
from ..shared.levels import rvol
from ..shared.providers import BarRequest, DataProvider

TREND_UP = 0.06     # %/bar regression slope thresholds
TREND_DOWN = -0.06


def updown_volume_ratio(daily: pd.DataFrame, window: int = 20) -> float:
    w = daily.tail(window)
    chg = w["close"].diff()
    up_vol = float(w["volume"][chg > 0].sum())
    down_vol = float(w["volume"][chg < 0].sum())
    return round(up_vol / down_vol, 2) if down_vol > 0 else float("inf")


def detect_failed_break(daily: pd.DataFrame, lookback: int = 5,
                        range_window: int = 20) -> str | None:
    """Failed breakout: a close above the prior range high within `lookback`
    bars, followed by a close back below it. Mirror for failed breakdown."""
    closes = daily["close"]
    for i in range(lookback, 0, -1):
        pos = len(daily) - i
        prior = daily.iloc[max(0, pos - range_window):pos]
        if len(prior) < range_window:
            continue
        # A failed break only exists relative to a genuine range: skip if the
        # prior window was trending (a pullback in trend is not a failed breakout).
        if abs(slope_pct(prior["close"], range_window)) > 0.08:
            continue
        range_high = float(prior["high"].max())
        range_low = float(prior["low"].min())
        c = float(closes.iloc[pos])
        after = closes.iloc[pos + 1:]
        if c > range_high and len(after) and float(after.iloc[-1]) < range_high:
            return "failed_breakout"
        if c < range_low and len(after) and float(after.iloc[-1]) > range_low:
            return "failed_breakdown"
    return None


def classify_phase(daily: pd.DataFrame, window: int = 40) -> dict:
    trend = slope_pct(daily["close"], window)
    short_trend = slope_pct(daily["close"], 5)
    udr = updown_volume_ratio(daily, 20)
    pos = range_position(daily["close"], 60)
    rv = rvol(daily, 20)
    vol_recent = float(daily["volume"].tail(5).mean())
    vol_prior = float(daily["volume"].tail(15).head(10).mean())
    vol_fade = vol_prior > 0 and vol_recent / vol_prior < 0.7
    contraction = atr(daily.tail(40), 7) / max(atr(daily, 28), 1e-9)

    failed = detect_failed_break(daily)
    if failed:
        phase = failed
    elif abs(trend) > 2.5 * abs(TREND_UP) and vol_fade and abs(short_trend) < 0.04:
        phase = "exhaustion"
    elif trend > TREND_UP and udr > 1.15:
        phase = "mark_up"
    elif trend < TREND_DOWN and udr < 0.87:
        phase = "mark_down"
    elif abs(trend) <= TREND_UP and pos <= 0.45 and udr > 1.1:
        phase = "accumulation"
    elif abs(trend) <= TREND_UP and pos >= 0.55 and udr < 0.91:
        phase = "distribution"
    elif trend > TREND_UP:
        phase = "mark_up"
    elif trend < TREND_DOWN:
        phase = "mark_down"
    else:
        phase = "consolidation"

    return {
        "phase": phase,
        "evidence": {
            "trend_slope_pct_per_bar": round(trend, 3),
            "short_trend_slope": round(short_trend, 3),
            "updown_volume_ratio_20d": udr if udr != float("inf") else None,
            "range_position_60d": round(pos, 2),
            "rvol_20d": rv,
            "recent_volume_fade": vol_fade,
            "atr_contraction_7v28": round(float(contraction), 2),
        },
        "computed_at": str(daily.index[-1]),
    }


class VolumeEngine:
    def __init__(self, provider: DataProvider, lookback_days: int = 200):
        self.provider = provider
        self.lookback = lookback_days

    def _daily(self, symbol: str) -> pd.DataFrame:
        return self.provider.get_bars(BarRequest(symbol, "1d", self.lookback))

    def get_rvol(self, symbol: str) -> dict:
        d = self._daily(symbol)
        return {
            "symbol": symbol,
            "rvol_20d": rvol(d, 20),
            "rvol_50d": rvol(d, 50),
            "updown_volume_ratio_20d": updown_volume_ratio(d, 20),
            "computed_at": str(d.index[-1]),
        }

    def get_phase(self, symbol: str) -> dict:
        return {"symbol": symbol} | classify_phase(self._daily(symbol))
