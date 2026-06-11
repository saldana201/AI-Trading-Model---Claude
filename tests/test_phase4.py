"""Phase 4 tests: lifecycle paths, predicates, market guard, store, engine."""

import numpy as np
import pandas as pd
import pytest

from alerts.lifecycle import (
    Trade, step, WATCHING, TRIGGERED, ACTIVE, TRAILING, CLOSED,
    INVALIDATED, STOPPED, DETERIORATED,
)
from alerts.predicates import AlertContext, evaluate
from alerts.store import Store
from alerts.engine import AlertEngine, market_guard_factory, arm_from_setup
from alerts.templates import render_event
from engines.shared.providers import (
    SyntheticProvider, ScriptedProvider, ReplayProvider, BarRequest,
)
from engines.levels_mcp.logic import LevelsEngine
from engines.vix_mcp.logic import VixEngine


def make_trade(**over):
    base = dict(symbol="NVDA", direction="long", entry_trigger=100.0, stop=96.0,
                target_1=106.0, target_2=112.0, trail_distance=3.0)
    base.update(over)
    return Trade(**base)


def bar(close, t=0, rvol=2.0):
    return {"close": close, "high": close + 0.5, "low": close - 0.5,
            "time": f"2026-06-{10+t:02d}", "rvol": rvol}


def run_path(trade, closes, guard=None):
    events = []
    for i, c in enumerate(closes):
        events += step(trade, bar(c, i), market_guard=guard)
    return events


# ---------- lifecycle paths ----------

def test_full_winning_path_to_target_2():
    tr = make_trade()
    ev = run_path(tr, [98, 101, 102, 107, 109, 113])
    states = [e["to_state"] for e in ev]
    assert states == [TRIGGERED, ACTIVE, "TRIMMED_T1", TRAILING, CLOSED]
    assert tr.state == CLOSED
    assert ev[-1]["reason"].startswith("target 2")
    assert tr.stop_current == tr.entry_price  # breakeven after trim


def test_stop_out_path():
    tr = make_trade()
    ev = run_path(tr, [101, 102, 95.0])
    assert [e["to_state"] for e in ev] == [TRIGGERED, ACTIVE, STOPPED]


def test_trailing_stop_exit_after_t1():
    tr = make_trade()
    # trigger, hold, hit T1, run to 110, then fade below 110-3=107
    ev = run_path(tr, [101, 102, 107, 110, 106.5])
    assert ev[-1]["to_state"] == CLOSED
    assert "trailing stop" in ev[-1]["reason"]


def test_breakeven_exit_after_t1():
    # Wide trail (8) from water 106.5 computes 98.5 -> clamped up to breakeven 101.
    tr = make_trade(trail_distance=8.0)
    ev = run_path(tr, [101, 102, 106.5, 100.0])
    assert ev[-1]["to_state"] == CLOSED
    assert "breakeven" in ev[-1]["reason"]


def test_failed_trigger_rearms_once_then_invalidates():
    tr = make_trade()
    ev = run_path(tr, [101, 99, 101, 99])  # break, fail, break, fail
    states = [e["to_state"] for e in ev]
    assert states == [TRIGGERED, WATCHING, TRIGGERED, INVALIDATED]


def test_pre_entry_invalidation_through_stop():
    tr = make_trade()
    ev = run_path(tr, [98, 95.0])
    assert [e["to_state"] for e in ev] == [INVALIDATED]


def test_low_rvol_does_not_trigger():
    tr = make_trade(min_rvol=1.5)
    ev = step(tr, bar(101, rvol=0.8))
    assert ev == [] and tr.state == WATCHING
    ev = step(tr, bar(101.5, rvol=2.0))
    assert ev[0]["to_state"] == TRIGGERED


def test_deterioration_fires_while_active():
    tr = make_trade()
    run_path(tr, [101, 102])           # ACTIVE
    guard = lambda d: (True, {"vix_spot": 21.0, "vix_pivot": 19.5,
                              "index_spot": 510.0, "index_weekly_pivot": 515.0})
    ev = step(tr, bar(103, 3), market_guard=guard)
    assert ev[0]["to_state"] == DETERIORATED
    assert "exit recommended" in ev[0]["reason"]
    assert step(tr, bar(120, 4)) == []  # terminal


def test_short_direction_mirrors():
    tr = make_trade(direction="short", entry_trigger=100.0, stop=104.0,
                    target_1=94.0, target_2=88.0)
    ev = run_path(tr, [99, 98, 93, 87])
    assert ev[-1]["to_state"] == CLOSED and tr.state == CLOSED


# ---------- predicates ----------

def synthetic_world():
    prov = SyntheticProvider(
        drift_map={"^VIX": -0.005, "QQQ": 0.0025, "SPY": 0.0015},
        start_price_map={"^VIX": 18.0, "QQQ": 520.0, "SPY": 600.0})
    return prov, LevelsEngine(prov), VixEngine(prov)


def test_predicate_tree_all_any_not():
    prov, levels, vix = synthetic_world()
    ctx = AlertContext(levels, vix)
    spot = levels.get_levels("QQQ")["spot"]
    fired, trail = evaluate({"all": [
        {"check": "price_above", "symbol": "QQQ", "level": spot - 1},
        {"any": [{"check": "vix_below_pivot"}, {"check": "vix_above_pivot"}]},
        {"not": {"check": "price_below", "symbol": "QQQ", "level": spot - 1}},
    ]}, ctx)
    assert fired is True
    assert all("check" in t for t in trail)
    fired, _ = evaluate({"check": "price_above", "symbol": "QQQ",
                         "level": spot + 1000}, ctx)
    assert fired is False


def test_predicate_unknown_check_raises():
    prov, levels, vix = synthetic_world()
    with pytest.raises(ValueError):
        evaluate({"check": "nope"}, AlertContext(levels, vix))


# ---------- store ----------

def test_store_roundtrip_and_active_filter():
    s = Store()
    t1 = make_trade().to_dict()
    t2 = make_trade(symbol="AMD").to_dict()
    t2["state"] = CLOSED
    s.save_trade(t1); s.save_trade(t2)
    assert {t["symbol"] for t in s.load_trades(active_only=True)} == {"NVDA"}
    assert len(s.load_trades(active_only=False)) == 2
    s.save_event({"trade_id": t1["id"], "to_state": ACTIVE, "x": 1})
    assert s.events(t1["id"])[0]["to_state"] == ACTIVE


# ---------- engine end to end on a scripted path ----------

def scripted_engine(closes_nvda, vix_path=None, qqq_path=None):
    """ScriptedProvider + ReplayProvider: NVDA walks `closes_nvda` while VIX/QQQ
    follow benign (or scripted) paths; the engine ticks bar by bar."""
    n = len(closes_nvda) + 60
    idx = pd.date_range("2026-03-02", periods=n, freq="B")

    def frame(path, base):
        closes = np.concatenate([np.full(n - len(path), base), np.asarray(path)])
        return pd.DataFrame({"open": closes, "high": closes + 0.6,
                             "low": closes - 0.6, "close": closes,
                             "volume": np.full(n, 1e6)}, index=idx)

    frames = {
        "NVDA": frame(closes_nvda, closes_nvda[0]),
        "^VIX": frame(vix_path or [15.0] * len(closes_nvda), 18.0),
        "QQQ": frame(qqq_path or [530.0] * len(closes_nvda), 520.0),
    }
    replay = ReplayProvider(ScriptedProvider(frames), start_offset=len(closes_nvda))
    levels = LevelsEngine(replay, lookback_days=80)
    vix = VixEngine(replay)
    return replay, AlertEngine(replay, levels, vix, store=Store())


def test_engine_drives_trade_through_lifecycle():
    closes = [98, 98, 101, 102, 107, 109, 113, 113]
    replay, engine = scripted_engine(closes)
    trade = make_trade()
    engine.trades[trade.id] = trade
    engine.store.save_trade(trade.to_dict())

    all_events = []
    for _ in range(len(closes)):
        all_events += engine.tick()
        replay.advance()
    states = [e["to_state"] for e in all_events]
    assert TRIGGERED in states and ACTIVE in states and CLOSED in states
    stored = engine.store.events(trade.id)
    assert len(stored) == len([e for e in all_events if e["trade_id"] == trade.id])


def test_arm_from_setup_and_render():
    setup = {"symbol": "NVDA", "direction": "long", "entry_trigger": 142.5,
             "stop": 139.8, "target_1": 147.0, "target_2": 151.0,
             "confidence": 7.8, "thesis": "Breaks 142.5 with sector leading.",
             "sector_etf": "SMH", "invalidation": "close below 21d MA"}
    trade = arm_from_setup(setup, atr14=2.0)
    assert trade.trail_distance == 3.0 and trade.state == WATCHING
    ev = step(trade, bar(143.0))
    msg = render_event(ev[0], trade.to_dict())
    assert "trigger fired" in msg and "142.5" in msg and "why:" in msg
