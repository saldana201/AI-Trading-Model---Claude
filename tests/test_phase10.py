"""Phase 10 tests: pinned tickers, morning brief, auto-arm scheduler."""

import json
from datetime import datetime
from zoneinfo import ZoneInfo

from orchestrator.brief import render_brief
from orchestrator.composer import load_pinned, load_watchlist
from apps.api.live import maybe_autoarm
from tests.test_phase3 import bull_world, make_composer

ET = ZoneInfo("America/New_York")


# ---------- pinned tickers ----------

def test_load_pinned_and_watchlist_ignores_underscore_keys(tmp_path):
    cfg = tmp_path / "watchlist.json"
    cfg.write_text(json.dumps({"_pinned": ["tsla", "NVDA"],
                               "SMH": ["AMD"]}))
    assert load_pinned(str(cfg)) == ["TSLA", "NVDA"]
    wl = load_watchlist(str(cfg))
    assert "_PINNED" not in wl and "_pinned" not in wl
    assert wl["SMH"] == ["AMD"]
    assert load_pinned("does-not-exist.json") == []


def test_pinned_symbol_becomes_candidate_outside_active_sectors():
    composer = make_composer(bull_world())
    composer.pinned = ["ZZTOP"]          # unknown to every watchlist sector
    out = composer.compose()
    assert "ZZTOP" in out["funnel"]["pinned_candidates"]
    # known-sector candidates unaffected
    assert out["funnel"]["candidate_stocks"] > 1


def test_pinned_setup_carries_flag_and_pseudo_sector():
    prov = bull_world(extra_drift={"PINME": 0.0045})
    composer = make_composer(prov)
    composer.pinned = ["PINME"]
    out = composer.compose()
    pinned_rows = [s for s in out["setups"] if s["symbol"] == "PINME"]
    if pinned_rows:                       # if it cleared the quality gates
        s = pinned_rows[0]
        assert s["pinned"] is True
        assert s["sector_etf"] == "PINNED" and s["sector_status"] == "pinned"
        assert s["confidence"] >= 6.0     # gates were NOT bypassed
    # whether or not it set up, it must have been screened
    assert "PINME" in out["funnel"]["pinned_candidates"]


# ---------- morning brief ----------

def make_snapshot():
    composer = make_composer(bull_world())
    plan = composer.compose()
    return {
        "generated_at": "2026-06-12T08:30:00",
        "source": "synthetic",
        "regime": plan["regime"],
        "setups": plan,
        "vix": {"levels": {"spot": 14.2, "pivot": 15.1, "upside_target_1": 16.8,
                           "upside_target_2": 18.4, "downside_target_1": 13.0,
                           "downside_target_2": 12.1},
                "alignment": {"state": "confirming_bullish"}},
        "indices": {"QQQ": {"levels": {"spot": 530.0, "bullish_trigger": 534.2,
                                       "bearish_trigger": 521.0,
                                       "weekly": {"weekly_pivot": 528.0,
                                                  "weekly_ceiling": 537.0,
                                                  "weekly_floor": 519.0}}}},
        "rotation": {"etfs": [{"symbol": "SMH", "status": "leading"},
                              {"symbol": "XLV", "status": "improving"},
                              {"symbol": "XLP", "status": "lagging"}]},
        "options": {"QQQ": {"gamma_regime": "positive", "zero_gamma_flip": 525.0,
                            "call_wall": 540.0, "put_wall": 510.0}},
    }


def test_brief_contains_the_game_plan():
    snap = make_snapshot()
    md = render_brief(snap)
    assert "Confluence morning brief — 2026-06-12" in md
    assert "## Regime:" in md and "## VIX 14.20" in md
    assert "bull trigger 534.20" in md
    assert "leading: SMH" in md and "improving: XLV" in md
    assert "## Setups" in md
    for s in snap["setups"]["setups"]:
        assert s["symbol"] in md
    assert "not investment advice" in md


def test_brief_survives_partial_snapshot():
    md = render_brief({"generated_at": "2026-06-12", "source": "yfinance",
                       "setups": {"no_trade": True, "reason": "chop"}})
    assert "Standing aside." in md and "chop" in md


# ---------- auto-arm scheduler ----------

class FakeAlerts:
    def __init__(self):
        self.calls = 0

    def arm(self, plan):
        self.calls += 1
        return {"armed": 3}


def state_for_test():
    from apps.api.live import Broadcaster
    return {"live_alerts": FakeAlerts(), "broadcaster": Broadcaster(),
            "snapshot": None, "snapshot_at": 0.0}


def test_autoarm_fires_once_after_time(tmp_path):
    state = state_for_test()
    build = lambda: make_snapshot()
    early = datetime(2026, 6, 12, 7, 59, tzinfo=ET)
    assert maybe_autoarm(state, early, "08:30", build,
                         briefs_dir=str(tmp_path)) is None
    at_time = datetime(2026, 6, 12, 8, 31, tzinfo=ET)
    res = maybe_autoarm(state, at_time, "08:30", build, briefs_dir=str(tmp_path))
    assert res["armed"] == 3 and res["date"] == "2026-06-12"
    assert (tmp_path / "2026-06-12.md").exists()
    assert state["snapshot"] is not None
    # same day, later: no double-arm
    later = datetime(2026, 6, 12, 14, 0, tzinfo=ET)
    assert maybe_autoarm(state, later, "08:30", build,
                         briefs_dir=str(tmp_path)) is None
    assert state["live_alerts"].calls == 1
    # next day: fires again
    nxt = datetime(2026, 6, 15, 8, 35, tzinfo=ET)
    assert maybe_autoarm(state, nxt, "08:30", build,
                         briefs_dir=str(tmp_path))["date"] == "2026-06-15"


def test_autoarm_disabled_or_bad_time():
    state = state_for_test()
    now = datetime(2026, 6, 12, 9, 0, tzinfo=ET)
    assert maybe_autoarm(state, now, None, lambda: {}) is None
    assert maybe_autoarm(state, now, "nonsense", lambda: {}) is None
    assert state["live_alerts"].calls == 0


def test_health_surfaces_pinned_and_watchlist(tmp_path, monkeypatch):
    import json
    cfg = tmp_path / "watchlist.json"
    cfg.write_text(json.dumps({"_pinned": ["TSLA"], "SMH": ["NVDA"]}))
    monkeypatch.setenv("CONFLUENCE_WATCHLIST", str(cfg))
    from orchestrator.composer import load_pinned, load_watchlist
    assert load_pinned() == ["TSLA"]                 # env override resolves
    assert "SMH" in load_watchlist()


def test_resolve_searches_cwd_and_env(tmp_path, monkeypatch):
    import json
    from orchestrator.composer import _resolve_watchlist_path
    # env override
    f = tmp_path / "custom.json"
    f.write_text(json.dumps({"_pinned": []}))
    monkeypatch.setenv("CONFLUENCE_WATCHLIST", str(f))
    resolved, _ = _resolve_watchlist_path("watchlist.json")
    assert resolved == f
    monkeypatch.delenv("CONFLUENCE_WATCHLIST")
    # cwd
    monkeypatch.chdir(tmp_path)
    (tmp_path / "watchlist.json").write_text(json.dumps({"_pinned": ["X"]}))
    resolved2, _ = _resolve_watchlist_path("watchlist.json")
    assert resolved2 == tmp_path / "watchlist.json"


def test_pinned_outcomes_traces_every_pin():
    composer = make_composer(bull_world(extra_drift={"NVDA": 0.005}))
    composer.pinned = ["NVDA", "TSLA", "ZZNOPE"]
    out = composer.compose()
    outcomes = out["funnel"]["pinned_outcomes"]
    assert set(outcomes.keys()) == {"NVDA", "TSLA", "ZZNOPE"}
    # every pin has a disposition string; none silently vanish
    for sym, disp in outcomes.items():
        assert isinstance(disp, str) and disp
    # a pin that became a setup says so and carries the flag
    setups = {s["symbol"] for s in out["setups"] if s.get("pinned")}
    for sym in setups:
        assert outcomes[sym] == "setup"
    # suppressed pins carry pinned:True on their record
    for s in out["suppressed"]:
        if s["symbol"] in composer.pinned:
            assert s.get("pinned") is True


def test_pinned_screen_rejection_is_recorded():
    # a pinned name screening as no_setup must appear with a reason, not vanish
    composer = make_composer(bull_world())
    composer.pinned = ["XLP"]   # defensive ETF, unlikely canslim_leader in bull world
    out = composer.compose()
    assert "XLP" in out["funnel"]["pinned_outcomes"]
