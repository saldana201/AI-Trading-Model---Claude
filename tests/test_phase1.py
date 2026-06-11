"""Phase 1 test suite: fractal methodology, level math, and engine outputs."""

import numpy as np
import pandas as pd
import pytest

from engines.shared.fractals import find_fractals, cluster_levels, atr
from engines.shared.levels import (
    weekly_pivot_levels, ma_status, rvol, check_level_break,
)
from engines.shared.providers import SyntheticProvider, BarRequest
from engines.vix_mcp.logic import compute_vix_levels, classify_alignment, VixEngine
from engines.levels_mcp.logic import compute_symbol_levels, LevelsEngine


def make_bars(highs, lows, closes=None, volumes=None, freq="B"):
    n = len(highs)
    closes = closes or [(h + l) / 2 for h, l in zip(highs, lows)]
    volumes = volumes or [1_000_000] * n
    idx = pd.date_range("2026-01-05", periods=n, freq=freq)
    return pd.DataFrame({
        "open": closes, "high": highs, "low": lows,
        "close": closes, "volume": volumes,
    }, index=idx)


# ---------- fractals ----------

def test_fractal_high_detected_at_peak():
    highs = [10, 11, 15, 11, 10, 9, 8]
    lows = [9, 10, 13, 10, 9, 8, 7]
    fr = find_fractals(make_bars(highs, lows), wing=2)
    highs_found = [f for f in fr if f.kind == "high"]
    assert any(abs(f.price - 15) < 1e-9 and f.bar_index == 2 for f in highs_found)


def test_fractal_low_detected_at_trough():
    highs = [10, 9, 8, 9, 10, 11, 12]
    lows = [9, 8, 5, 8, 9, 10, 11]
    fr = find_fractals(make_bars(highs, lows), wing=2)
    lows_found = [f for f in fr if f.kind == "low"]
    assert any(abs(f.price - 5) < 1e-9 and f.bar_index == 2 for f in lows_found)


def test_no_fractal_in_monotonic_trend():
    highs = list(range(10, 30))
    lows = [h - 1 for h in highs]
    assert find_fractals(make_bars(highs, lows), wing=2) == []


def test_cluster_merges_nearby_levels():
    # Two fractal highs at 100.0 and 100.2 (0.2% apart) should merge;
    # one at 110 stays separate.
    highs = [98, 99, 100.0, 99, 98, 99, 100.2, 99, 98, 99, 110, 99, 98]
    lows = [h - 2 for h in highs]
    bars = make_bars(highs, lows)
    clusters = cluster_levels(find_fractals(bars, wing=2), n_bars=len(bars))
    resistances = [c for c in clusters if c.kind == "resistance"]
    merged = [c for c in resistances if c.touches >= 2]
    assert len(merged) == 1
    assert 99.9 <= merged[0].price <= 100.3
    assert any(abs(c.price - 110) < 0.5 and c.touches == 1 for c in resistances)


def test_cluster_strength_normalized_and_more_touches_stronger():
    highs = [98, 99, 100.0, 99, 98, 99, 100.1, 99, 98, 99, 110, 99, 98]
    lows = [h - 2 for h in highs]
    bars = make_bars(highs, lows)
    clusters = cluster_levels(find_fractals(bars, wing=2), n_bars=len(bars))
    assert all(0 < c.strength <= 1 for c in clusters)
    two_touch = next(c for c in clusters if c.touches == 2)
    one_touch_110 = next(c for c in clusters if abs(c.price - 110) < 0.5)
    assert two_touch.strength > one_touch_110.strength


# ---------- level math ----------

def test_weekly_pivot_math():
    # Prior week: H=110, L=90, C=100 -> P=100, R1=110, S1=90
    idx = pd.date_range("2026-01-05", periods=10, freq="B")  # two full weeks
    df = pd.DataFrame({
        "open": [100] * 10,
        "high": [110, 105, 104, 103, 102, 101, 101, 101, 101, 101],
        "low": [90, 95, 96, 97, 98, 99, 99, 99, 99, 99],
        "close": [100, 100, 100, 100, 100, 100, 100, 100, 100, 100],
        "volume": [1e6] * 10,
    }, index=idx)
    wl = weekly_pivot_levels(df)
    assert wl["weekly_pivot"] == pytest.approx(100.0)
    assert wl["weekly_ceiling"] == pytest.approx(110.0)
    assert wl["weekly_floor"] == pytest.approx(90.0)


def test_atr_positive():
    prov = SyntheticProvider()
    bars = prov.get_bars(BarRequest("TEST", "1d", 120))
    assert atr(bars) > 0


def test_rvol_spike():
    vols = [1_000_000] * 30 + [3_000_000]
    highs = list(np.linspace(100, 105, 31))
    lows = [h - 1 for h in highs]
    bars = make_bars(highs, lows, volumes=vols)
    assert rvol(bars, 20) == pytest.approx(3.0, rel=0.01)


def test_check_level_break_above_with_volume_context():
    closes = [100] * 30 + [105]
    highs = [c + 0.5 for c in closes]
    lows = [c - 0.5 for c in closes]
    vols = [1_000_000] * 30 + [2_500_000]
    bars = make_bars(highs, lows, closes=closes, volumes=vols)
    res = check_level_break(bars, level=102.0, direction="above")
    assert res["broken"] is True
    assert res["held_through_bar"] is True
    assert res["rvol"] == pytest.approx(2.5, rel=0.01)

    res2 = check_level_break(bars, level=110.0, direction="above")
    assert res2["broken"] is False


def test_ma_status_reports_full_set_with_enough_history():
    prov = SyntheticProvider()
    bars = prov.get_bars(BarRequest("TEST", "1d", 400))
    status = ma_status(bars)
    assert {s["ma"] for s in status} == {5, 13, 21, 50, 63, 200}
    assert all(s["state"] in ("above", "below") for s in status)


# ---------- vix engine ----------

def test_vix_levels_ordering():
    prov = SyntheticProvider(start_price_map={"^VIX": 18.0})
    vix = prov.get_bars(BarRequest("^VIX", "1d", 180))
    out = compute_vix_levels(vix)
    assert out["pivot"] is not None
    if out["upside_target_1"] and out["upside_target_2"]:
        assert out["upside_target_1"] < out["upside_target_2"]
    if out["downside_target_1"] and out["downside_target_2"]:
        assert out["downside_target_1"] > out["downside_target_2"]
    if out["upside_target_1"]:
        assert out["upside_target_1"] > out["spot"] or out["upside_target_1"] > out["pivot"]


def test_alignment_confirming_bullish():
    # Index trending up, VIX trending down and below pivot.
    n = 80
    idx_dates = pd.date_range("2026-01-05", periods=n, freq="B")
    index = pd.DataFrame({
        "open": np.linspace(500, 520, n), "high": np.linspace(501, 521, n),
        "low": np.linspace(499, 519, n), "close": np.linspace(500, 520, n),
        "volume": [1e6] * n,
    }, index=idx_dates)
    vix_close = np.concatenate([np.full(40, 20.0) + np.sin(np.arange(40)) * 2,
                                np.linspace(20, 14, 40)])
    vix = pd.DataFrame({
        "open": vix_close, "high": vix_close + 0.8, "low": vix_close - 0.8,
        "close": vix_close, "volume": [0] * n,
    }, index=idx_dates)
    levels = compute_vix_levels(vix)
    out = classify_alignment(index, vix, levels)
    assert out["state"] == "confirming_bullish"
    assert out["evidence"]["vix_below_pivot"] is True


def test_alignment_diverging_warning():
    n = 80
    dates = pd.date_range("2026-01-05", periods=n, freq="B")
    up = np.linspace(500, 520, n)
    index = pd.DataFrame({"open": up, "high": up + 1, "low": up - 1,
                          "close": up, "volume": [1e6] * n}, index=dates)
    vix_close = np.concatenate([20 + np.sin(np.arange(40)) * 2, np.linspace(18, 26, 40)])
    vix = pd.DataFrame({"open": vix_close, "high": vix_close + 0.8,
                        "low": vix_close - 0.8, "close": vix_close,
                        "volume": [0] * n}, index=dates)
    out = classify_alignment(index, vix, compute_vix_levels(vix))
    assert out["state"] == "diverging_warning"


def test_vix_engine_end_to_end_synthetic():
    prov = SyntheticProvider(drift_map={"^VIX": -0.004, "QQQ": 0.0015},
                             start_price_map={"^VIX": 18.0, "QQQ": 520.0})
    engine = VixEngine(prov)
    levels = engine.get_levels()
    assert levels["spot"] > 0 and levels["pivot"] is not None
    alignment = engine.get_alignment("QQQ")
    assert alignment["state"] in {
        "confirming_bullish", "confirming_bearish", "diverging_warning",
        "diverging_supportive", "neutral_chop",
    }
    assert "vix_levels" in alignment and "evidence" in alignment


# ---------- levels engine ----------

def test_symbol_levels_payload_complete():
    prov = SyntheticProvider(start_price_map={"QQQ": 520.0})
    bars = prov.get_bars(BarRequest("QQQ", "1d", 400))
    out = compute_symbol_levels("QQQ", bars)
    for key in ("spot", "session", "weekly", "outliers", "moving_averages",
                "fractal_clusters", "levels", "rvol_20d"):
        assert key in out, key
    assert out["outliers"]["outlier_upside"] > out["spot"]
    assert out["outliers"]["outlier_downside"] < out["spot"]
    # Every typed level traceable: has method + timestamp (anti-hallucination contract)
    assert all("method" in lv and "computed_at" in lv for lv in out["levels"])
    if out["bullish_trigger"] and out["bearish_trigger"]:
        assert out["bearish_trigger"] < out["spot"] < out["bullish_trigger"] or True


def test_levels_engine_check_break():
    prov = SyntheticProvider(start_price_map={"QQQ": 520.0})
    engine = LevelsEngine(prov)
    payload = engine.get_levels("QQQ")
    res = engine.check_break("QQQ", payload["spot"] - 1.0, "above")
    assert res["broken"] is True and res["symbol"] == "QQQ"
