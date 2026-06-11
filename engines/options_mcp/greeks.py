"""Black-Scholes gamma and vanna (design doc §4.6).

Only the greeks the positioning engine needs. Gamma is identical for calls
and puts; vanna (dDelta/dVol) is too. Stdlib-only.
"""

from __future__ import annotations

import math

SQRT_2PI = math.sqrt(2 * math.pi)


def _phi(x: float) -> float:
    return math.exp(-0.5 * x * x) / SQRT_2PI


def _d1_d2(spot: float, strike: float, iv: float, t_years: float,
           r: float = 0.04) -> tuple[float, float]:
    if t_years <= 0 or iv <= 0 or spot <= 0 or strike <= 0:
        return 0.0, 0.0
    vt = iv * math.sqrt(t_years)
    d1 = (math.log(spot / strike) + (r + 0.5 * iv * iv) * t_years) / vt
    return d1, d1 - vt


def gamma(spot: float, strike: float, iv: float, t_years: float,
          r: float = 0.04) -> float:
    """Per-share gamma. Peaks at the money, same for calls and puts."""
    if t_years <= 0 or iv <= 0:
        return 0.0
    d1, _ = _d1_d2(spot, strike, iv, t_years, r)
    return _phi(d1) / (spot * iv * math.sqrt(t_years))


def vanna(spot: float, strike: float, iv: float, t_years: float,
          r: float = 0.04) -> float:
    """dDelta/dVol per 1.00 of vol. Positive for OTM calls (d2 < 0)."""
    if t_years <= 0 or iv <= 0:
        return 0.0
    d1, d2 = _d1_d2(spot, strike, iv, t_years, r)
    return -_phi(d1) * d2 / iv


def expected_move(spot: float, atm_iv: float, dte: int) -> float:
    """1-sigma expected move in price terms over the contract's life."""
    return spot * atm_iv * math.sqrt(max(dte, 0) / 365.0)
