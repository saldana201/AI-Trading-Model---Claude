"""Phase 5 tests: greeks, GEX profile, walls/flip, contract selection,
options-aware scoring, and composer integration with graceful degradation."""

from datetime import date

import pytest

from engines.options_mcp.greeks import gamma, vanna, expected_move
from engines.options_mcp.providers import SyntheticOptions
from engines.options_mcp.logic import (
    gex_profile, dealer_zones, select_contract, contract_quality,
    options_alignment, OptionsEngine,
)
from engines.shared.providers import SyntheticProvider
from orchestrator.scoring import score_setup, WEIGHTS
from tests.test_phase3 import bull_world, make_composer, base_ctx


TODAY = date(2026, 6, 10)


def chain(**kw):
    defaults = dict(iv_rank=0.35, base_iv=0.30, spread_pct=0.02,
                    call_wall_offset=0.05, put_wall_offset=-0.06, today=TODAY)
    defaults.update(kw)
    return SyntheticOptions(**defaults).get_chain("TEST", 100.0)


# ---------- greeks ----------

def test_gamma_peaks_at_the_money():
    atm = gamma(100, 100, 0.3, 30 / 365)
    otm = gamma(100, 112, 0.3, 30 / 365)
    deep = gamma(100, 130, 0.3, 30 / 365)
    assert atm > otm > deep > 0


def test_vanna_sign_otm_call_positive():
    assert vanna(100, 110, 0.3, 30 / 365) > 0     # OTM call: d2 < 0
    assert vanna(100, 85, 0.3, 30 / 365) < 0      # deep ITM: d2 > 0


def test_expected_move_scales_with_iv_and_time():
    assert expected_move(100, 0.4, 30) > expected_move(100, 0.2, 30)
    assert expected_move(100, 0.3, 45) > expected_move(100, 0.3, 7)
    assert expected_move(100, 0.3, 0) == 0


# ---------- GEX profile ----------

def test_walls_detected_at_engineered_strikes():
    p = gex_profile(chain())
    assert p["call_wall"] == pytest.approx(105.0, abs=1.5)
    assert p["put_wall"] == pytest.approx(94.0, abs=1.5)
    assert p["zero_gamma_flip"] is not None
    assert p["put_wall"] < p["zero_gamma_flip"] < p["call_wall"]


def test_gamma_regime_classification():
    p = gex_profile(chain())
    z = dealer_zones(p)
    assert z["gamma_regime"] in ("positive", "negative")
    assert ("dampen" in z["reading"]) == (z["gamma_regime"] == "positive")


# ---------- contract selection ----------

def test_low_iv_selects_single_leg_near_entry():
    out = select_contract(chain(iv_rank=0.30), "long", entry=102.0,
                          target_1=106.0, target_2=110.0)
    assert out["instrument"] == "call"
    assert out["strike"] <= 102.0
    assert 21 <= out["dte"] <= 50
    assert out["spread_pct"] <= 0.08 and out["oi"] >= 500


def test_high_iv_selects_debit_spread_with_short_leg_at_t2():
    out = select_contract(chain(iv_rank=0.72), "long", entry=102.0,
                          target_1=106.0, target_2=110.0)
    assert out["instrument"] == "call_debit_spread"
    assert out["short_strike"] == pytest.approx(110.0, abs=1.5)
    assert "debit spread" in out["reason"]


def test_illiquid_chain_falls_back_to_stock_with_reason():
    out = select_contract(chain(spread_pct=0.30, oi_scale=0.05), "long",
                          entry=102.0, target_1=106.0, target_2=110.0)
    assert out["instrument"] == "stock"
    assert "no liquid strike" in out["reason"]


def test_expected_move_flag_on_distant_target():
    out = select_contract(chain(base_iv=0.12), "long", entry=102.0,
                          target_1=125.0, target_2=130.0)
    assert out.get("t1_within_expected_move") is False or out["instrument"] == "stock"


def test_short_direction_selects_puts():
    out = select_contract(chain(iv_rank=0.30), "short", entry=98.0,
                          target_1=93.0, target_2=90.0)
    assert out["instrument"] == "put"
    assert out["strike"] >= 98.0


def test_contract_quality_verdicts():
    ch = chain()
    exp = ch["expiries"][2]["date"]            # 30 dte
    cw = gex_profile(ch)["call_wall"]
    q = contract_quality(ch, cw, exp, "call")  # wall strike = huge OI
    assert q["found"] and q["liquid"]
    assert contract_quality(ch, 12345.0, exp, "call")["found"] is False


# ---------- alignment scoring ----------

def test_alignment_headwind_when_wall_blocks_t1():
    profile = {"symbol": "T", "spot": 100, "zero_gamma_flip": 96.0,
               "call_wall": 104.0, "put_wall": 92.0}
    blocked = options_alignment(profile, "long", entry=101.0, target_1=108.0)
    clear = options_alignment({**profile, "call_wall": 112.0}, "long",
                              entry=101.0, target_1=108.0)
    assert clear["value"] > blocked["value"]
    assert any("between entry and T1" in r for r in blocked["reasons"])


def test_score_uses_real_options_components():
    oa = {"value": 0.85, "reasons": ["no call-wall resistance before T1"],
          "flip": 96.0, "call_wall": 115.0, "put_wall": 92.0}
    contract = {"instrument": "call", "oi": 4000, "spread_pct": 0.02,
                "t1_within_expected_move": True}
    out = score_setup("long", base_ctx(options_alignment=oa, contract=contract))
    assert "placeholder" not in out["components"]["options_alignment"]
    assert "placeholder" not in out["components"]["liquidity"]
    assert out["components"]["options_alignment"]["value"] == 0.85

    headwind = score_setup("long", base_ctx(
        options_alignment={"value": 0.2, "reasons": ["call wall 104 sits between "
                                                     "entry and T1"],
                           "flip": 96.0, "call_wall": 104.0, "put_wall": 92.0},
        contract=contract))
    assert headwind["score"] < out["score"]
    assert any("headwind" in r for r in headwind["risks"])


def test_score_degrades_to_placeholder_without_options():
    out = score_setup("long", base_ctx())
    assert out["components"]["options_alignment"].get("placeholder") is True
    assert out["components"]["liquidity"].get("placeholder") is True


# ---------- composer integration ----------

def test_composer_attaches_options_and_instruments():
    prov = bull_world()
    composer = make_composer(prov)
    composer.options = OptionsEngine(prov, SyntheticOptions(iv_rank=0.70, today=TODAY))
    out = composer.compose()
    assert len(out["setups"]) >= 1
    for s in out["setups"]:
        assert s["options"] is not None and "gamma_regime" in s["options"]
        sug = s["instrument_suggestion"]
        assert sug is not None
        assert s["instrument"] == sug["instrument"]
        if sug["instrument"].endswith("debit_spread"):
            assert sug["long_strike"] is not None
        comp = s["score_components"]["options_alignment"]
        assert "placeholder" not in comp


def test_composer_degrades_when_options_engine_breaks():
    class Broken:
        def get_alignment(self, *a, **k): raise RuntimeError("feed down")
        def select_contract(self, *a, **k): raise RuntimeError("feed down")
        def get_dealer_zones(self, *a, **k): raise RuntimeError("feed down")

    composer = make_composer(bull_world())
    composer.options = Broken()
    out = composer.compose()
    assert len(out["setups"]) >= 1
    for s in out["setups"]:
        assert s["options"] is None and s["instrument"] == "stock"
        assert s["score_components"]["options_alignment"].get("placeholder") is True
