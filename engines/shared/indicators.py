"""Shared indicator math: Wilder RSI, normalized trend slope, resampling."""

from __future__ import annotations

import numpy as np
import pandas as pd


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Wilder-smoothed RSI."""
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    out = 100 - 100 / (1 + rs)
    return out.fillna(100.0).where(avg_loss.notna(), np.nan)


def slope_pct(close: pd.Series, window: int = 40) -> float:
    """Linear-regression slope over `window` bars, as % of mean price per bar."""
    y = close.tail(window).to_numpy(dtype=float)
    if len(y) < 3:
        return 0.0
    x = np.arange(len(y), dtype=float)
    slope = np.polyfit(x, y, 1)[0]
    return float(slope / y.mean() * 100)


def resample_ohlcv(bars: pd.DataFrame, rule: str) -> pd.DataFrame:
    """Resample OHLCV bars (e.g. daily -> 'W-FRI' weekly, 'ME' monthly, '1h')."""
    out = bars.resample(rule).agg({
        "open": "first", "high": "max", "low": "min",
        "close": "last", "volume": "sum",
    }).dropna(subset=["close"])
    return out


def range_position(close: pd.Series, window: int = 60) -> float:
    """Where the latest close sits in the trailing window's range: 0=low, 1=high."""
    w = close.tail(window)
    lo, hi = float(w.min()), float(w.max())
    if hi == lo:
        return 0.5
    return float((w.iloc[-1] - lo) / (hi - lo))
