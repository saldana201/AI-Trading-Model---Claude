"""Phase 9 tests: outcome journal, restart re-arming, /api/journal."""

from alerts.journal import trade_outcome, build_journal
from alerts.lifecycle import Trade, step
from alerts.store import Store


def drive(closes, store=None, **over):
    base = dict(symbol="T", direction="long", entry_trigger=100.0, stop=96.0,
                target_1=106.0, target_2=112.0, trail_distance=3.0)
    base.update(over)
    tr = Trade(**base)
    store = store or Store()
    store.save_trade(tr.to_dict())
    for i, c in enumerate(closes):
        for e in step(tr, {"close": c, "high": c + 0.5, "low": c - 0.5,
                           "time": f"2026-06-{10 + i:02d}", "rvol": 2.0}):
            store.save_event(e)
    store.save_trade(tr.to_dict())
    return tr, store


# ---------- per-trade outcome math ----------

def test_journal_winner_matches_backtest_semantics():
    tr, store = drive([101, 102, 107, 113])     # trim at 106, close at T2
    row = trade_outcome(tr.to_dict(), store.events(tr.id))
    assert row["status"] == "closed" and row["final_state"] == "CLOSED"
    assert row["realized_r"] == round((0.5 * 5 + 0.5 * 12) / 5, 3)   # 1.7
    assert row["opened_at"] and row["closed_at"]


def test_journal_open_trade_marked_to_quote():
    tr, store = drive([101, 103])                # ACTIVE, still open
    row = trade_outcome(tr.to_dict(), store.events(tr.id), mark_price=105.0)
    assert row["status"] == "open" and row["final_state"] == "OPEN"
    assert row["realized_r"] == round((105.0 - 101) / 5, 3)
    # without a quote, the water mark is the conservative proxy
    row2 = trade_outcome(tr.to_dict(), store.events(tr.id))
    assert row2["exit_or_mark"] == tr.water_mark


def test_journal_pending_and_no_fill():
    tr, store = drive([98, 99])                  # never triggered
    row = trade_outcome(tr.to_dict(), store.events(tr.id))
    assert row["status"] == "pending" and row["realized_r"] is None

    tr2, store2 = drive([101, 95, 101, 95])      # failed twice -> INVALIDATED
    row2 = trade_outcome(tr2.to_dict(), store2.events(tr2.id))
    assert row2["status"] == "no_fill"


def test_journal_deteriorated_counts_as_closed():
    tr, store = drive([101, 102])
    guard = lambda d: (True, {"vix_spot": 21.0, "vix_pivot": 19.0,
                              "index_spot": 500.0, "index_weekly_pivot": 510.0})
    for e in step(tr, {"close": 103, "high": 103.5, "low": 102.5,
                       "time": "2026-06-13", "rvol": 2.0}, market_guard=guard):
        store.save_event(e)
    store.save_trade(tr.to_dict())
    row = trade_outcome(tr.to_dict(), store.events(tr.id))
    assert row["final_state"] == "DETERIORATED" and row["status"] == "closed"
    assert row["realized_r"] is not None


# ---------- aggregate journal ----------

def test_build_journal_summary_and_counts():
    store = Store()
    drive([101, 102, 107, 113], store=store)                       # winner
    drive([101, 102, 95], store=store, symbol="L")                 # stopped
    drive([98, 99], store=store, symbol="P")                       # pending
    out = build_journal(store, mark_fn=lambda s: 100.0)
    assert out["counts"] == {"closed": 2, "pending": 1}
    assert out["summary"]["overall"]["n"] == 2
    assert out["summary"]["overall"]["win_rate"] == 0.5
    assert len(out["rows"]) == 3
    assert "outcomes" not in out["summary"]      # rows carry the detail


def test_build_journal_mark_fn_failure_degrades():
    store = Store()
    drive([101, 103], store=store)               # open trade
    def boom(symbol):
        raise RuntimeError("quote feed down")
    out = build_journal(store, mark_fn=boom)
    row = out["rows"][0]
    assert row["status"] == "open" and row["realized_r"] is not None  # water mark


# ---------- restart re-arming + gateway endpoint ----------

def test_live_alerts_rearm_from_store(tmp_path):
    from apps.api.live import LiveAlerts, Broadcaster
    from engines.shared.providers import SyntheticProvider
    from engines.levels_mcp.logic import LevelsEngine
    from engines.vix_mcp.logic import VixEngine

    db = str(tmp_path / "alerts.db")
    prov = SyntheticProvider()
    tr, _ = drive([98], store=Store(db),
                  setup_meta={"data_source": "synthetic"})  # tagged: re-armable
    live = LiveAlerts(prov, LevelsEngine(prov), VixEngine(prov),
                      Broadcaster(), db_path=db, data_source="synthetic")
    assert tr.id in live.engine.trades           # survived the "restart"
    assert live.engine.trades[tr.id].state == "WATCHING"


def test_journal_endpoint(client_module=None):
    import os
    os.environ["CONFLUENCE_DATA"] = "synthetic"
    from fastapi.testclient import TestClient
    from apps.api import main as gateway
    client = TestClient(gateway.app)
    client.post("/api/alerts/arm")
    out = client.get("/api/journal").json()
    assert set(out) == {"rows", "summary", "counts"}
    assert sum(out["counts"].values()) == len(out["rows"]) >= 1
    for r in out["rows"]:
        assert r["status"] in ("pending", "open", "closed", "no_fill")


def test_rearm_skips_mismatched_data_source(tmp_path):
    from apps.api.live import LiveAlerts, Broadcaster
    from engines.shared.providers import SyntheticProvider
    from engines.levels_mcp.logic import LevelsEngine
    from engines.vix_mcp.logic import VixEngine

    db = str(tmp_path / "alerts.db")
    store = Store(db)
    tr, _ = drive([98], store=store)                          # legacy: no source
    tr2 = Trade(symbol="S", direction="long", entry_trigger=100, stop=96,
                target_1=106, target_2=112, trail_distance=3,
                setup_meta={"data_source": "yfinance"})
    store.save_trade(tr2.to_dict())
    tr3 = Trade(symbol="OK", direction="long", entry_trigger=100, stop=96,
                target_1=106, target_2=112, trail_distance=3,
                setup_meta={"data_source": "synthetic"})
    store.save_trade(tr3.to_dict())

    prov = SyntheticProvider()
    live = LiveAlerts(prov, LevelsEngine(prov), VixEngine(prov), Broadcaster(),
                      db_path=db, data_source="synthetic")
    assert tr3.id in live.engine.trades            # matching source re-armed
    assert tr.id not in live.engine.trades         # legacy (no tag) skipped
    assert tr2.id not in live.engine.trades        # other world skipped


def test_arm_tags_trades_with_data_source(tmp_path):
    from apps.api.live import LiveAlerts, Broadcaster
    from engines.shared.providers import SyntheticProvider
    from engines.levels_mcp.logic import LevelsEngine
    from engines.vix_mcp.logic import VixEngine
    from tests.test_phase3 import bull_world, make_composer

    prov = bull_world()
    plan = make_composer(prov).compose()
    live = LiveAlerts(prov, LevelsEngine(prov), VixEngine(prov), Broadcaster(),
                      db_path=str(tmp_path / "a.db"), data_source="synthetic")
    live.arm(plan)
    stored = live.engine.store.load_trades(active_only=True)
    assert stored and all(
        t["setup_meta"]["data_source"] == "synthetic" for t in stored)


def test_compose_exposes_funnel():
    from tests.test_phase3 import bull_world, make_composer
    out = make_composer(bull_world()).compose()
    f = out["funnel"]
    assert f["candidate_stocks"] >= 1
    assert f["passed_screen"] <= f["candidate_stocks"]
    assert set(f["kept_classes"]) == {"canslim_leader", "laggard_turn"}
    assert isinstance(f["screen_classifications"], dict)
