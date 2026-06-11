"""Phase 2 tests: volume phases, RSI/divergences, regime composite."""

import numpy as np
import pandas as pd
import pytest

from engines.shared.indicators import rsi, slope_pct, resample_ohlcv
from engines.shared.providers import SyntheticProvider
from engines.volume_mcp.logic import classify_phase, detect_failed_break, updown_volume_ratio
from engines.momentum_mcp.logic import find_divergences, MomentumEngine
from engines.regime_mcp.logic import compute_regime, RegimeEngine, MAX_RAW, WEIGHTS


def bars_from(closes, volumes=None, spread=0.5, freq="B"):
    closes = np.asarray(closes, dtype=float)
    n = len(closes)
    volumes = np.asarray(volumes if volumes is not None else [1e6] * n, dtype=float)
    idx = pd.date_range("2025-06-02", periods=n, freq=freq)
    return pd.DataFrame({
        "open": closes, "high": closes + spread, "low": closes - spread,
        "close": closes, "volume": volumes,
    }, index=idx)


# ---------- indicators ----------

def test_rsi_extremes():
    up = bars_from(np.linspace(100, 160, 60))
    down = bars_from(np.linspace(160, 100, 60))
    assert float(rsi(up["close"]).iloc[-1]) > 85
    assert float(rsi(down["close"]).iloc[-1]) < 15


def test_slope_sign():
    assert slope_pct(pd.Series(np.linspace(100, 120, 40))) > 0
    assert slope_pct(pd.Series(np.linspace(120, 100, 40))) < 0


def test_resample_weekly_shape():
    daily = bars_from(np.linspace(100, 110, 30))
    weekly = resample_ohlcv(daily, "W-FRI")
    assert 4 <= len(weekly) <= 8
    assert float(weekly["high"].max()) >= float(daily["high"].max()) - 1e-9


# ---------- volume phases ----------

def test_phase_mark_up():
    n = 80
    closes = np.linspace(100, 140, n) + np.sin(np.arange(n)) * 1.5
    chg = np.diff(closes, prepend=closes[0])
    vols = np.where(chg > 0, 2_000_000, 900_000)  # heavy up-day volume
    out = classify_phase(bars_from(closes, vols))
    assert out["phase"] == "mark_up"
    assert out["evidence"]["updown_volume_ratio_20d"] > 1.15


def test_phase_distribution():
    # Flat range near highs after a run, down days carry the volume.
    run = np.linspace(100, 130, 40)
    rng = np.random.default_rng(3)
    flat = 130 + np.cumsum(rng.normal(0, 0.25, 40))
    closes = np.concatenate([run, flat])
    chg = np.diff(closes, prepend=closes[0])
    vols = np.where(chg < 0, 2_200_000, 900_000)
    out = classify_phase(bars_from(closes, vols))
    assert out["phase"] in ("distribution", "failed_breakout", "exhaustion")


def test_failed_breakout_detected():
    base = [100 + (i % 5) * 0.3 for i in range(40)]      # 40-bar range ~100-101.2
    closes = base + [103.5, 99.8, 99.5]                   # pop above, slam back in
    assert detect_failed_break(bars_from(closes)) == "failed_breakout"


def test_failed_breakdown_detected():
    base = [100 + (i % 5) * 0.3 for i in range(40)]
    closes = base + [96.5, 100.6, 100.9]
    assert detect_failed_break(bars_from(closes)) == "failed_breakdown"


def test_updown_ratio_math():
    closes = [100, 101, 100, 101, 100, 101]   # alternating
    vols = [1e6, 3e6, 1e6, 3e6, 1e6, 3e6]     # all volume on up days
    assert updown_volume_ratio(bars_from(closes, vols), 5) > 2.5


# ---------- momentum / divergences ----------

def test_bearish_divergence_detected():
    # Two swing highs: price higher high, weaker momentum into the second.
    rng = np.random.default_rng(1)
    leg1 = np.linspace(100, 120, 25)                       # strong push -> pivot 1
    pull = np.linspace(120, 110, 10)
    leg2 = np.concatenate([np.linspace(110, 121.5, 30),    # grinding higher high
                           ])
    fade = np.linspace(121.5, 117, 8)
    closes = np.concatenate([leg1, pull, leg2, fade]) + rng.normal(0, 0.05, 73)
    divs = find_divergences(bars_from(closes), "1d")
    types = {d["type"] for d in divs}
    assert "bearish_divergence" in types
    d = next(x for x in divs if x["type"] == "bearish_divergence")
    assert d["pivots"][1]["price"] > d["pivots"][0]["price"]
    assert d["pivots"][1]["rsi"] < d["pivots"][0]["rsi"]


def test_no_divergence_in_clean_trend():
    closes = np.linspace(100, 130, 80)  # monotonic: no fractal pivots at all
    assert find_divergences(bars_from(closes), "1d") == []


def test_rsi_stack_timeframes():
    prov = SyntheticProvider(start_price_map={"QQQ": 520.0})
    stack = MomentumEngine(prov).get_rsi_stack("QQQ")["stack"]
    tfs = [s["timeframe"] for s in stack]
    assert "daily" in tfs and "weekly" in tfs and "monthly" in tfs
    assert all(0 <= s["rsi"] <= 100 for s in stack)
    assert all(s["zone"] in ("overbought", "oversold", "neutral") for s in stack)


# ---------- regime ----------

def _provider(vix_drift, idx_drift):
    return SyntheticProvider(
        drift_map={"^VIX": vix_drift, "QQQ": idx_drift, "SPY": idx_drift},
        start_price_map={"^VIX": 18.0, "QQQ": 520.0, "SPY": 600.0},
    )


def test_regime_payload_contract():
    out = compute_regime(_provider(-0.004, 0.0015))
    assert out["regime"] in ("risk_on", "risk_off", "chop")
    assert -10 <= out["risk_score"] <= 10
    assert {c["name"] for c in out["components"]} == set(WEIGHTS)
    # contributions reconcile with the headline score
    raw = sum(c["contribution"] for c in out["components"])
    assert out["risk_score"] == pytest.approx(round(raw / MAX_RAW * 10, 1), abs=0.05)
    for c in out["components"]:
        assert "evidence" in c and -2 <= c["score"] <= 2


def test_regime_directional_sanity():
    bull = compute_regime(_provider(-0.006, 0.0035))["risk_score"]
    bear = compute_regime(_provider(0.008, -0.0035))["risk_score"]
    assert bull > bear
    assert bear < 0 < bull


def test_regime_engine_end_to_end():
    out = RegimeEngine(_provider(-0.004, 0.002)).get_regime()
    assert "not_yet_classified" in out  # honest about Phase 3/4 gaps
