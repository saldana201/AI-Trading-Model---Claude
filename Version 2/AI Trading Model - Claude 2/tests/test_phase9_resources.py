"""Phase 9 tests: API key auth + resource-style CRUD routers.

Conventions under test (the Refine 'simple REST' dialect):
_start/_end pagination, _sort/_order sorting, field=value equality filters,
X-Total-Count on list responses.
"""

import json
import os

import pytest

os.environ["CONFLUENCE_DATA"] = "synthetic"

from fastapi.testclient import TestClient


@pytest.fixture()
def env(tmp_path, monkeypatch):
    """Isolated env per test: API key on, watchlist in a temp file."""
    wl = tmp_path / "watchlist.json"
    wl.write_text(json.dumps({"SMH": ["NVDA", "AVGO"], "IGV": ["CRM"]}))
    monkeypatch.setenv("CONFLUENCE_API_KEY", "test-secret")
    monkeypatch.setenv("CONFLUENCE_WATCHLIST", str(wl))
    return wl


@pytest.fixture()
def client(env):
    from apps.api import main as gateway
    return TestClient(gateway.app)


H = {"X-API-Key": "test-secret"}


# ---------- auth ----------

def test_health_open_and_reports_auth(client):
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json()["auth"] == "api_key"


def test_protected_routes_401_without_key(client):
    assert client.get("/api/resources/trades").status_code == 401
    assert client.post("/api/chat", json={"message": "hi"}).status_code == 401
    assert client.post("/api/alerts/arm").status_code == 401


def test_bearer_and_header_both_accepted(client):
    assert client.get("/api/resources/trades", headers=H).status_code == 200
    assert client.get("/api/resources/trades", headers={
        "Authorization": "Bearer test-secret"}).status_code == 200


def test_wrong_key_rejected(client):
    r = client.get("/api/resources/trades", headers={"X-API-Key": "nope"})
    assert r.status_code == 401


# ---------- trades / events ----------

@pytest.fixture()
def armed(client):
    assert client.get("/api/snapshot").status_code == 200
    r = client.post("/api/alerts/arm", headers=H)
    assert r.status_code == 200
    return r.json()["armed"]


def test_trades_list_paginates_with_total(client, armed):
    r = client.get("/api/resources/trades?_start=0&_end=2", headers=H)
    assert r.status_code == 200
    assert len(r.json()) <= 2
    # >= not ==: earlier test modules may have armed trades into the same
    # in-process store; the count is the store's, not this arm call's
    assert int(r.headers["x-total-count"]) >= armed


def test_trades_sort_and_filter(client, armed):
    r = client.get("/api/resources/trades?_sort=symbol&_order=asc", headers=H)
    syms = [t["symbol"] for t in r.json()]
    assert syms == sorted(syms)
    if syms:
        r = client.get(f"/api/resources/trades?symbol={syms[0]}", headers=H)
        assert all(t["symbol"] == syms[0] for t in r.json())


def test_trade_patch_terminal_only_and_audited(client, armed):
    rows = client.get("/api/resources/trades", headers=H).json()
    if not rows:
        pytest.skip("no setups armed in this synthetic run")
    tid = rows[0]["id"]
    # non-terminal transition is the engine's job, not the API's
    r = client.patch(f"/api/resources/trades/{tid}",
                     json={"state": "ACTIVE"}, headers=H)
    assert r.status_code == 422
    r = client.patch(f"/api/resources/trades/{tid}",
                     json={"state": "CLOSED", "note": "manual"}, headers=H)
    assert r.status_code == 200 and r.json()["state"] == "CLOSED"
    events = client.get(
        f"/api/resources/events?trade_id={tid}", headers=H).json()
    assert any(e.get("type") == "manual_update" for e in events)


def test_trade_missing_404(client):
    assert client.get(
        "/api/resources/trades/doesnotexist", headers=H).status_code == 404


# ---------- watchlist ----------

def test_watchlist_crud_round_trip(client, env):
    r = client.get("/api/resources/watchlist", headers=H)
    assert r.status_code == 200 and int(r.headers["x-total-count"]) == 2

    r = client.post("/api/resources/watchlist", headers=H,
                    json={"sector_etf": "xbi", "tickers": ["vrtx", "REGN", "vrtx"]})
    assert r.status_code == 201
    assert r.json()["tickers"] == ["VRTX", "REGN"]   # upper-cased, deduped

    assert client.post("/api/resources/watchlist", headers=H,
                       json={"sector_etf": "XBI", "tickers": ["X"]}
                       ).status_code == 409

    r = client.put("/api/resources/watchlist/XBI", headers=H,
                   json={"tickers": ["VRTX", "AMGN"]})
    assert r.status_code == 200

    assert client.put("/api/resources/watchlist/XBI", headers=H,
                      json={"tickers": ["DROP TABLE"]}).status_code == 422

    assert client.delete(
        "/api/resources/watchlist/XBI", headers=H).status_code == 200
    disk = json.loads(env.read_text())
    assert "XBI" not in disk and "SMH" in disk


def test_watchlist_delete_missing_404(client):
    assert client.delete(
        "/api/resources/watchlist/ZZZZ", headers=H).status_code == 404
