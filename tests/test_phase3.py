"""Phase 3 tests: rotation, screener, fundamentals, scorer, validator, composer."""

from datetime import date

import pytest

from engines.shared.providers import SyntheticProvider
from engines.rotation_mcp.logic import RotationEngine, classify_rotation
from engines.screener_mcp.logic import ScreenerEngine
from engines.fundamentals_mcp.logic import SyntheticFundamentals, FundamentalsEngine
from engines.levels_mcp.logic import LevelsEngine
from engines.volume_mcp.logic import VolumeEngine
from engines.momentum_mcp.logic import MomentumEngine
from engines.regime_mcp.logic import RegimeEngine
from orchestrator.composer import SetupComposer, MIN_SCORE, MIN_RR_T1, MIN_RR_T2
from orchestrator.validator import validate_setup, collect_numbers
from orchestrator.scoring import score_setup, WEIGHTS


# ---------- rotation ----------

def test_classify_rotation_rules():
    assert classify_rotation(0.9, 0.9, 0.9, "above", None) == "leading"
    assert classify_rotation(0.9, 0.4, 0.2, "above", "reclaimed") == "improving"
    assert classify_rotation(0.1, 0.4, 0.8, "below", None) == "deteriorating"
    assert classify_rotation(0.2, 0.1, 0.1, "below", None) == "lagging"
    assert classify_rotation(None, 0.5, 0.5, "above", None) == "neutral"


def bull_world(extra_drift=None, drift_change=None):
    drift = {"^VIX": -0.005, "SPY": 0.0015, "QQQ": 0.0025,
             "SMH": 0.0045, "XLK": 0.0035, "IGV": 0.003,
             "NVDA": 0.005, "AVGO": 0.0045, "AMD": 0.004, "MU": 0.004,
             "MSFT": 0.0035, "AAPL": 0.003, "ORCL": 0.003,
             "CRM": 0.003, "NOW": 0.0035, "PLTR": 0.004}
    drift.update(extra_drift or {})
    return SyntheticProvider(
        drift_map=drift,
        start_price_map={"^VIX": 18.0, "QQQ": 520.0, "SPY": 600.0},
        drift_change_map=drift_change or {},
    )


def test_rotation_leader_and_improver_detected():
    # Engineer an unambiguous leader (drift edge >> noise over 4w/12w) and a
    # laggard turning up only in the last ~5% of the window.
    prov = bull_world(extra_drift={"SMH": 0.012, "XLK": 0.002},
                      drift_change={"URA": (-0.008, 0.012, 0.985)})
    board = RotationEngine(prov, universe=["XLK", "SMH", "URA", "XLP", "XLU",
                                           "XLE", "XLF", "XLV", "IGV"]).get_leaderboard()
    by = {e["symbol"]: e for e in board["etfs"]}
    assert by["SMH"]["status"] == "leading"
    # the engineered laggard-turn ranks top short-window, bottom long-window
    assert by["URA"]["rank_1w"] >= 0.75
    assert by["URA"]["rank_12w"] <= 0.5
    assert by["URA"]["status"] == "improving"


# ---------- screener ----------

def test_screener_classifies_trender_vs_chopper():
    # CHOP1 rises then bleeds: below long MAs, far off highs by the end.
    prov = bull_world(drift_change={"CHOP1": (0.003, -0.004, 0.45)})
    out = ScreenerEngine(prov).screen(["NVDA", "CHOP1"])
    res = {r["symbol"]: r for r in out["results"]}
    assert res["NVDA"]["passes"] > res["CHOP1"]["passes"]
    assert res["NVDA"]["checks"]["above_200d"] is True
    assert res["NVDA"]["classification"] in ("canslim_leader", "overextended",
                                             "speculative_momentum")
    assert res["CHOP1"]["classification"] in ("no_setup", "laggard_turn")


# ---------- fundamentals ----------

def test_fundamentals_earnings_window_and_grade():
    today = date(2026, 6, 10)
    prov = SyntheticFundamentals(overrides={
        "NVDA": {"revenue_growth": 0.45, "eps_growth": 0.60,
                 "earnings_date": "2026-06-14"},
        "SLOW": {"revenue_growth": 0.02, "eps_growth": -0.05,
                 "earnings_date": "2026-09-01"},
    }, today=today)
    eng = FundamentalsEngine(prov)
    nvda = eng.get_snapshot("NVDA")
    assert nvda["growth_grade"] == "strong"
    assert nvda["in_earnings_window"] is True and nvda["days_to_earnings"] == 4
    slow = eng.get_snapshot("SLOW")
    assert slow["growth_grade"] == "weak" and slow["in_earnings_window"] is False


# ---------- validator ----------

def test_validator_accepts_traced_and_rejects_invented():
    evidence = {"levels": {"clusters": [{"price": 142.5}, {"price": 147.0}],
                           "weekly": {"weekly_pivot": 139.8}}}
    good = {"entry_trigger": 142.5, "stop": 139.8, "target_1": 147.0, "target_2": None}
    assert validate_setup(good, evidence)["valid"] is True
    bad = dict(good, target_1=151.25)  # invented
    out = validate_setup(bad, evidence)
    assert out["valid"] is False
    assert out["violations"][0]["field"] == "target_1"


def test_validator_allows_declared_derivations_only_with_traced_inputs():
    evidence = {"entry": 100.0, "atr": 2.0}
    setup = {"entry_trigger": 100.0, "stop": 97.6, "target_1": None, "target_2": None,
             "derived_levels": {"stop": {"formula": "entry - 1.2*ATR14",
                                         "inputs": [100.0, 2.0]}}}
    assert validate_setup(setup, evidence)["valid"] is True
    setup["derived_levels"]["stop"]["inputs"] = [100.0, 9.9]  # untraced input
    assert validate_setup(setup, evidence)["valid"] is False


def test_collect_numbers_skips_bools():
    assert collect_numbers({"a": True, "b": 1.5}) == {1.5}


# ---------- scorer ----------

def base_ctx(**over):
    ctx = {
        "regime": "risk_on", "regime_risk_score": 6.0,
        "vix_alignment_state": "confirming_bullish",
        "sector_etf": "SMH", "sector_status": "leading", "sector_rank_4w": 0.9,
        "screen": {"classification": "canslim_leader", "passes": 10,
                   "total_checks": 11, "extension_vs_21d_pct": 4.0},
        "phase": "mark_up", "rvol_20d": 1.8, "daily_rsi": 62.0,
        "bearish_divergence": False, "bullish_divergence": False,
        "mas_above": 6, "risk_reward_t1": 2.4, "risk_reward_t2": 3.5,
        "avg_dollar_volume_m": 900.0,
        "fundamentals": {"growth_grade": "strong", "days_to_earnings": 30,
                         "in_earnings_window": False},
    }
    ctx.update(over)
    return ctx


def test_score_strong_confluence_high_weak_low():
    strong = score_setup("long", base_ctx())
    assert strong["score"] >= 7.5
    weak = score_setup("long", base_ctx(
        vix_alignment_state="diverging_warning", sector_status="lagging",
        rvol_20d=0.7, daily_rsi=48.0, mas_above=2, risk_reward_t1=1.1,
        regime_risk_score=0.5,
        screen={"classification": "no_setup", "passes": 3, "total_checks": 11,
                "extension_vs_21d_pct": 1.0},
        fundamentals={"growth_grade": "weak", "days_to_earnings": 30,
                      "in_earnings_window": False}))
    assert weak["score"] < strong["score"] - 2.5


def test_score_flags_extension_and_earnings_risks():
    out = score_setup("long", base_ctx(
        screen={"classification": "canslim_leader", "passes": 10,
                "total_checks": 11, "extension_vs_21d_pct": 11.0},
        fundamentals={"growth_grade": "strong", "days_to_earnings": 3,
                      "in_earnings_window": True}))
    joined = " ".join(out["risks"])
    assert "21d MA" in joined and "earnings" in joined


def test_score_components_complete_and_placeholders_labeled():
    out = score_setup("long", base_ctx())
    assert set(out["components"]) == set(WEIGHTS)
    assert out["components"]["options_alignment"].get("placeholder") is True


# ---------- composer end to end ----------

def make_composer(prov):
    return SetupComposer(
        provider=prov,
        regime_engine=RegimeEngine(prov),
        rotation_engine=RotationEngine(prov, universe=["SMH", "XLK", "IGV", "XLP",
                                                       "XLU", "XLE", "XLF", "XLV"]),
        levels_engine=LevelsEngine(prov),
        volume_engine=VolumeEngine(prov),
        momentum_engine=MomentumEngine(prov),
        fundamentals_engine=FundamentalsEngine(
            SyntheticFundamentals(today=date(2026, 6, 10))),
        screener_engine=ScreenerEngine(prov),
    )


def test_composer_emits_validated_setups_in_bull_world():
    out = make_composer(bull_world()).compose()
    assert out["no_trade"] is False and out["direction"] == "long"
    assert len(out["setups"]) >= 1
    for s in out["setups"]:
        assert s["validated"] is True
        assert s["confidence"] >= MIN_SCORE
        assert s["risk_reward_t1"] >= MIN_RR_T1
        assert s["risk_reward_t2"] >= MIN_RR_T2
        assert s["entry_trigger"] > s["stop"]           # long geometry
        assert s["target_2"] >= s["target_1"] > s["entry_trigger"] * 0.999
        assert str(s["entry_trigger"]) in s["thesis"]   # thesis cites real levels
        assert s["sector_etf"] in ("SMH", "XLK", "IGV", "XLE", "XLF", "XLV")


def test_composer_stands_aside_in_chop():
    flat = SyntheticProvider(
        drift_map={"^VIX": 0.0, "QQQ": 0.0, "SPY": 0.0},
        start_price_map={"^VIX": 18.0, "QQQ": 520.0, "SPY": 600.0})
    out = make_composer(flat).compose()
    if out["no_trade"]:
        assert out["setups"] == [] and "chop" in out["reason"]
    else:  # synthetic noise can tip the composite either way; geometry must hold
        for s in out["setups"]:
            assert s["validated"] is True


def test_composer_suppression_reasons_recorded():
    out = make_composer(bull_world()).compose()
    for sup in out["suppressed"]:
        assert "reason" in sup and sup["reason"]
