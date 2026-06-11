"""fundamentals-mcp core logic (design doc §4.8, PRD §14).

Fundamental snapshot with the same provider abstraction as price data:
YFinanceFundamentals for live use, SyntheticFundamentals for offline dev.
The earnings-date proximity flag is a hard input to the setup composer —
swing setups inside the earnings window get flagged.
"""

from __future__ import annotations

import hashlib
from datetime import date, timedelta
from typing import Protocol

EARNINGS_WINDOW_DAYS = 7


class FundamentalsProvider(Protocol):
    def get_snapshot(self, symbol: str) -> dict: ...


def _grade(revenue_g, eps_g) -> str:
    if revenue_g is None or eps_g is None:
        return "unknown"
    if revenue_g >= 0.20 and eps_g >= 0.25:
        return "strong"
    if revenue_g >= 0.08 and eps_g >= 0.10:
        return "moderate"
    return "weak"


def enrich(snapshot: dict, today: date | None = None) -> dict:
    today = today or date.today()
    ed = snapshot.get("earnings_date")
    days_to = None
    if ed:
        days_to = (date.fromisoformat(ed) - today).days
    snapshot["days_to_earnings"] = days_to
    snapshot["in_earnings_window"] = (
        days_to is not None and 0 <= days_to <= EARNINGS_WINDOW_DAYS
    )
    snapshot["growth_grade"] = _grade(
        snapshot.get("revenue_growth"), snapshot.get("eps_growth"))
    return snapshot


class YFinanceFundamentals:
    """Live snapshot via yfinance .info / calendar. Prototyping-grade."""

    def get_snapshot(self, symbol: str) -> dict:
        import yfinance as yf
        t = yf.Ticker(symbol)
        info = t.info or {}
        ed = None
        try:
            cal = t.calendar
            dates = cal.get("Earnings Date") if isinstance(cal, dict) else None
            if dates:
                ed = str(dates[0])[:10]
        except Exception:
            pass
        return enrich({
            "symbol": symbol,
            "revenue_growth": info.get("revenueGrowth"),
            "eps_growth": info.get("earningsGrowth"),
            "profit_margin": info.get("profitMargins"),
            "forward_pe": info.get("forwardPE"),
            "institutional_pct": info.get("heldPercentInstitutions"),
            "sector": info.get("sector"),
            "industry": info.get("industry"),
            "earnings_date": ed,
            "source": "yfinance",
        })


class SyntheticFundamentals:
    """Deterministic per-symbol snapshot for offline dev; optionally overridden."""

    def __init__(self, overrides: dict[str, dict] | None = None,
                 today: date | None = None):
        self.overrides = overrides or {}
        self.today = today or date.today()

    def get_snapshot(self, symbol: str) -> dict:
        if symbol in self.overrides:
            return enrich({"symbol": symbol, "source": "synthetic",
                           **self.overrides[symbol]}, self.today)
        h = int(hashlib.sha256(symbol.encode()).hexdigest(), 16)
        return enrich({
            "symbol": symbol,
            "revenue_growth": round((h % 45) / 100, 2),          # 0..0.44
            "eps_growth": round(((h // 7) % 55) / 100, 2),       # 0..0.54
            "profit_margin": round(((h // 11) % 30) / 100, 2),
            "forward_pe": 15 + (h // 13) % 40,
            "institutional_pct": round(0.4 + ((h // 17) % 50) / 100, 2),
            "sector": "Technology",
            "industry": "—",
            "earnings_date": str(self.today + timedelta(days=(h // 19) % 60)),
            "source": "synthetic",
        }, self.today)


class FundamentalsEngine:
    def __init__(self, provider: FundamentalsProvider):
        self.provider = provider

    def get_snapshot(self, symbol: str) -> dict:
        return self.provider.get_snapshot(symbol)
