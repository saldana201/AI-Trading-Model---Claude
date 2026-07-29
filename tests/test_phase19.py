"""Phase 19 tests: contract structure decided by iv_rank AND variance risk premium.

The behaviour under test is a decision, not a number, so the cases that matter
are the *disagreements*. iv_rank asks "is IV high for this name?"; VRP asks "is
IV high versus what will actually be realized?" When they conflict, VRP is the
signal that determines whether you are overpaying, so it wins — and the reason
string has to say so, or the choice is unauditable.

Backwards compatibility is a hard requirement: vrp=None must reproduce the
pre-Phase-19 behaviour exactly, because every prior phase's tests depend on it.
"""

import pytest

from engines.options_mcp.logic import decide_structure, HIGH_IV_RANK


def vrp(verdict, iv=0.30, fc=0.20, ratio=None):
    return {"available": True, "verdict": verdict, "implied_vol": iv,
            "forecast_vol": fc, "ratio": ratio if ratio is not None else iv / fc}


# ---------- backwards compatibility ----------

def test_no_vrp_reproduces_iv_rank_behaviour_high():
    d = decide_structure(0.62, None)
    assert d["use_spread"] is True
    assert "IV rank 62%" in d["reason"]
    assert d["inputs"]["decided_by"] == "iv_rank"


def test_no_vrp_reproduces_iv_rank_behaviour_low():
    d = decide_structure(0.20, None)
    assert d["use_spread"] is False
    assert d["reason"] == "IV not elevated — single leg acceptable"


def test_missing_iv_rank_defaults_to_single_leg():
    assert decide_structure(None, None)["use_spread"] is False


def test_unavailable_vrp_is_treated_as_absent():
    d = decide_structure(0.62, {"available": False, "reason": "no fit"})
    assert d["use_spread"] is True
    assert d["inputs"]["decided_by"] == "iv_rank"


# ---------- agreement ----------

def test_both_say_rich_gives_spread():
    d = decide_structure(0.70, vrp("rich", iv=0.40, fc=0.22))
    assert d["use_spread"] is True
    assert d["inputs"]["decided_by"] == "both agree"
    assert "agree options are rich" in d["reason"]


def test_both_say_not_rich_gives_single_leg():
    d = decide_structure(0.20, vrp("cheap", iv=0.18, fc=0.30))
    assert d["use_spread"] is False
    assert d["inputs"]["decided_by"] == "both agree"


# ---------- disagreement: the whole point ----------

def test_cheap_vrp_overrides_high_iv_rank():
    """IV rank says 'high for this name' but IV is below forecast realized vol.
    Buying a spread here finances away convexity that is on sale."""
    d = decide_structure(0.62, vrp("cheap", iv=0.30, fc=0.42))
    assert d["use_spread"] is False
    assert "variance_risk_premium (overrode iv_rank)" in d["inputs"]["decided_by"]
    assert "cheap versus what should be realized" in d["reason"]
    assert "keep the convexity" in d["reason"]


def test_rich_vrp_overrides_low_iv_rank():
    """Unremarkable rank, but IV is well above forecast — still overpaying."""
    d = decide_structure(0.30, vrp("rich", iv=0.45, fc=0.25))
    assert d["use_spread"] is True
    assert "overrode iv_rank" in d["inputs"]["decided_by"]
    assert "despite an unremarkable rank" in d["reason"]


def test_override_records_both_signals_for_audit():
    d = decide_structure(0.62, vrp("cheap", iv=0.30, fc=0.42))
    i = d["inputs"]
    assert i["iv_rank"] == 0.62
    assert i["iv_rank_says"] == "spread"
    assert i["vrp_says"] == "single_leg"
    assert i["vrp"]["forecast_vol"] == 0.42


# ---------- equivocal VRP defers rather than inventing a view ----------

@pytest.mark.parametrize("verdict", ["slightly_rich", "fair", "slightly_cheap"])
def test_equivocal_vrp_defers_to_iv_rank(verdict):
    high = decide_structure(0.70, vrp(verdict))
    low = decide_structure(0.20, vrp(verdict))
    assert high["use_spread"] is True
    assert low["use_spread"] is False
    assert high["inputs"]["decided_by"] == "iv_rank"
    assert "not decisive" in high["reason"]


def test_equivocal_vrp_still_records_the_signal():
    d = decide_structure(0.70, vrp("fair", iv=0.30, fc=0.30))
    assert d["inputs"]["vrp"]["verdict"] == "fair"
    assert d["inputs"]["vrp_says"] == "not decisive"


# ---------- threshold behaviour ----------

def test_threshold_is_inclusive():
    assert decide_structure(HIGH_IV_RANK, None)["use_spread"] is True
    assert decide_structure(HIGH_IV_RANK - 0.001, None)["use_spread"] is False


def test_custom_threshold_is_honoured():
    assert decide_structure(0.40, None, high_iv_rank=0.35)["use_spread"] is True


# ---------- integration through select_contract ----------

def _chain(iv_rank):
    strikes = [90, 95, 100, 105, 110, 115]
    return {
        "symbol": "XYZ", "spot": 100.0, "iv_rank": iv_rank,
        "expiries": [{"date": "2026-08-24", "dte": 30}],
        "contracts": [
            {"strike": s, "expiry": "2026-08-24", "dte": 30, "type": t,
             "iv": 0.30, "oi": 900, "volume": 500,
             "bid": 2.0, "mid": 2.05, "ask": 2.1}
            for s in strikes for t in ("call", "put")],
    }


def test_select_contract_uses_vrp_to_flip_structure():
    from engines.options_mcp.logic import select_contract
    ch = _chain(iv_rank=0.62)          # rank alone would say spread
    without = select_contract(ch, "long", 100.0, 106.0, 112.0)
    with_cheap = select_contract(ch, "long", 100.0, 106.0, 112.0,
                                 vrp=vrp("cheap", iv=0.30, fc=0.42))
    assert without["instrument"] == "call_debit_spread"
    assert with_cheap["instrument"] == "call"        # VRP flipped it
    assert "structure_decision" in with_cheap


def test_select_contract_records_decision_provenance():
    from engines.options_mcp.logic import select_contract
    out = select_contract(_chain(0.62), "long", 100.0, 106.0, 112.0,
                          vrp=vrp("rich", iv=0.40, fc=0.22))
    d = out["structure_decision"]
    assert d["decided_by"] == "both agree"
    assert d["vrp"]["ratio"] == pytest.approx(0.40 / 0.22, rel=1e-6)


def test_engine_without_volatility_returns_no_vrp():
    from engines.options_mcp.logic import OptionsEngine

    class _P:
        def get_chain(self, sym, spot):
            return _chain(0.62)

    class _Prices:
        def get_bars(self, req):
            import pandas as pd
            idx = pd.date_range("2024-01-01", periods=30, freq="B")
            return pd.DataFrame({"open": 100.0, "high": 101.0, "low": 99.0,
                                 "close": 100.0, "volume": 1e6}, index=idx)

    eng = OptionsEngine(_Prices(), _P())
    assert eng._vrp_for("XYZ", _chain(0.62)) is None
    out = eng.select_contract("XYZ", "long", 100.0, 106.0, 112.0)
    assert out["structure_decision"]["decided_by"] == "iv_rank"
