"""Phase 23 tests: pre-entry invalidation separated from the post-entry stop.

Ground truth showed 96% of NO_FILLs were "price hit the STOP side before entry"
— setups discarded by adverse movement that cost nothing, because there was no
position yet. The stop was doing double duty: exit-a-live-trade AND
abandon-a-pending-setup. These tests pin the three modes and, critically, that
the legacy default is unchanged.
"""

import pytest

from alerts.lifecycle import Trade, step, WATCHING, TRIGGERED, INVALIDATED
from alerts.engine import _preentry_invalidation, arm_from_setup
from config import update_config, reset_cache


def mk(direction="long", preentry=None):
    return Trade(symbol="AAA", direction=direction, entry_trigger=105.0,
                 stop=95.0, target_1=115.0, target_2=125.0,
                 trail_distance=2.0, min_rvol=0.0,
                 preentry_invalidation=preentry)


def bar(close, rvol=99.0):
    return {"close": close, "high": close + 0.5, "low": close - 0.5,
            "time": "2026-01-01", "rvol": rvol}


# ---------- legacy default is unchanged ----------

def test_default_none_falls_back_to_stop_legacy_behaviour():
    t = mk()                       # preentry_invalidation not set
    step(t, bar(94.0))             # below the stop
    assert t.state == INVALIDATED


def test_default_still_triggers_normally():
    t = mk()
    step(t, bar(106.0))
    assert t.state == TRIGGERED


# ---------- mode: none ----------

def test_none_mode_survives_adverse_move_then_triggers():
    """The whole point: a setup you are not in should not be discarded by a
    move that cost you nothing."""
    t = mk(preentry=float("-inf"))
    step(t, bar(90.0))             # would have invalidated under legacy
    assert t.state == WATCHING
    step(t, bar(106.0))            # later the trigger fires
    assert t.state == TRIGGERED


def test_none_mode_short_side():
    t = mk(direction="short", preentry=float("inf"))
    t.entry_trigger, t.stop = 95.0, 105.0
    step(t, bar(110.0))            # adverse for a short
    assert t.state == WATCHING
    step(t, bar(94.0))
    assert t.state == TRIGGERED


# ---------- mode: wide ----------

def test_wide_mode_tolerates_noise_but_still_abandons_on_decisive_move():
    t = mk(preentry=90.0)          # stop 95, invalidation 90
    step(t, bar(93.0))             # through the stop, not the invalidation
    assert t.state == WATCHING
    step(t, bar(89.0))             # decisively through
    assert t.state == INVALIDATED


# ---------- level computation from config ----------

def test_preentry_level_stop_mode_is_the_stop():
    reset_cache()
    update_config({"gates": {"preentry_invalidation": "stop"}}, persist=False)
    try:
        assert _preentry_invalidation("long", 95.0, 2.0) == 95.0
    finally:
        reset_cache()


def test_preentry_level_none_mode_is_infinite():
    reset_cache()
    update_config({"gates": {"preentry_invalidation": "none"}}, persist=False)
    try:
        assert _preentry_invalidation("long", 95.0, 2.0) == float("-inf")
        assert _preentry_invalidation("short", 105.0, 2.0) == float("inf")
    finally:
        reset_cache()


def test_preentry_level_wide_mode_pads_by_atr():
    reset_cache()
    update_config({"gates": {"preentry_invalidation": "wide",
                             "preentry_invalidation_atr": 1.5}}, persist=False)
    try:
        # long: stop pushed DOWN by 1.5 ATR
        assert _preentry_invalidation("long", 95.0, 2.0) == pytest.approx(92.0)
        # short: stop pushed UP
        assert _preentry_invalidation("short", 105.0, 2.0) == pytest.approx(108.0)
    finally:
        reset_cache()


def test_arm_from_setup_carries_the_level():
    reset_cache()
    update_config({"gates": {"preentry_invalidation": "none"}}, persist=False)
    try:
        t = arm_from_setup(
            {"symbol": "AAA", "direction": "long", "entry_trigger": 105.0,
             "stop": 95.0, "target_1": 115.0, "target_2": 125.0}, atr14=2.0)
        assert t.preentry_invalidation == float("-inf")
    finally:
        reset_cache()


# ---------- the stop still works AFTER entry in every mode ----------

def test_post_entry_stop_is_unaffected_by_none_mode():
    """Disabling pre-entry invalidation must NOT disable the real stop."""
    t = mk(preentry=float("-inf"))
    step(t, bar(106.0))            # trigger
    step(t, bar(106.5))            # hold -> ACTIVE
    assert t.state not in (WATCHING, INVALIDATED)
    step(t, bar(94.0))             # now genuinely stopped out
    assert t.state == "STOPPED"
