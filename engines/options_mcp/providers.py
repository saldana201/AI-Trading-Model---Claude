"""Options chain providers (design doc §3, §4.6).

Chain format (plain dicts, provider-agnostic):

    {"symbol": str, "spot": float, "iv_rank": float|None,
     "expiries": [{"date": "YYYY-MM-DD", "dte": int}],
     "contracts": [{"expiry": str, "dte": int, "strike": float,
                    "type": "call"|"put", "iv": float, "oi": int,
                    "volume": int, "bid": float, "mid": float, "ask": float}]}

SyntheticOptions builds deterministic chains with engineerable call/put wall
strikes, IV rank, and spread quality — so wall detection, contract selection,
and liquidity gates are all testable offline. YFinanceOptions is the
prototyping live feed (iv_rank is not derivable from a single yfinance chain
snapshot, so it is honestly None there unless supplied).
"""

from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Protocol


class OptionsProvider(Protocol):
    def get_chain(self, symbol: str, spot: float) -> dict: ...


def _nice_step(spot: float) -> float:
    for limit, step in ((25, 0.5), (60, 1.0), (120, 2.5), (300, 5.0)):
        if spot < limit:
            return step
    return 10.0


class SyntheticOptions:
    def __init__(self, iv_rank: float = 0.35, base_iv: float = 0.30,
                 spread_pct: float = 0.02, oi_scale: float = 1.0,
                 call_wall_offset: float = 0.05, put_wall_offset: float = -0.06,
                 today: date | None = None, dtes: tuple = (7, 14, 30, 45)):
        self.iv_rank = iv_rank
        self.base_iv = base_iv
        self.spread_pct = spread_pct
        self.oi_scale = oi_scale
        self.call_wall_offset = call_wall_offset
        self.put_wall_offset = put_wall_offset
        self.today = today or date.today()
        self.dtes = dtes

    def get_chain(self, symbol: str, spot: float) -> dict:
        step = _nice_step(spot)
        strikes = [round(k * step, 2) for k in
                   range(int(spot * 0.82 / step), int(spot * 1.18 / step) + 1)]
        cw = min(strikes, key=lambda k: abs(k - spot * (1 + self.call_wall_offset)))
        pw = min(strikes, key=lambda k: abs(k - spot * (1 + self.put_wall_offset)))

        expiries = [{"date": str(self.today + timedelta(days=d)), "dte": d}
                    for d in self.dtes]
        contracts = []
        for exp in expiries:
            t = exp["dte"] / 365.0
            for k in strikes:
                m = (k - spot) / spot
                # put-skewed smile
                iv = self.base_iv * (1 + 0.6 * max(-m, 0) + 0.15 * max(m, 0))
                # OI: bell around ATM + engineered wall spikes
                bell = math.exp(-(m / 0.07) ** 2)
                for typ in ("call", "put"):
                    oi = 800 * bell
                    if typ == "call" and k == cw:
                        oi += 6000
                    if typ == "put" and k == pw:
                        oi += 6000
                    oi = int(oi * self.oi_scale)
                    intrinsic = max(spot - k, 0) if typ == "call" else max(k - spot, 0)
                    extrinsic = spot * iv * math.sqrt(t) * 0.4 * math.exp(-(m / 0.12) ** 2)
                    mid = max(round(intrinsic + extrinsic, 2), 0.05)
                    half = mid * self.spread_pct / 2
                    contracts.append({
                        "expiry": exp["date"], "dte": exp["dte"], "strike": k,
                        "type": typ, "iv": round(iv, 4), "oi": oi,
                        "volume": int(oi * 0.35),
                        "bid": round(mid - half, 2), "mid": mid,
                        "ask": round(mid + half, 2),
                    })
        return {"symbol": symbol, "spot": spot, "iv_rank": self.iv_rank,
                "expiries": expiries, "contracts": contracts}


class YFinanceOptions:
    """Live chains via yfinance — prototyping-grade (delayed, OI updates
    overnight). iv_rank is None unless the caller supplies one."""

    def __init__(self, max_expiries: int = 4, iv_rank: float | None = None):
        self.max_expiries = max_expiries
        self.iv_rank = iv_rank

    def get_chain(self, symbol: str, spot: float) -> dict:
        import yfinance as yf
        t = yf.Ticker(symbol)
        today = date.today()
        expiries, contracts = [], []
        for exp in (t.options or [])[: self.max_expiries]:
            dte = (date.fromisoformat(exp) - today).days
            if dte < 0:
                continue
            expiries.append({"date": exp, "dte": dte})
            chain = t.option_chain(exp)
            for typ, df in (("call", chain.calls), ("put", chain.puts)):
                for _, row in df.iterrows():
                    bid = float(row.get("bid") or 0)
                    ask = float(row.get("ask") or 0)
                    mid = round((bid + ask) / 2, 4) if ask > 0 else float(row.get("lastPrice") or 0)
                    contracts.append({
                        "expiry": exp, "dte": dte, "strike": float(row["strike"]),
                        "type": typ, "iv": float(row.get("impliedVolatility") or 0),
                        "oi": int(row.get("openInterest") or 0),
                        "volume": int(row.get("volume") or 0),
                        "bid": bid, "mid": mid, "ask": ask,
                    })
        return {"symbol": symbol, "spot": spot, "iv_rank": self.iv_rank,
                "expiries": expiries, "contracts": contracts}
