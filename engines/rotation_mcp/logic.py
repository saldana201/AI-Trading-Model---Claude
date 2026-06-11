"""rotation-mcp core logic (design doc §4.5, PRD §6).

Tracks the PRD's 31-ETF sector universe. For each ETF: relative performance
vs SPY over 1/4/12/24/48 weeks, RVOL, MA-stack position, and a rotation
classification:

- leading:       top quartile over both 4w and 12w
- improving:     bottom half over 12w, top quartile over 1-2w, reclaiming the
                 21-day MA — the early-rotation flag (URA/URNM/NLR case)
- deteriorating: top half over 12w, bottom quartile over 1-2w, losing short MAs
- lagging:       bottom quartile across windows
- neutral:       everything else
"""

from __future__ import annotations

import pandas as pd

from ..shared.levels import ma_status, rvol
from ..shared.providers import BarRequest, DataProvider

UNIVERSE = [
    "XLK", "XLC", "XLY", "XLI", "XLF", "XLP", "XLV", "XLU", "XLE", "XLB",
    "XOP", "OIH", "SMH", "SOXX", "PAVE", "GRID", "IFRA", "IGV", "MAGS", "MGK",
    "IWF", "SCHG", "XLRE", "AIQ", "XES", "URA", "URNM", "XAR", "AIPO", "DTCR",
    "NLR",
]
WINDOWS_WEEKS = [1, 4, 12, 24, 48]
BENCHMARK = "SPY"


def _perf(close: pd.Series, weeks: int) -> float | None:
    bars = weeks * 5
    if len(close) <= bars:
        return None
    return float(close.iloc[-1] / close.iloc[-1 - bars] - 1) * 100


def relative_performance(etf: pd.DataFrame, bench: pd.DataFrame) -> dict:
    out = {}
    for w in WINDOWS_WEEKS:
        a, b = _perf(etf["close"], w), _perf(bench["close"], w)
        out[f"{w}w"] = None if a is None or b is None else round(a - b, 2)
        out[f"{w}w_abs"] = None if a is None else round(a, 2)
    return out


def _rank_pct(values: dict[str, float | None], sym: str) -> float | None:
    """Percentile rank of sym among non-null values (1.0 = best)."""
    vals = {k: v for k, v in values.items() if v is not None}
    if sym not in vals or len(vals) < 2:
        return None
    sorted_syms = sorted(vals, key=lambda k: vals[k])
    return round(sorted_syms.index(sym) / (len(sorted_syms) - 1), 2)


def classify_rotation(rank_1w, rank_4w, rank_12w, ma21_state, ma21_event) -> str:
    if None in (rank_1w, rank_4w, rank_12w):
        return "neutral"
    if rank_4w >= 0.75 and rank_12w >= 0.75:
        return "leading"
    if rank_12w <= 0.5 and rank_1w >= 0.75 and (
        ma21_state == "above" or ma21_event == "reclaimed"
    ):
        return "improving"
    if rank_12w >= 0.5 and rank_1w <= 0.25 and ma21_state == "below":
        return "deteriorating"
    if rank_12w <= 0.25 and rank_1w <= 0.5:
        return "lagging"
    return "neutral"


class RotationEngine:
    def __init__(self, provider: DataProvider, universe: list[str] | None = None,
                 lookback_days: int = 280):
        self.provider = provider
        self.universe = universe or UNIVERSE
        self.lookback = lookback_days

    def _bars(self, symbol: str) -> pd.DataFrame:
        return self.provider.get_bars(BarRequest(symbol, "1d", self.lookback))

    def get_leaderboard(self) -> dict:
        bench = self._bars(BENCHMARK)
        rows = {}
        for sym in self.universe:
            try:
                bars = self._bars(sym)
            except Exception as exc:  # a missing ETF shouldn't sink the board
                rows[sym] = {"error": str(exc)}
                continue
            perf = relative_performance(bars, bench)
            mas = {m["ma"]: m for m in ma_status(bars)}
            rows[sym] = {
                "relative_perf": perf,
                "rvol_20d": rvol(bars, 20),
                "ma21": mas.get(21, {}).get("state"),
                "ma21_event": mas.get(21, {}).get("recent_event"),
                "ma50": mas.get(50, {}).get("state"),
                "ma200": mas.get(200, {}).get("state"),
            }

        ok = {s: r for s, r in rows.items() if "error" not in r}
        for w in (1, 4, 12):
            vals = {s: r["relative_perf"].get(f"{w}w") for s, r in ok.items()}
            for s in ok:
                ok[s][f"rank_{w}w"] = _rank_pct(vals, s)

        for s, r in ok.items():
            r["status"] = classify_rotation(
                r.get("rank_1w"), r.get("rank_4w"), r.get("rank_12w"),
                r.get("ma21"), r.get("ma21_event"),
            )

        order = {"leading": 0, "improving": 1, "neutral": 2,
                 "deteriorating": 3, "lagging": 4}
        board = sorted(
            ({"symbol": s} | r for s, r in ok.items()),
            key=lambda r: (order.get(r["status"], 9), -(r.get("rank_4w") or 0)),
        )
        return {
            "benchmark": BENCHMARK,
            "as_of": str(bench.index[-1]),
            "etfs": board,
            "errors": {s: r["error"] for s, r in rows.items() if "error" in r},
        }

    def get_rotation_candidates(self) -> dict:
        board = self.get_leaderboard()
        return {
            "as_of": board["as_of"],
            "leading": [e for e in board["etfs"] if e["status"] == "leading"],
            "improving": [e for e in board["etfs"] if e["status"] == "improving"],
            "deteriorating": [e for e in board["etfs"] if e["status"] == "deteriorating"],
        }
