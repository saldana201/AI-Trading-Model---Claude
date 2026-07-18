"""Phase 12 tests — unified config + trade assistant.

Conventions follow the existing suite: synthetic data, no network,
`>=` for shared-state count assertions.
"""

from __future__ import annotations

import json
import os

import pytest

os.environ.setdefault("CONFLUENCE_DATA", "synthetic")

from config import (DEFAULTS, get_config, update_config, reset_cache,
                    validate, list_presets, get_preset)
from config import loader as config_loader
from assistant import size_position, build_plan, advise, record_fill
from alerts.lifecycle import Trade, WATCHING, ACTIVE, TRAILING


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    """Every test gets its own config file and a clean cache."""
    path = tmp_path / "confluence.json"
    monkeypatch.setenv("CONFLUENCE_CONFIG", str(path))
    for var in ("CONFLUENCE_MIN_SCORE", "CONFLUENCE_MIN_RR_T1",
                "CONFLUENCE_MIN_RR_T2", "CONFLUENCE_FORCE_DIRECTION"):
        monkeypatch.delenv(var, raising=False)
    reset_cache()
    yield path
    reset_cache()
    # the gateway holds a module-level state singleton with a cached snapshot;
    # a snapshot composed under this test's config must not leak into later
    # phases that share the singleton — drop it so it recomposes clean.
    import sys
    gw = sys.modules.get("apps.api.main")
    if gw is not None:
        try:
            st = gw.get_state()
            st["snapshot"] = None
            st["snapshot_at"] = 0.0
        except Exception:
            pass


# ---------------- config layering ----------------

def test_defaults_match_historical_constants():
    cfg = get_config()
    assert cfg["risk"]["min_score"] == 6.0
    assert cfg["risk"]["min_rr_t1"] == 1.0
    assert cfg["risk"]["min_rr_t2"] == 2.0
    assert cfg["setup"]["entry_buffer_atr"] == 0.25
    assert cfg["setup"]["stop_atr"] == 1.2
    assert cfg["lifecycle"]["max_trigger_attempts"] == 2
    assert cfg["lifecycle"]["trail_atr"] == 1.5
    assert cfg["gates"]["chop_mode"] == "hard"


def test_env_overlay_still_honored(monkeypatch):
    monkeypatch.setenv("CONFLUENCE_MIN_SCORE", "7.5")
    reset_cache()
    assert get_config()["risk"]["min_score"] == 7.5


def test_file_beats_env(monkeypatch, isolated_config):
    monkeypatch.setenv("CONFLUENCE_MIN_SCORE", "7.5")
    isolated_config.write_text(json.dumps({"risk": {"min_score": 5.5}}))
    reset_cache()
    assert get_config()["risk"]["min_score"] == 5.5


def test_update_persists_and_audits(isolated_config):
    result = update_config({"risk": {"min_score": 6.5}})
    assert result["config"]["risk"]["min_score"] == 6.5
    assert result["event"]["type"] == "config_update"
    assert "risk.min_score" in result["event"]["changed"]
    on_disk = json.loads(isolated_config.read_text())
    assert on_disk["risk"]["min_score"] == 6.5
    reset_cache()  # survives a cold reload
    assert get_config()["risk"]["min_score"] == 6.5


def test_invalid_updates_rejected():
    with pytest.raises(ValueError):
        update_config({"risk": {"min_score": 42}})
    with pytest.raises(ValueError):
        update_config({"gates": {"chop_mode": "sometimes"}})
    with pytest.raises(ValueError):
        update_config({"setup": {"t2_atr": 0.5}})          # t2 <= t1
    with pytest.raises(ValueError):
        update_config({"risk": {"risk_per_trade_pct": 50}})  # unsafe
    with pytest.raises(ValueError):
        update_config({"riskk": {"min_score": 6.0}})       # typo section
    # a failed update must not corrupt the effective config
    assert get_config()["risk"]["min_score"] == 6.0


def test_corrupt_file_degrades_to_defaults(isolated_config):
    isolated_config.write_text("{not json")
    reset_cache()
    assert get_config()["risk"]["min_score"] == 6.0


def test_presets_are_valid_patches():
    for name in list_presets():
        assert validate(get_preset(name)) == []
    balanced = update_config(get_preset("balanced"))["config"]
    assert balanced["risk"]["min_score"] == DEFAULTS["risk"]["min_score"]
    aggressive = update_config(get_preset("aggressive"))["config"]
    assert aggressive["gates"]["chop_mode"] == "soft"
    assert aggressive["risk"]["min_score"] == 5.0


# ---------------- retrofits ----------------

def test_composer_module_constants_still_importable():
    from orchestrator import composer
    assert composer.MIN_SCORE == 6.0
    update_config({"risk": {"min_score": 7.0}})
    assert composer.MIN_SCORE == 7.0  # live, not frozen at import


def test_scoring_uses_config_weights():
    from orchestrator.scoring import score_setup
    ctx = _score_ctx()
    base = score_setup("long", ctx)["score"]
    # zero out a heavyweight component's weight — the score must move
    update_config({"scoring": {"weights": {"vix_alignment": 0.0}}})
    tweaked = score_setup("long", ctx)["score"]
    assert tweaked != base


def test_lifecycle_attempts_configurable():
    from alerts.lifecycle import step
    update_config({"lifecycle": {"max_trigger_attempts": 1}})
    t = _trade(min_rvol=0.0)                  # trigger needs rvol >= min
    step(t, _bar(101.5))                      # strictly beyond 101 -> TRIGGERED
    assert t.state == "TRIGGERED"
    events = step(t, _bar(99.0))              # fails to hold
    assert t.state == "INVALIDATED"           # one attempt only now
    assert any(e["to_state"] == "INVALIDATED" for e in events)


def test_trail_distance_from_config():
    from alerts.engine import arm_from_setup
    update_config({"lifecycle": {"trail_atr": 2.0}})
    trade = arm_from_setup(_setup(), atr14=2.0)
    assert trade.trail_distance == 4.0


def _chop_composer():
    from engines.shared.providers import SyntheticProvider
    from tests.test_phase3 import make_composer
    flat = SyntheticProvider(
        drift_map={"^VIX": 0.0, "QQQ": 0.0, "SPY": 0.0},
        start_price_map={"^VIX": 18.0, "QQQ": 520.0, "SPY": 600.0})
    composer = make_composer(flat)
    assert composer.regime.get_regime()["regime"] == "chop"  # precondition
    return composer


def test_hard_chop_mode_unchanged(monkeypatch):
    monkeypatch.setenv("CONFLUENCE_DATA", "synthetic")
    result = _chop_composer().compose()      # default gate is hard
    assert result["no_trade"] is True
    assert result["setups"] == []
    assert result.get("chop_gate") == "hard"


def test_soft_chop_mode_composes_with_warning(monkeypatch):
    monkeypatch.setenv("CONFLUENCE_DATA", "synthetic")
    update_config({"gates": {"chop_mode": "soft"}})
    result = _chop_composer().compose()
    assert result["no_trade"] is False
    assert result["chop_gate"] == "soft"
    assert "chop_warning" in result and "OVERRIDDEN" in result["chop_warning"]


def test_off_chop_mode_composes_silently(monkeypatch):
    monkeypatch.setenv("CONFLUENCE_DATA", "synthetic")
    update_config({"gates": {"chop_mode": "off"}})
    result = _chop_composer().compose()
    assert result["no_trade"] is False
    assert "chop_warning" not in result      # off = no warning, just trade


# ---------------- assistant: sizing ----------------

def test_sizing_math():
    update_config({"risk": {"account_size": 100000.0,
                            "risk_per_trade_pct": 1.0,
                            "max_position_pct": 100.0}})
    s = size_position(entry=50.0, stop=48.0)
    # $1000 risk budget / $2 per share = 500 shares
    assert s["shares"] == 500
    assert s["dollar_risk"] == 1000.0
    assert s["position_value"] == 25000.0
    assert not s["capped_by_position_limit"]
    assert s["evidence"]["inputs"]["entry"] == 50.0


def test_sizing_respects_position_cap():
    update_config({"risk": {"account_size": 100000.0,
                            "risk_per_trade_pct": 2.0,
                            "max_position_pct": 10.0}})
    s = size_position(entry=100.0, stop=99.0)   # uncapped would be 2000 sh
    assert s["shares"] == 100                    # 10% of 100k / $100
    assert s["capped_by_position_limit"]


def test_sizing_zero_risk_guard():
    assert size_position(50.0, 50.0)["shares"] == 0


# ---------------- assistant: plan ----------------

def test_plan_traces_and_reads():
    update_config({"risk": {"account_size": 100000.0,
                            "risk_per_trade_pct": 1.0}})
    plan = build_plan(_setup())
    assert plan["bracket"]["entry"] == 101.0
    assert plan["bracket"]["stop"] == 98.0
    qty = plan["sizing"]["shares"]
    assert plan["bracket"]["trim_quantity"] + plan["bracket"]["runner_quantity"] == qty
    assert "buy stop" in plan["steps"][0]["order"]
    assert str(101.0) in plan["text"] and str(98.0) in plan["text"]
    # every plan price came from the setup — nothing invented
    for p in (plan["bracket"]["entry"], plan["bracket"]["stop"],
              plan["bracket"]["target_1"], plan["bracket"]["target_2"]):
        assert p in (101.0, 98.0, 104.0, 107.0)


# ---------------- assistant: advisor ----------------

def test_advisor_wait_prestages_orders():
    rec = advise(_trade(), price=100.0)
    assert rec["action"] == "wait"
    assert "sizing" in rec
    assert rec["evidence"]["levels"]["entry_trigger"] == 101.0


def test_advisor_trigger_and_never_mutates():
    t = _trade()
    rec = advise(t, price=101.5)
    assert rec["action"] == "enter"
    assert t.state == WATCHING            # engine ownership preserved
    assert rec["evidence"]["lifecycle_events"]


def test_advisor_stop_hit_says_exit():
    t = _trade(state=ACTIVE, entry_price=101.0, stop_current=98.0,
               water_mark=101.0)
    rec = advise(t, price=97.0)
    assert rec["action"] == "exit"
    assert t.state == ACTIVE              # unchanged


def test_advisor_t1_says_trim():
    t = _trade(state=ACTIVE, entry_price=101.0, stop_current=98.0,
               water_mark=101.0)
    rec = advise(t, price=104.5)
    assert rec["action"] == "trim"
    assert "breakeven" in rec["instruction"]


def test_advisor_market_guard_exit():
    t = _trade(state=ACTIVE, entry_price=101.0, stop_current=98.0,
               water_mark=102.0)
    guard = lambda direction: (True, {"vix_spot": 25.0})  # noqa: E731
    rec = advise(t, price=102.0, market_guard=guard)
    assert rec["action"] == "exit"
    assert "guard" in rec["instruction"].lower()


def test_advisor_trailing_reports_effective_stop():
    t = _trade(state=TRAILING, entry_price=101.0, stop_current=101.0,
               water_mark=105.0, trail_distance=2.0)
    rec = advise(t, price=104.0)
    assert rec["action"] == "hold"
    assert rec["stop_current"] == 103.0   # 105 water mark - 2.0 trail


def test_record_fill_pre_entry_only():
    t = _trade()
    event = record_fill(t, price=101.2, shares=100)
    assert t.state == ACTIVE
    assert t.entry_price == 101.2
    assert event["reason"].startswith("manual_fill")
    with pytest.raises(ValueError):
        record_fill(t, price=102.0)       # already ACTIVE — engine-owned


# ---------------- API surface ----------------

def test_api_config_and_assistant_endpoints(monkeypatch):
    monkeypatch.setenv("CONFLUENCE_DATA", "synthetic")
    from fastapi.testclient import TestClient
    from apps.api.main import app
    client = TestClient(app)

    r = client.get("/api/config")
    assert r.status_code == 200 and r.json()["config"]["risk"]["min_score"] == 6.0

    r = client.put("/api/config", json={"patch": {"risk": {"min_score": 6.5}}})
    assert r.status_code == 200
    assert r.json()["config"]["risk"]["min_score"] == 6.5

    r = client.put("/api/config", json={"patch": {"risk": {"min_score": 99}}})
    assert r.status_code == 422

    r = client.get("/api/config/presets")
    assert r.status_code == 200 and "aggressive" in r.json()["presets"]

    r = client.post("/api/config/presets/conservative")
    assert r.status_code == 200
    assert r.json()["config"]["risk"]["min_score"] == 7.0
    assert client.post("/api/config/presets/yolo").status_code == 404

    r = client.post("/api/assistant/plan", json={"setup": _setup()})
    assert r.status_code == 200
    assert r.json()["bracket"]["entry"] == 101.0
    assert client.post("/api/assistant/plan",
                       json={"setup": {"symbol": "X"}}).status_code == 422

    assert client.get("/api/assistant/advise/nope").status_code == 404


def test_api_fill_and_advise_flow(monkeypatch):
    monkeypatch.setenv("CONFLUENCE_DATA", "synthetic")
    from fastapi.testclient import TestClient
    from apps.api.main import app, get_state
    client = TestClient(app)

    s = get_state()
    trade = _trade()
    s["live_alerts"].engine.trades[trade.id] = trade
    try:
        r = client.post("/api/assistant/fill",
                        json={"trade_id": trade.id, "price": 101.3, "shares": 50})
        assert r.status_code == 200
        assert r.json()["trade"]["state"] == "ACTIVE"

        # second fill on an active trade is refused — lifecycle stays engine-owned
        r = client.post("/api/assistant/fill",
                        json={"trade_id": trade.id, "price": 102.0})
        assert r.status_code == 409

        r = client.get(f"/api/assistant/advise/{trade.id}", params={"price": 97.0})
        assert r.status_code == 200
        assert r.json()["action"] == "exit"
    finally:
        # never leak this trade into the shared in-process engine state that
        # later phases assert against
        s["live_alerts"].engine.trades.pop(trade.id, None)


# ---------------- helpers ----------------

def _setup() -> dict:
    return {"symbol": "TEST", "direction": "long", "entry_trigger": 101.0,
            "stop": 98.0, "target_1": 104.0, "target_2": 107.0,
            "risk_reward_t1": 1.0, "risk_reward_t2": 2.0,
            "confidence": 7.0, "invalidation": "close below 21d MA"}


def _trade(**over) -> Trade:
    base = dict(symbol="TEST", direction="long", entry_trigger=101.0,
                stop=98.0, target_1=104.0, target_2=107.0,
                trail_distance=2.0, min_rvol=0.0)
    return Trade(**{**base, **over})


def _bar(price: float) -> dict:
    return {"close": price, "time": "2026-01-01", "rvol": 2.0}


def _score_ctx() -> dict:
    return {
        "regime": "risk_on", "regime_risk_score": 2.0,
        "vix_alignment_state": "confirming_bullish",
        "sector_etf": "SMH", "sector_status": "leading", "sector_rank_4w": 1,
        "screen": {"classification": "canslim_leader", "passes": 6,
                   "total_checks": 7, "relative_strength_vs_spy_pct": 8.0,
                   "extension_vs_21d_pct": 3.0},
        "phase": "markup", "rvol_20d": 1.5, "daily_rsi": 60.0,
        "bearish_divergence": False, "bullish_divergence": False,
        "mas_above": 3, "risk_reward_t1": 1.2, "risk_reward_t2": 2.4,
        "avg_dollar_volume_m": 500.0,
        "fundamentals": {"growth_grade": "strong", "days_to_earnings": 30,
                         "in_earnings_window": False},
    }
