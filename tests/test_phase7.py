"""Phase 7 tests: provider caching, quotes, live alert arming, SSE stream."""

import asyncio
import os

import pytest

os.environ["CONFLUENCE_DATA"] = "synthetic"
os.environ["CONFLUENCE_SSE_KEEPALIVE"] = "0.2"

from fastapi.testclient import TestClient

from apps.api import main as gateway
from apps.api.live import Broadcaster, build_quotes
from engines.shared.providers import (
    CachedProvider, SyntheticProvider, BarRequest,
)


@pytest.fixture(scope="module")
def client():
    return TestClient(gateway.app)


# ---------- CachedProvider ----------

class CountingProvider:
    def __init__(self):
        self.calls = 0
        self.base = SyntheticProvider()

    def get_bars(self, req):
        self.calls += 1
        return self.base.get_bars(req)


def test_cache_hits_within_ttl_and_expires_after():
    clock = {"t": 1000.0}
    counting = CountingProvider()
    cp = CachedProvider(counting, ttl_s=60, clock=lambda: clock["t"])
    req = BarRequest("QQQ", "1d", 100)
    a = cp.get_bars(req)
    b = cp.get_bars(req)
    assert counting.calls == 1 and a is b          # served from cache
    cp.get_bars(BarRequest("QQQ", "1d", 50))       # different key -> miss
    assert counting.calls == 2
    clock["t"] += 61                                # TTL expiry
    cp.get_bars(req)
    assert counting.calls == 3
    cp.invalidate()
    cp.get_bars(req)
    assert counting.calls == 4


# ---------- quotes ----------

def test_build_quotes_shape_and_error_isolation():
    prov = SyntheticProvider(start_price_map={"QQQ": 100.0})

    class Flaky:
        def get_bars(self, req):
            if req.symbol == "BAD":
                raise RuntimeError("nope")
            return prov.get_bars(req)

    out = build_quotes(Flaky(), ["QQQ", "BAD"])
    assert "QQQ" in out["quotes"] and "BAD" in out["errors"]
    q = out["quotes"]["QQQ"]
    assert set(q) == {"spot", "change_pct", "rvol_20d", "bar_time"}


def test_quotes_endpoint(client):
    r = client.get("/api/quotes").json()
    assert {"QQQ", "SPY", "^VIX"} <= set(r["quotes"])
    r2 = client.get("/api/quotes", params={"symbols": "nvda"}).json()
    assert "NVDA" in r2["quotes"]


# ---------- live alerts ----------

def test_arm_tick_state_cycle(client):
    armed = client.post("/api/alerts/arm").json()
    assert armed["armed"] >= 1
    state = client.get("/api/alerts/state").json()
    assert len(state["trades"]) == armed["armed"]
    assert all(t["state"] == "WATCHING" for t in state["trades"])
    ticked = client.post("/api/alerts/tick").json()
    assert isinstance(ticked["events"], list)   # synthetic bars are static:
    state2 = client.get("/api/alerts/state").json()   # ticking must not crash
    assert len(state2["trades"]) == len(state["trades"])
    # ticker strip now follows armed names
    h = client.get("/api/quotes").json()
    assert len(h["quotes"]) > 3


# ---------- broadcaster + SSE ----------

def test_broadcaster_publish_and_slow_consumer_dropped():
    b = Broadcaster()

    async def run():
        q = b.subscribe()
        b.publish("quote", {"x": 1})
        msg = await q.get()
        assert msg.startswith("event: quote\n")
        assert '"x": 1' in msg
        # slow consumer: fill the queue past capacity -> dropped
        for _ in range(250):
            b.publish("quote", {"x": 2})
        assert q not in b.clients

    asyncio.run(run())


def test_stream_generator_hello_event_and_cleanup():
    """Exercise the real SSE generator directly: TestClient can't close an
    infinite stream (it drains forever), so we drive the async generator."""
    async def run():
        s = gateway.get_state()
        before = len(s["broadcaster"].clients)
        resp = await gateway.stream()
        assert resp.media_type == "text/event-stream"
        agen = resp.body_iterator
        first = await agen.__anext__()
        assert "event: hello" in first and "synthetic" in first
        assert len(s["broadcaster"].clients) == before + 1
        s["broadcaster"].publish("quote", {"x": 1})
        second = await agen.__anext__()
        assert second.startswith("event: quote") and '"x": 1' in second
        await agen.aclose()
        assert len(s["broadcaster"].clients) == before   # unsubscribed

    asyncio.run(run())


def test_health_still_ok_with_live_layer(client):
    r = client.get("/api/health").json()
    assert r["ok"] is True


def test_setups_arm_without_instant_invalidation():
    """The geometry guard: every composed setup must survive its first tick
    (stop on the correct side of spot), so arming never instantly kills a trade."""
    from tests.test_phase3 import bull_world, make_composer
    from alerts.engine import arm_from_setup
    from alerts.lifecycle import step, INVALIDATED
    from engines.shared.providers import BarRequest

    prov = bull_world()
    out = make_composer(prov).compose()
    assert len(out["setups"]) >= 1
    for s in out["setups"]:
        bars = prov.get_bars(BarRequest(s["symbol"], "1d", 40))
        spot = float(bars["close"].iloc[-1])
        if s["direction"] == "long":
            assert s["stop"] < spot
        trade = arm_from_setup(s, atr14=1.0)
        events = step(trade, {"close": spot, "high": spot, "low": spot,
                              "time": "t0", "rvol": 1.0})
        assert all(e["to_state"] != INVALIDATED for e in events)


def test_watchlist_json_merges_over_defaults(tmp_path):
    import json
    from orchestrator.composer import load_watchlist, DEFAULT_WATCHLIST
    cfg = tmp_path / "watchlist.json"
    cfg.write_text(json.dumps({"smh": ["nvda", "mrvl"], "XLY": ["TSLA"]}))
    wl = load_watchlist(path=str(cfg))
    assert wl["SMH"] == ["NVDA", "MRVL"]                    # replaced + uppercased
    assert wl["XLY"] == ["TSLA"]                            # new sector key
    assert wl["XLK"] == DEFAULT_WATCHLIST["XLK"]            # defaults intact
    assert load_watchlist("does-not-exist.json") is DEFAULT_WATCHLIST


def test_force_direction_bypasses_only_the_chop_gate(monkeypatch):
    from engines.shared.providers import SyntheticProvider
    from tests.test_phase3 import make_composer
    flat = SyntheticProvider(
        drift_map={"^VIX": 0.0, "QQQ": 0.0, "SPY": 0.0},
        start_price_map={"^VIX": 18.0, "QQQ": 520.0, "SPY": 600.0})
    composer = make_composer(flat)
    monkeypatch.setenv("CONFLUENCE_FORCE_DIRECTION", "long")
    out = composer.compose()
    assert out["no_trade"] is False and out["forced"] is True
    assert out["direction"] == "long"
    for s in out["setups"]:           # quality gates still apply when forced
        assert s["validated"] is True and s["confidence"] >= 6.0
    monkeypatch.delenv("CONFLUENCE_FORCE_DIRECTION")
    out2 = composer.compose()
    assert out2.get("forced") is False


def test_flip_ignores_far_otm_noise():
    from engines.options_mcp.providers import SyntheticOptions
    from engines.options_mcp.logic import gex_profile
    ch = SyntheticOptions().get_chain("TEST", 100.0)
    # inject huge put OI 55% below spot — must not drag the flip down there
    ch["contracts"].append({"expiry": ch["expiries"][2]["date"], "dte": 30,
                            "strike": 45.0, "type": "put", "iv": 0.9,
                            "oi": 500000, "volume": 1000,
                            "bid": 0.04, "mid": 0.05, "ask": 0.06})
    p = gex_profile(ch)
    assert p["zero_gamma_flip"] is not None
    assert abs(p["zero_gamma_flip"] - 100.0) / 100.0 <= 0.20
