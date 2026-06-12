"""Phase 8 tests: R-multiple math, forward simulation, harness end to end."""

import pytest

from backtest.harness import (
    Backtest, realized_r_from_events, report, render_text,
)
from backtest.run import composer_factory_for
from alerts.lifecycle import Trade, step
from tests.test_phase3 import bull_world


def run_trade(closes, **over):
    base = dict(symbol="T", direction="long", entry_trigger=100.0, stop=96.0,
                target_1=106.0, target_2=112.0, trail_distance=3.0)
    base.update(over)
    tr = Trade(**base)
    events = []
    for i, c in enumerate(closes):
        events += step(tr, {"close": c, "high": c + 0.5, "low": c - 0.5,
                            "time": f"t{i}", "rvol": 2.0})
    return tr, events


# ---------- R math (exact, by construction) ----------

def test_r_full_winner_half_at_t1_half_at_t2():
    # entry 101, risk 5; half at T1 106 (+5), half at T2-close 113 (+12)
    tr, ev = run_trade([101, 102, 107, 113])
    r, state, _ = realized_r_from_events(tr, ev, last_close=113)
    assert state == "CLOSED"
    assert r == pytest.approx((0.5 * 5 + 0.5 * 12) / 5, abs=0.01)  # 1.7


def test_r_stop_out_is_negative_one_ish():
    # trigger holds (ACTIVE at 102), then close gaps through the stop
    tr, ev = run_trade([101, 102, 95.0])
    r, state, _ = realized_r_from_events(tr, ev, last_close=95.0)
    assert state == "STOPPED"
    assert r == pytest.approx((95.0 - 101) / 5, abs=0.01)  # ≈ -1.2 (gap past stop)


def test_failed_trigger_is_no_fill_not_a_loss():
    # break then immediate reversal = re-armed, never filled (live semantics)
    tr, ev = run_trade([101, 95.0])
    r, state, _ = realized_r_from_events(tr, ev, last_close=95.0)
    assert state == "NO_FILL" and r is None


def test_r_open_at_horizon_marked_to_market():
    tr, ev = run_trade([101, 103])           # ACTIVE, never exits
    r, state, _ = realized_r_from_events(tr, ev, last_close=104.0)
    assert state == "OPEN_AT_HORIZON"
    assert r == pytest.approx((104.0 - 101) / 5, abs=0.01)


def test_r_no_fill_when_never_triggered():
    tr, ev = run_trade([99, 98.5, 99.2])
    r, state, _ = realized_r_from_events(tr, ev, last_close=99.2)
    assert state == "NO_FILL" and r is None


def test_r_short_direction():
    tr, ev = run_trade([99, 98, 93.5, 87],
                       direction="short", entry_trigger=100.0, stop=104.0,
                       target_1=94.0, target_2=88.0)
    r, state, _ = realized_r_from_events(tr, ev, last_close=87)
    assert state == "CLOSED" and r > 1.0     # winner in R terms


# ---------- report ----------

def make_outcome(conf, r, state="CLOSED", comps=None):
    return {"symbol": "T", "as_of": "d", "direction": "long",
            "confidence": conf, "entry_trigger": 100, "stop": 96,
            "target_1": 106, "target_2": 112, "sector_etf": "SMH",
            "classification": "canslim_leader",
            "components": comps or {"vix_alignment": 0.8, "risk_reward": 0.6},
            "final_state": state, "realized_r": r, "bars_held": 5,
            "exit_reason": "x"}


def test_report_buckets_and_component_edge():
    rows = [
        make_outcome(8.0, 1.5, comps={"vix_alignment": 0.9, "risk_reward": 0.7}),
        make_outcome(8.1, 0.8, comps={"vix_alignment": 0.8, "risk_reward": 0.6}),
        make_outcome(6.2, -1.0, comps={"vix_alignment": 0.3, "risk_reward": 0.5}),
        make_outcome(7.0, None, state="NO_FILL"),
    ]
    rep = report(rows, compose_points=10, no_trade_points=4)
    assert rep["setups"] == 4 and rep["fill_rate"] == 0.75
    assert rep["by_confidence"]["≥7.5"]["n"] == 2
    assert rep["by_confidence"]["≥7.5"]["win_rate"] == 1.0
    assert rep["by_confidence"]["<6.5"]["avg_r"] == -1.0
    assert rep["component_signal"]["vix_alignment"]["edge"] > 0
    txt = render_text(rep)
    assert "by confidence" in txt and "component edge" in txt


# ---------- harness end to end (synthetic bull world) ----------

def test_backtest_runs_end_to_end():
    prov = bull_world()
    bt = Backtest(prov, composer_factory_for("synthetic"),
                  span_bars=140, step_bars=20, horizon_bars=12)
    rep = bt.run()
    assert rep["compose_points"] >= 5
    assert rep["setups"] + rep["no_trade_points"] > 0
    for o in rep["outcomes"]:
        assert o["final_state"] in ("NO_FILL", "CLOSED", "STOPPED",
                                    "DETERIORATED", "OPEN_AT_HORIZON")
        assert "components" in o and o["confidence"] >= 6.0
    if rep["overall"].get("n"):
        assert -5 < rep["overall"]["avg_r"] < 5   # sane R range
    assert rep["caveats"]
