"""Data providers for the Confluence engines.

Engines never talk to vendors directly in production (they read the shared
database). For Phase 1 prototyping, providers fetch bars on demand:

- YFinanceProvider: live data via yfinance (dev/prototyping feed per design doc §3)
- SyntheticProvider: deterministic random-walk bars for tests and offline dev
"""

from __future__ import annotations

import hashlib

from dataclasses import dataclass
from typing import Protocol

import numpy as np
import pandas as pd

REQUIRED_COLS = ["open", "high", "low", "close", "volume"]


@dataclass(frozen=True)
class BarRequest:
    symbol: str
    interval: str = "1d"   # "1d", "30m", "5m", ...
    lookback_days: int = 120


class DataProvider(Protocol):
    def get_bars(self, req: BarRequest) -> pd.DataFrame:
        """Return a DataFrame indexed by timestamp with columns
        open/high/low/close/volume, oldest first."""
        ...


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    df = df.rename(columns={c: c.lower() for c in df.columns})
    df = df[[c for c in REQUIRED_COLS if c in df.columns]].copy()
    missing = [c for c in REQUIRED_COLS if c not in df.columns]
    for c in missing:
        df[c] = 0.0 if c == "volume" else np.nan
    df = df.sort_index()
    return df.dropna(subset=["close"])


class YFinanceProvider:
    """Live bars via yfinance. Suitable for prototyping only."""

    def get_bars(self, req: BarRequest) -> pd.DataFrame:
        import yfinance as yf

        period = f"{req.lookback_days}d"
        # yfinance caps intraday history; clamp sensibly.
        if req.interval.endswith("m") and req.lookback_days > 59:
            period = "59d"
        df = yf.Ticker(req.symbol).history(period=period, interval=req.interval)
        if df.empty:
            raise RuntimeError(f"No data returned for {req.symbol} ({req.interval})")
        df.index = pd.to_datetime(df.index)
        return _normalize(df)


class SyntheticProvider:
    """Seeded random-walk bars so tests and demos are reproducible offline.

    drift_map lets a test shape a symbol's behavior, e.g. an uptrending QQQ
    against a downtrending ^VIX to exercise alignment logic.
    """

    def __init__(self, seed: int = 7, drift_map: dict[str, float] | None = None,
                 start_price_map: dict[str, float] | None = None,
                 drift_change_map: dict[str, tuple[float, float, float]] | None = None):
        self.seed = seed
        self.drift_map = drift_map or {}
        self.start_price_map = start_price_map or {}
        # symbol -> (early_drift, late_drift, switch_fraction in 0..1)
        # e.g. {"URA": (-0.003, 0.006, 0.9)} = laggard turning up in the last 10%
        self.drift_change_map = drift_change_map or {}

    MASTER_BARS = 800   # one master series per (symbol, interval); every
                        # lookback slices its tail, so spot is identical
                        # across engines regardless of how much history
                        # each one requests.

    def _build_master(self, symbol: str, interval: str) -> pd.DataFrame:
        digest = hashlib.sha256(f"{symbol}|{interval}|{self.seed}".encode()).hexdigest()
        rng = np.random.default_rng(int(digest[:8], 16))
        n = self.MASTER_BARS
        start = self.start_price_map.get(symbol, 100.0)

        if symbol in self.drift_change_map:
            early, late, frac = self.drift_change_map[symbol]
            k = int(n * frac)
            drift_arr = np.concatenate([np.full(k, early), np.full(n - k, late)])
        else:
            drift_arr = np.full(n, self.drift_map.get(symbol, 0.0))

        rets = rng.normal(loc=drift_arr, scale=0.011, size=n)
        close = start * np.exp(np.cumsum(rets))
        spread = np.abs(rng.normal(0.004, 0.002, size=n))
        open_ = close * (1 + rng.normal(0, 0.003, size=n))
        high = np.maximum(open_, close) * (1 + spread)
        low = np.minimum(open_, close) * (1 - spread)
        volume = rng.integers(1_000_000, 5_000_000, size=n).astype(float)
        spikes = rng.choice(n, size=max(1, n // 20), replace=False)
        volume[spikes] *= rng.uniform(2.0, 4.0, size=len(spikes))

        freq = "B" if interval == "1d" else "30min"
        idx = pd.date_range(end=pd.Timestamp.now("UTC").floor("min"), periods=n, freq=freq)
        return pd.DataFrame(
            {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
            index=idx,
        )

    def get_bars(self, req: BarRequest) -> pd.DataFrame:
        key = (req.symbol, req.interval)
        if not hasattr(self, "_master"):
            self._master: dict = {}
        if key not in self._master:
            self._master[key] = self._build_master(req.symbol, req.interval)
        n = req.lookback_days if req.interval == "1d" else min(req.lookback_days * 13, self.MASTER_BARS)
        n = max(n, 60)
        return self._master[key].iloc[-n:]


class ReplayProvider:
    """Wraps another provider and replays its bars progressively — get_bars
    returns history only up to the cursor, advance() moves one bar forward.
    This is how the alert engine is tested and demoed bar by bar."""

    def __init__(self, base: DataProvider, start_offset: int = 30):
        self.base = base
        self.offset = start_offset   # bars held back from "now"
        self._full: dict[tuple, pd.DataFrame] = {}

    def _full_bars(self, req: BarRequest) -> pd.DataFrame:
        key = (req.symbol, req.interval)
        if key not in self._full:
            self._full[key] = self.base.get_bars(
                BarRequest(req.symbol, req.interval, req.lookback_days + self.offset))
        return self._full[key]

    def get_bars(self, req: BarRequest) -> pd.DataFrame:
        full = self._full_bars(req)
        end = len(full) - self.offset
        return full.iloc[:max(end, 10)]

    def advance(self, bars: int = 1) -> bool:
        self.offset = max(self.offset - bars, 0)
        return self.offset > 0


class ScriptedProvider:
    """Serves explicit bar DataFrames per symbol — for deterministic lifecycle
    demos where the price path must be exact. Combine with ReplayProvider."""

    def __init__(self, frames: dict[str, pd.DataFrame]):
        self.frames = frames

    def get_bars(self, req: BarRequest) -> pd.DataFrame:
        if req.symbol not in self.frames:
            raise KeyError(f"No scripted bars for {req.symbol}")
        return self.frames[req.symbol]
