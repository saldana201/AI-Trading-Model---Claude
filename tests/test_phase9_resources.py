"""Phase 9 tests — API key auth + headless resource REST."""

from __future__ import annotations

import json
import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("CONFLUENCE_DATA", "synthetic")

from alerts.lifecycle import Trade
from apps.api.resources.common import apply_filters, apply_sort, paginate


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("CONFLUENCE_DATA", "synthetic")
    monkeypatch.delenv("CONFLUENCE_API_KEY", raising=False)
    from apps.api.main import app
    return TestClient(app)


@pytest.fixture
def seeded(client):
    """One known trade in the shared store, removed afterwards."""
    from apps.api.main import get_state
    s = get_state()
    t = Trade(symbol="ZTEST", direction="long", entry_trigger=101.0,
              stop=98.0, target_1=104.0, target_2=107.0, trail_distance=2.0)
    s["live_alerts"].engine.trades[t.id] = t
    s["live_alerts"].engine.store.save_trade(t.to_dict())
    yield t
    s["live_alerts"].engine.trades.pop(t.id, None)


# ---------------- dialect ----------------

def test_filter_sort_paginate():
    rows = [{"id": "1", "symbol": "AAA", "n": 3},
            {"id": "2", "symbol": "BBB", "n": 1},
            {"id": "3", "symbol": "AAA", "n": 2}]
    assert len(apply_filters(rows, {"symbol": "AAA"})) == 2
    assert apply_filters(rows, {"_sort": "n"}) == rows      # reserved ignored
    assert apply_filters(rows, {"symbol": "NOPE"}) == []    # typo -> empty
    assert [r["n"] for r in apply_sort(rows, "n", "asc")] == [1, 2, 3]
    assert [r["n"] for r in apply_sort(rows, "n", "desc")] == [3, 2, 1]
    assert len(paginate(rows, 0, 2)) == 2
    assert paginate(rows, None, None) == rows


def test_sort_handles_missing_values():
    rows = [{"id": "1"}, {"id": "2", "n": 5}]
    assert apply_sort(rows, "n", "asc")[0]["id"] == "2"    # None sorts last


# ---------------- auth ----------------

def test_auth_disabled_by_default(client):
    assert client.get("/api/health").json()["auth"] == "disabled"
    assert client.get("/api/resources/trades").status_code == 200


def test_auth_enforced_when_key_set(monkeypatch):
    monkeypatch.setenv("CONFLUENCE_DATA", "synthetic")
    monkeypatch.setenv("CONFLUENCE_API_KEY", "s3cret")
    from apps.api.main import app
    c = TestClient(app)

    assert c.get("/api/health").json()["auth"] == "api_key"
    assert c.get("/api/resources/trades").status_code == 401
    assert c.get("/api/resources/trades",
                 headers={"X-API-Key": "wrong"}).status_code == 401
    assert c.get("/api/resources/trades",
                 headers={"X-API-Key": "s3cret"}).status_code == 200
    assert c.get("/api/resources/trades",
                 headers={"Authorization": "Bearer s3cret"}).status_code == 200
    # mutating gateway endpoints are protected too
    assert c.post("/api/alerts/arm").status_code == 401
    # reads stay open so the dashboard keeps working
    assert c.get("/api/snapshot").status_code == 200


# ---------------- trades ----------------

def test_trades_list_and_total_count(client, seeded):
    r = client.get("/api/resources/trades", params={"_start": 0, "_end": 100})
    assert r.status_code == 200
    assert "X-Total-Count" in r.headers
    assert any(t["symbol"] == "ZTEST" for t in r.json())


def test_trades_filter_and_get(client, seeded):
    r = client.get("/api/resources/trades", params={"symbol": "ZTEST"})
    assert all(t["symbol"] == "ZTEST" for t in r.json())
    assert client.get(f"/api/resources/trades/{seeded.id}").status_code == 200
    assert client.get("/api/resources/trades/nope").status_code == 404


def test_trades_patch_terminal_only(client, seeded):
    # non-terminal transitions are refused — engine owns the lifecycle
    r = client.patch(f"/api/resources/trades/{seeded.id}",
                     json={"state": "ACTIVE"})
    assert r.status_code == 422

    r = client.patch(f"/api/resources/trades/{seeded.id}",
                     json={"state": "CLOSED", "note": "manual close"})
    assert r.status_code == 200 and r.json()["state"] == "CLOSED"

    events = client.get("/api/resources/events",
                        params={"trade_id": seeded.id}).json()
    assert any(e["reason"].startswith("manual_update") for e in events)


def test_trades_has_no_delete(client, seeded):
    assert client.delete(f"/api/resources/trades/{seeded.id}").status_code == 405


# ---------------- events ----------------

def test_events_read_only(client):
    assert client.get("/api/resources/events").status_code == 200
    assert client.post("/api/resources/events", json={}).status_code == 405


# ---------------- watchlist ----------------

@pytest.fixture
def wl(tmp_path, monkeypatch, client):
    p = tmp_path / "watchlist.json"
    p.write_text(json.dumps({"_pinned": ["NVDA"], "SMH": ["AVGO", "AMD"]}))
    monkeypatch.setenv("CONFLUENCE_WATCHLIST", str(p))
    return p


def test_watchlist_lists_sectors_and_pinned(client, wl):
    rows = client.get("/api/resources/watchlist").json()
    by_id = {r["id"]: r for r in rows}
    assert by_id["PINNED"]["symbols"] == ["NVDA"]
    assert by_id["SMH"]["symbols"] == ["AVGO", "AMD"]


def test_watchlist_crud_roundtrip(client, wl):
    r = client.post("/api/resources/watchlist",
                    json={"id": "xlk", "symbols": ["msft", "aapl", "msft"]})
    assert r.status_code == 200
    assert r.json()["symbols"] == ["MSFT", "AAPL"]      # upper-cased + deduped
    assert "next snapshot" in r.json()["note"]

    assert client.post("/api/resources/watchlist",
                       json={"id": "XLK", "symbols": []}).status_code == 409

    r = client.patch("/api/resources/watchlist/XLK", json={"symbols": ["orcl"]})
    assert r.json()["symbols"] == ["ORCL"]

    assert client.delete("/api/resources/watchlist/XLK").status_code == 200
    assert client.get("/api/resources/watchlist/XLK").status_code == 404
    assert client.patch("/api/resources/watchlist/NOPE",
                        json={"symbols": []}).status_code == 404


def test_watchlist_rejects_bad_symbols(client, wl):
    r = client.patch("/api/resources/watchlist/SMH",
                     json={"symbols": ["OK", "bad symbol!"]})
    assert r.status_code == 422


def test_watchlist_pinned_is_editable(client, wl):
    r = client.patch("/api/resources/watchlist/PINNED",
                     json={"symbols": ["tsla", "nvda"]})
    assert r.json()["symbols"] == ["TSLA", "NVDA"]
    assert json.loads(wl.read_text())["_pinned"] == ["TSLA", "NVDA"]
