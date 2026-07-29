"""fundamentals-mcp core logic (design doc §4.8, PRD §14).

Fundamental snapshot with the same provider abstraction as price data:
YFinanceFundamentals for live use, SyntheticFundamentals for offline dev.
The earnings-date proximity flag is a hard input to the setup composer —
swing setups inside the earnings window get flagged.
"""

from __future__ import annotations

import json
import os
import time

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
    """Live snapshot via yfinance .info / calendar, with a persistent disk cache.

    Why the cache is not optional
    -----------------------------
    `compose()` calls this once per candidate per compose point. A 143-ticker
    watchlist over ~200 compose points in two directions is tens of thousands of
    Yahoo requests, which gets throttled into timeouts (curl 28).

    The throttling caused a subtler and worse problem than slowness: when some
    `.info` calls time out and silently return empty, those symbols score
    differently, so the SAME backtest produces different setups on each run.
    That non-determinism is the most likely source of the 4x spread we saw
    between bias_check, benchmark and walk_forward on supposedly identical
    settings. A cache makes a backtest reproducible.

    Caching is also honest here: fundamentals are near-static across a backtest
    window, and the engine already applies today's snapshot to historical bars
    (a known look-ahead limitation documented in the report caveats). Caching
    does not add bias — it just stops re-fetching the same value thousands of
    times.

    Set CONFLUENCE_FUNDAMENTALS_CACHE to relocate; delete the file to refresh.
    """

    _MEM: dict[str, dict] = {}
    _DISK_LOADED = False

    def __init__(self, cache_path: str | None = None, ttl_days: int = 7):
        self.cache_path = cache_path or os.environ.get(
            "CONFLUENCE_FUNDAMENTALS_CACHE", ".cache/fundamentals.json")
        self.ttl_days = ttl_days
        self._load_disk()

    def _load_disk(self) -> None:
        if YFinanceFundamentals._DISK_LOADED:
            return
        YFinanceFundamentals._DISK_LOADED = True
        try:
            with open(self.cache_path) as fh:
                data = json.load(fh)
            cutoff = time.time() - self.ttl_days * 86400
            YFinanceFundamentals._MEM = {
                k: v for k, v in data.items()
                if isinstance(v, dict) and v.get("_fetched_at", 0) > cutoff}
        except Exception:
            YFinanceFundamentals._MEM = {}

    def _save_disk(self) -> None:
        try:
            os.makedirs(os.path.dirname(self.cache_path) or ".", exist_ok=True)
            with open(self.cache_path, "w") as fh:
                json.dump(YFinanceFundamentals._MEM, fh)
        except Exception:
            pass

    def get_snapshot(self, symbol: str) -> dict:
        hit = YFinanceFundamentals._MEM.get(symbol)
        if hit is not None:
            return {k: v for k, v in hit.items() if k != "_fetched_at"}

        import yfinance as yf
        info: dict = {}
        ed = None
        try:
            t = yf.Ticker(symbol)
            info = t.info or {}
            try:
                cal = t.calendar
                dates = cal.get("Earnings Date") if isinstance(cal, dict) else None
                if dates:
                    ed = str(dates[0])[:10]
            except Exception:
                pass
        except Exception:
            # Network failure (throttling, timeout). Cache the empty result so a
            # single run does not retry the same dead symbol hundreds of times,
            # and so the run stays deterministic. Fundamentals degrade to
            # unknown rather than crashing the backtest.
            info = {}

        snap = enrich({
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
        YFinanceFundamentals._MEM[symbol] = {**snap, "_fetched_at": time.time()}
        if len(YFinanceFundamentals._MEM) % 10 == 0:
            self._save_disk()
        return snap

    def flush(self) -> None:
        self._save_disk()


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
