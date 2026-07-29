"""Phase 18 tests: the volatility engine.

Layers:
  - estimator math checked against closed-form values on constructed bars;
  - GARCH parameter *recovery* on simulated paths with known truth (the real
    test of a hand-rolled MLE — validated separately against `arch` 8.0.0,
    which is deliberately not a shipped dependency);
  - variance-risk-premium banding, which is what actually feeds the contract
    decision;
  - engine-level provenance, because the validator needs method + computed_at.
"""

import math

import numpy as np
import pandas as pd
import pytest

from engines.volatility_mcp.logic import (
    log_returns, realized_vol, ewma_vol, garch11_fit, garch_forecast,
    vol_cone, variance_risk_premium, expected_move, VolatilityEngine,
    TRADING_DAYS,
)
from engines.shared.providers import SyntheticProvider


def bars_from_close(closes, hi_mult=1.0, lo_mult=1.0):
    c = np.asarray(closes, float)
    idx = pd.date_range("2024-01-01", periods=len(c), freq="B")
    return pd.DataFrame({
        "open": c, "high": c * hi_mult, "low": c * lo_mult,
        "close": c, "volume": np.full(len(c), 1_000_000.0)}, index=idx)


def simulate_garch(n, omega, alpha, beta, seed=7):
    rng = np.random.default_rng(seed)
    s2 = omega / (1 - alpha - beta)
    out = np.empty(n)
    for t in range(n):
        x = rng.normal(0.0, math.sqrt(s2))
        out[t] = x
        s2 = omega + alpha * x * x + beta * s2
    return out


# ---------- returns & realized vol ----------

def test_log_returns_are_exact_on_a_constant_growth_series():
    closes = [100 * (1.01 ** i) for i in range(10)]
    r = log_returns(bars_from_close(closes))
    assert np.allclose(r, math.log(1.01))


def test_realized_vol_of_a_flat_series_is_zero():
    assert realized_vol(bars_from_close([100.0] * 40), 20) == pytest.approx(0.0)


def test_realized_vol_matches_hand_computed_annualization():
    rng = np.random.default_rng(3)
    r = rng.normal(0, 0.01, 300)
    closes = 100 * np.exp(np.cumsum(r))
    bars = bars_from_close(closes)
    got = realized_vol(bars, 100)
    expected = np.std(log_returns(bars.tail(101)), ddof=1) * math.sqrt(TRADING_DAYS)
    assert got == pytest.approx(expected, rel=1e-9)


def test_parkinson_needs_a_real_range_and_beats_zero():
    bars = bars_from_close([100.0] * 60, hi_mult=1.02, lo_mult=0.98)
    # close-to-close sees a flat series; Parkinson sees the intraday range
    assert realized_vol(bars, 20, "close_to_close") == pytest.approx(0.0)
    assert realized_vol(bars, 20, "parkinson") > 0.05


def test_unknown_estimator_raises():
    with pytest.raises(ValueError):
        realized_vol(bars_from_close([100.0] * 40), 20, "nonsense")


def test_realized_vol_returns_none_on_too_few_bars():
    assert realized_vol(bars_from_close([100.0, 101.0]), 60) is None


def test_ewma_reacts_faster_than_equal_weight():
    calm = np.full(200, 0.001)
    shocked = np.concatenate([calm, np.full(10, 0.05)])
    assert ewma_vol(shocked) > ewma_vol(calm) * 5


def test_ewma_none_on_short_input():
    assert ewma_vol(np.array([0.01, 0.02])) is None


# ---------- GARCH: parameter recovery ----------

def test_garch_recovers_known_parameters():
    r = simulate_garch(1500, 2e-6, 0.08, 0.90, seed=7)
    fit = garch11_fit(r)
    assert fit is not None
    assert fit.alpha == pytest.approx(0.08, abs=0.03)
    assert fit.beta == pytest.approx(0.90, abs=0.05)
    assert fit.persistence == pytest.approx(0.98, abs=0.02)


def test_garch_recovers_a_second_parameter_set():
    r = simulate_garch(1500, 5e-6, 0.15, 0.80, seed=11)
    fit = garch11_fit(r)
    assert fit is not None
    assert fit.alpha == pytest.approx(0.15, abs=0.06)
    assert fit.persistence == pytest.approx(0.95, abs=0.04)


def test_garch_is_deterministic():
    r = simulate_garch(400, 2e-6, 0.08, 0.90, seed=5)
    a, b = garch11_fit(r), garch11_fit(r)
    assert (a.alpha, a.beta, a.omega) == (b.alpha, b.beta, b.omega)


def test_garch_respects_stationarity():
    fit = garch11_fit(simulate_garch(800, 2e-6, 0.08, 0.90, seed=2))
    assert 0 < fit.persistence < 1
    assert fit.omega > 0 and fit.alpha >= 0 and fit.beta >= 0


def test_garch_declines_on_too_few_observations():
    assert garch11_fit(np.random.default_rng(1).normal(0, 0.01, 40)) is None


def test_garch_declines_on_zero_variance():
    assert garch11_fit(np.zeros(200)) is None


# ---------- GARCH forecasting ----------

def test_forecast_mean_reverts_toward_unconditional():
    r = simulate_garch(1200, 2e-6, 0.08, 0.90, seed=9)
    fit = garch11_fit(r)
    short = garch_forecast(fit, r, 1)["horizon_annualized_vol"]
    far = garch_forecast(fit, r, 250)["horizon_annualized_vol"]
    unc = fit.to_dict()["uncond_annualized_vol"]
    # the long horizon must sit closer to unconditional than the 1-day does
    assert abs(far - unc) < abs(short - unc) or short == pytest.approx(unc, abs=1e-6)


def test_half_life_is_positive_and_finite():
    r = simulate_garch(800, 2e-6, 0.08, 0.90, seed=4)
    hl = garch_forecast(garch11_fit(r), r, 21)["half_life_days"]
    assert hl is not None and hl > 0


def test_horizon_sigma_grows_with_horizon():
    r = simulate_garch(800, 2e-6, 0.08, 0.90, seed=6)
    fit = garch11_fit(r)
    s5 = garch_forecast(fit, r, 5)["horizon_total_sigma"]
    s60 = garch_forecast(fit, r, 60)["horizon_total_sigma"]
    assert s60 > s5


# ---------- expected move ----------

def test_expected_move_scales_with_sqrt_time():
    one = expected_move(100.0, 0.30, 21)
    four = expected_move(100.0, 0.30, 84)
    assert four == pytest.approx(2 * one, rel=1e-9)


def test_expected_move_matches_closed_form():
    assert expected_move(100.0, 0.20, 252) == pytest.approx(20.0, rel=1e-9)


# ---------- variance risk premium: the contract decision ----------

def test_vrp_flags_rich_options():
    v = variance_risk_premium(0.45, 0.30)
    assert v["verdict"] == "rich"
    assert v["ratio"] == pytest.approx(1.5, rel=1e-6)
    assert "spread" in v["interpretation"]


def test_vrp_flags_cheap_options():
    v = variance_risk_premium(0.20, 0.35)
    assert v["verdict"] == "cheap"
    assert v["premium"] < 0
    assert "single long leg" in v["interpretation"]


def test_vrp_fair_band_is_symmetric_around_one():
    assert variance_risk_premium(0.30, 0.30)["verdict"] == "fair"
    assert variance_risk_premium(0.309, 0.30)["verdict"] == "fair"
    assert variance_risk_premium(0.291, 0.30)["verdict"] == "fair"


def test_vrp_rejects_nonpositive_inputs():
    assert variance_risk_premium(0.0, 0.3)["available"] is False
    assert variance_risk_premium(0.3, None)["available"] is False


def test_vrp_answers_what_iv_rank_cannot():
    """Same IV rank, opposite conclusions — the whole point of the engine."""
    high_forecast = variance_risk_premium(0.30, 0.42)   # IV 30% but RV forecast 42%
    low_forecast = variance_risk_premium(0.30, 0.18)    # same IV, RV forecast 18%
    assert high_forecast["verdict"] == "cheap"
    assert low_forecast["verdict"] == "rich"


# ---------- vol cone ----------

def test_vol_cone_percentile_is_in_unit_interval():
    rng = np.random.default_rng(8)
    closes = 100 * np.exp(np.cumsum(rng.normal(0, 0.012, 400)))
    cone = vol_cone(bars_from_close(closes))
    assert cone
    for horizon in cone.values():
        assert 0.0 <= horizon["percentile_of_current"] <= 1.0
        assert horizon["min"] <= horizon["median"] <= horizon["max"]


# ---------- engine-level provenance ----------

def _engine():
    return VolatilityEngine(
        SyntheticProvider(drift_map={"QQQ": 0.0015},
                          start_price_map={"QQQ": 520.0}))


def test_engine_forecast_carries_provenance():
    out = _engine().get_forecast("QQQ", 21)
    assert out["available"] is True
    assert "GARCH(1,1)" in out["method"]
    assert out["computed_at"]                      # validator needs this
    assert out["forecast"]["horizon_annualized_vol"] > 0


def test_engine_realized_carries_provenance():
    out = _engine().get_realized("QQQ")
    assert out["available"] is True
    assert out["computed_at"] and out["method"]
    assert out["estimators"]["close_to_close"]["21"] > 0


def test_engine_iv_comparison_end_to_end():
    out = _engine().get_iv_comparison("QQQ", implied_vol=0.60, dte=30)
    assert out["available"] is True
    assert out["variance_risk_premium"]["verdict"] in (
        "rich", "slightly_rich", "fair", "slightly_cheap", "cheap")
    assert out["implied_expected_move"] > 0
    assert out["forecast_expected_move"] > 0
    assert out["computed_at"]


def test_engine_degrades_without_enough_bars():
    eng = VolatilityEngine(
        SyntheticProvider(start_price_map={"QQQ": 100.0}), lookback_days=20)
    out = eng.get_forecast("QQQ")
    assert out["available"] is False
    assert "80 daily bars" in out["reason"]
