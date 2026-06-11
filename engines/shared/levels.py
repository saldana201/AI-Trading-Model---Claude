"""Shared level math used by levels-mcp (and partially by vix-mcp).

Implements design doc §4.2: weekly pivot/ceiling/floor, ATR-based outlier
levels, gap levels, moving-average reclaim/loss status, RVOL, and the
level-break primitive the alert engine polls.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .fractals import atr

MA_SET = [5, 13, 21, 50, 63, 200]


def weekly_pivot_levels(daily: pd.DataFrame) -> dict:
    """Classic floor-trader pivots from the prior completed week."""
    weekly = daily.resample("W-FRI").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}
    ).dropna()
    if len(weekly) < 2:
        raise ValueError("Need at least two weeks of daily bars")
    prior = weekly.iloc[-2]
    p = (prior["high"] + prior["low"] + prior["close"]) / 3.0
    return {
        "weekly_pivot": round(float(p), 2),
        "weekly_ceiling": round(float(2 * p - prior["low"]), 2),   # R1
        "weekly_floor": round(float(2 * p - prior["high"]), 2),    # S1
        "prior_week_high": round(float(prior["high"]), 2),
        "prior_week_low": round(float(prior["low"]), 2),
    }


def outlier_levels(daily: pd.DataFrame, mult: float = 1.5) -> dict:
    """Outlier upside/downside: current week's range extended by mult * ATR(14)."""
    a = atr(daily, 14)
    this_week = daily[daily.index >= daily.index[-1] - pd.Timedelta(days=daily.index[-1].weekday())]
    hi = float(this_week["high"].max())
    lo = float(this_week["low"].min())
    return {
        "outlier_upside": round(hi + mult * a, 2),
        "outlier_downside": round(lo - mult * a, 2),
        "atr14": round(a, 2),
    }


def day_levels(daily: pd.DataFrame) -> dict:
    today, prior = daily.iloc[-1], daily.iloc[-2]
    gap = round(float(today["open"] - prior["close"]), 2)
    return {
        "high_of_day": round(float(today["high"]), 2),
        "low_of_day": round(float(today["low"]), 2),
        "prior_day_high": round(float(prior["high"]), 2),
        "prior_day_low": round(float(prior["low"]), 2),
        "gap": gap,
        "gap_fill_level": round(float(prior["close"]), 2) if gap != 0 else None,
    }


def ma_status(daily: pd.DataFrame, reclaim_window: int = 3) -> list[dict]:
    """Above/below each MA in MA_SET plus reclaimed/lost-within-window flags."""
    close = daily["close"]
    out = []
    for n in MA_SET:
        if len(close) < n + reclaim_window:
            continue
        ma = close.rolling(n).mean()
        above_now = bool(close.iloc[-1] > ma.iloc[-1])
        was_above = bool(close.iloc[-1 - reclaim_window] > ma.iloc[-1 - reclaim_window])
        state = "above" if above_now else "below"
        event = None
        if above_now and not was_above:
            event = "reclaimed"
        elif not above_now and was_above:
            event = "lost"
        out.append({
            "ma": n,
            "value": round(float(ma.iloc[-1]), 2),
            "state": state,
            "recent_event": event,
            "distance_pct": round(float(close.iloc[-1] / ma.iloc[-1] - 1) * 100, 2),
        })
    return out


def rvol(daily: pd.DataFrame, lookback: int = 20) -> float:
    """Today's volume vs trailing average (excluding today)."""
    vol = daily["volume"]
    base = vol.iloc[-1 - lookback:-1].mean()
    return round(float(vol.iloc[-1] / base), 2) if base > 0 else 0.0


def check_level_break(bars: pd.DataFrame, level: float, direction: str,
                      rvol_lookback: int = 20) -> dict:
    """The alert-engine primitive: has the latest bar broken `level`?

    direction: "above" | "below". Returns break status with volume context so
    a 0.4x-RVOL break never reads the same as a 2.5x one (design doc §4.2).
    """
    last = bars.iloc[-1]
    broke = bool(last["close"] > level) if direction == "above" else bool(last["close"] < level)
    held = bool(last["low"] > level) if direction == "above" else bool(last["high"] < level)
    return {
        "level": round(float(level), 2),
        "direction": direction,
        "broken": broke,
        "held_through_bar": broke and held,
        "close": round(float(last["close"]), 2),
        "rvol": rvol(bars, rvol_lookback),
        "bar_time": str(bars.index[-1]),
    }
