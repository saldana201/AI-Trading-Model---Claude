"""Phase 17 tests: transaction costs and slippage.

The properties that matter:
  - cost math is exact by construction (hand-computable), not approximately right;
  - costs scale inversely with stop width — the tight-stop setups that score best
    are the ones friction hurts most, and the model must show that;
  - options costs come from the *engine's* spread when it exists, and say so
    when they don't (glass box: a cost is auditable like a price level);
  - the sign-flip check fires when a gross edge does not survive friction —
    the FinMem/FINSABER failure mode, operationalized.
"""

import pytest

from backtest.costs import (
    CostModel, cost_in_r, apply_cost, cost_sensitivity, render_costs,
)
from backtest.harness import report


ZERO = CostModel(slippage_bps=0.0, commission_per_share=0.0,
                 commission_per_contract=0.0, option_spread_pct=0.0)


# ---------- stock cost math, exact ----------

def test_stock_slippage_is_hand_computable():
    # entry 100, stop 96 -> risk 4. 10bps of 100 = 0.10/share, two sides = 0.20
    # 0.20 / 4 = 0.05R. commission zero.
    m = CostModel(slippage_bps=10.0, commission_per_share=0.0)
    c = cost_in_r(100.0, 96.0, "stock", model=m)
    assert c["r_drag"] == pytest.approx(0.05, abs=1e-9)


def test_stock_commission_is_hand_computable():
    # $0.01/share × 2 sides = 0.02 on risk 4 -> 0.005R
    m = CostModel(slippage_bps=0.0, commission_per_share=0.01)
    c = cost_in_r(100.0, 96.0, "stock", model=m)
    assert c["r_drag"] == pytest.approx(0.005, abs=1e-9)


def test_tighter_stop_means_larger_cost_in_r():
    """The point most cost models miss: friction is fixed in dollars, so a
    tight stop pays a bigger fraction of its risk unit."""
    m = CostModel(slippage_bps=10.0, commission_per_share=0.0)
    wide = cost_in_r(100.0, 90.0, "stock", model=m)["r_drag"]   # risk 10
    tight = cost_in_r(100.0, 99.0, "stock", model=m)["r_drag"]  # risk 1
    assert tight == pytest.approx(10 * wide, rel=1e-9)
    assert tight > 0.15   # a 1-point stop bleeds real R


def test_zero_risk_distance_is_not_computable():
    c = cost_in_r(100.0, 100.0, "stock")
    assert c["r_drag"] == 0.0
    assert "not computable" in c["assumptions"][0]


# ---------- options costs come from engine evidence ----------

def test_option_uses_engine_spread_when_present():
    m = CostModel(commission_per_contract=0.0)
    c = cost_in_r(100.0, 96.0, "call_debit_spread", spread_pct=0.021, model=m)
    assert c["r_drag"] == pytest.approx(0.021, abs=1e-9)
    src = [x["source"] for x in c["components"] if x["name"] == "bid_ask_round_trip"]
    assert "options engine" in src[0]


def test_option_falls_back_to_default_and_says_so():
    m = CostModel(commission_per_contract=0.0, default_option_spread_pct=0.08)
    c = cost_in_r(100.0, 96.0, "call", spread_pct=None, model=m)
    assert c["r_drag"] == pytest.approx(0.08, abs=1e-9)
    assert any("default" in a for a in c["assumptions"])


def test_config_override_beats_engine_spread():
    m = CostModel(option_spread_pct=0.01, commission_per_contract=0.0)
    c = cost_in_r(100.0, 96.0, "call", spread_pct=0.20, model=m)
    assert c["r_drag"] == pytest.approx(0.01, abs=1e-9)


def test_spread_instrument_charges_two_legs_of_commission():
    m = CostModel(option_spread_pct=0.0, commission_per_contract=1.0,
                  contract_multiplier=100)
    single = cost_in_r(100.0, 96.0, "call", model=m)["r_drag"]
    vertical = cost_in_r(100.0, 96.0, "call_debit_spread", model=m)["r_drag"]
    assert vertical == pytest.approx(2 * single, rel=1e-9)


def test_options_assumption_is_always_disclosed():
    c = cost_in_r(100.0, 96.0, "call_debit_spread", spread_pct=0.02)
    assert any("debit ≈ dollar risk" in a for a in c["assumptions"])


def test_zero_model_is_free():
    assert cost_in_r(100.0, 96.0, "stock", model=ZERO)["r_drag"] == 0.0
    assert cost_in_r(100.0, 96.0, "call_debit_spread", spread_pct=0.05,
                     model=ZERO)["r_drag"] == 0.0


def test_multiplier_scales_everything():
    m = CostModel(slippage_bps=10.0, commission_per_share=0.0)
    base = cost_in_r(100.0, 96.0, "stock", model=m)["r_drag"]
    doubled = cost_in_r(100.0, 96.0, "stock", model=m.scaled(2.0))["r_drag"]
    assert doubled == pytest.approx(2 * base, rel=1e-9)


# ---------- apply_cost ----------

def test_costs_are_paid_on_winners_and_losers_alike():
    assert apply_cost(2.0, 0.05) == pytest.approx(1.95)
    assert apply_cost(-1.0, 0.05) == pytest.approx(-1.05)


def test_apply_cost_passes_through_none():
    assert apply_cost(None, 0.05) is None


# ---------- sensitivity: the FINSABER check ----------

def test_sign_flip_detected_when_edge_dies_under_costs():
    gross = [0.10, 0.12, 0.08, 0.11]     # thin positive edge
    drags = [0.15] * 4                    # friction larger than the edge
    s = cost_sensitivity(gross, drags)
    assert s["gross_avg_r"] > 0
    assert s["net_avg_r"] < 0
    assert s["sign_flip_under_costs"] is True
    assert "DOES NOT SURVIVE" in s["verdict"]


def test_robust_edge_reports_headroom_not_a_flip():
    gross = [1.0, 1.2, 0.8, 1.1]
    drags = [0.05] * 4
    s = cost_sensitivity(gross, drags)
    assert s["sign_flip_under_costs"] is False
    assert s["cost_headroom_x"] > 2
    assert "survives" in s["verdict"]


def test_thin_headroom_is_called_fragile():
    gross = [0.10] * 6
    drags = [0.06] * 6
    s = cost_sensitivity(gross, drags)
    assert s["sign_flip_under_costs"] is False
    assert s["cost_headroom_x"] < 2
    assert "fragile" in s["verdict"]


def test_no_gross_edge_is_not_blamed_on_costs():
    s = cost_sensitivity([-0.5, -0.2, -0.3], [0.05] * 3)
    assert "not the binding problem" in s["verdict"]
    assert s["breakeven_drag_r"] is None


def test_cost_curve_is_monotonically_decreasing():
    s = cost_sensitivity([1.0, 0.5, 0.8], [0.1] * 3)
    avgs = [c["avg_r"] for c in s["curve"]]
    assert avgs == sorted(avgs, reverse=True)
    assert s["curve"][0]["cost_multiple"] == 0.0     # gross is on the curve


def test_breakeven_drag_equals_gross_edge():
    s = cost_sensitivity([0.4, 0.6], [0.01, 0.01])
    assert s["breakeven_drag_r"] == pytest.approx(0.5, abs=1e-9)


def test_sensitivity_unavailable_without_trades():
    s = cost_sensitivity([], [])
    assert s["available"] is False
    assert "unavailable" in render_costs(s)


def test_none_gross_entries_are_skipped():
    s = cost_sensitivity([1.0, None, 0.5], [0.1, 0.1, 0.1])
    assert s["n"] == 2


# ---------- report integration ----------

def _outcomes(rows):
    return [{"realized_r": net, "gross_r": g, "cost_r": c, "confidence": 7.0,
             "final_state": "CLOSED", "components": {}}
            for g, c, net in rows]


def test_report_includes_cost_block_when_costs_modeled():
    rep = report(_outcomes([(1.0, 0.05, 0.95), (-1.0, 0.05, -1.05),
                            (0.8, 0.05, 0.75), (1.2, 0.05, 1.15)]))
    assert rep["costs"]["available"] is True
    assert rep["costs"]["gross_avg_r"] > rep["costs"]["net_avg_r"]


def test_report_costs_unavailable_for_gross_only_rows():
    # live journal rows carry no cost fields; must not fake a zero-cost verdict
    rows = [{"realized_r": r, "confidence": 7.0, "final_state": "CLOSED",
             "components": {}} for r in (0.5, -1.0, 1.2)]
    rep = report(rows)
    assert rep["costs"]["available"] is False
    assert "gross by construction" in rep["costs"]["reason"]


def test_rigor_uses_net_r_not_gross():
    # realized_r is net; the rigor block must be computed on the net series
    rows = _outcomes([(1.0, 0.5, 0.5), (1.0, 0.5, 0.5), (1.0, 0.5, 0.5),
                      (1.0, 0.5, 0.5)])
    rep = report(rows)
    assert rep["overall"]["avg_r"] == pytest.approx(0.5, abs=1e-9)
