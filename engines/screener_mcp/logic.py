"""screener-mcp core logic (design doc §4.8, PRD §15).

CANSLIM-style technical screen. For each symbol: the full filter checklist,
a pass count, extension measurement vs the 21d/50d MAs, distance from
52-week high, breakout/pullback structure, and a candidate classification:

- canslim_leader:       passes the core stack, near highs, not overextended
- speculative_momentum: strong short-term tape but core stack incomplete
- laggard_turn:         below long MAs but reclaiming short ones on volume
- overextended:         leader structure but stretched > 9% over the 21d MA
- no_setup:             everything else
"""

from __future__ import annotations

import pandas as pd

from ..shared.indicators import slope_pct
from ..shared.levels import ma_status, rvol
from ..shared.providers import BarRequest, DataProvider

EXTENSION_LIMIT_21 = 9.0   # % over the 21d MA where chasing gets penalized (PRD §17)
NEAR_HIGH_PCT = 8.0        # within this % of the 52-week high counts as "near highs"


def screen_symbol(symbol: str, daily: pd.DataFrame) -> dict:
    close = daily["close"]
    spot = float(close.iloc[-1])
    mas = {m["ma"]: m for m in ma_status(daily)}

    def above(n):
        return mas.get(n, {}).get("state") == "above"

    ma50 = mas.get(50, {}).get("value")
    ma200 = mas.get(200, {}).get("value")
    ma5 = close.rolling(5).mean()
    crossed_above_5d = bool(
        len(close) > 6 and close.iloc[-1] > ma5.iloc[-1] and close.iloc[-2] <= ma5.iloc[-2]
    )

    high_52w = float(daily["high"].tail(252).max())
    pct_off_high = round((1 - spot / high_52w) * 100, 2)
    ext_21 = mas.get(21, {}).get("distance_pct")
    rv = rvol(daily, 20)
    trend = slope_pct(close, 40)

    # Constructive pullback: uptrend, 3-8% off highs, holding the 21d MA.
    pullback = bool(trend > 0.05 and 3 <= pct_off_high <= NEAR_HIGH_PCT and above(21))
    # Breakout: new 20-day closing high on above-average volume.
    breakout = bool(spot >= float(close.tail(20).max()) - 1e-9 and rv >= 1.3)

    checks = {
        "above_50d": above(50),
        "above_200d": above(200),
        "50d_above_200d": bool(ma50 and ma200 and ma50 > ma200),
        "above_13d": above(13),
        "above_21d": above(21),
        "above_63d": above(63),
        "crossed_above_5d": crossed_above_5d,
        "near_52w_high": pct_off_high <= NEAR_HIGH_PCT,
        "high_rvol": rv >= 1.3,
        "breakout_or_pullback": breakout or pullback,
        "not_overextended": ext_21 is not None and ext_21 <= EXTENSION_LIMIT_21,
    }
    passes = sum(checks.values())
    core = all(checks[k] for k in ("above_50d", "above_200d", "50d_above_200d",
                                   "above_21d", "near_52w_high"))

    if core and checks["not_overextended"] and checks["breakout_or_pullback"]:
        klass = "canslim_leader"
    elif core and not checks["not_overextended"]:
        klass = "overextended"
    elif not checks["above_200d"] and above(13) and above(21) and rv >= 1.2:
        klass = "laggard_turn"
    elif checks["high_rvol"] and above(13) and trend > 0.1 and not core:
        klass = "speculative_momentum"
    elif core:
        klass = "canslim_leader" if checks["not_overextended"] else "overextended"
    else:
        klass = "no_setup"

    return {
        "symbol": symbol,
        "spot": round(spot, 2),
        "classification": klass,
        "passes": passes,
        "total_checks": len(checks),
        "checks": checks,
        "pct_off_52w_high": pct_off_high,
        "extension_vs_21d_pct": ext_21,
        "rvol_20d": rv,
        "trend_slope": round(trend, 3),
        "structure": "breakout" if breakout else "pullback" if pullback else "none",
        "computed_at": str(daily.index[-1]),
    }


class ScreenerEngine:
    def __init__(self, provider: DataProvider, lookback_days: int = 400):
        self.provider = provider
        self.lookback = lookback_days

    def screen(self, symbols: list[str]) -> dict:
        results, errors = [], {}
        for sym in symbols:
            try:
                bars = self.provider.get_bars(BarRequest(sym, "1d", self.lookback))
                results.append(screen_symbol(sym, bars))
            except Exception as exc:
                errors[sym] = str(exc)
        rank = {"canslim_leader": 0, "laggard_turn": 1, "speculative_momentum": 2,
                "overextended": 3, "no_setup": 4}
        results.sort(key=lambda r: (rank.get(r["classification"], 9), -r["passes"]))
        return {"results": results, "errors": errors}
