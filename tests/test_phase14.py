"""Phase 14 tests — universe explorer.

The contract under test: every watchlist ticker gets the full card
treatment with gates REPORTED rather than silently filtering, compose()
behavior is completely untouched, and no card is ever invented when the
levels engine has nothing.
"""

from __future__ import annotations

import os
import pathlib

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("CONFLUENCE_DATA", "synthetic")

REPO = pathlib.Path(__file__).resolve().parents[1]

GATE_NAMES = {"regime", "sector_rotation", "screen_class", "risk_reward",
              "confidence", "evidence_validation"}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("CONFLUENCE_DATA", "synthetic")
    monkeypatch.delenv("CONFLUENCE_API_KEY", raising=False)
    from apps.api.main import app
    return TestClient(app)


def _composer(client):
    from apps.api.main import get_state
    return get_state()["toolbox"].composer


# ---------------- universe ----------------

def test_universe_lists_every_watchlist_sector(client):
    comp = _composer(client)
    u = comp.explore_universe()
    listed = {s["etf"] for s in u["sectors"]}
    assert set(comp.watchlist) <= listed          # nothing hidden
    assert u["direction"] in ("long", "short")
    # pinned flags surface on the tickers
    flat = {t["symbol"]: t for s in u["sectors"] for t in s["tickers"]}
    for sym in comp.pinned:
        if sym in flat:
            assert flat[sym]["pinned"] is True


def test_universe_shows_sectors_without_watchlist_entries(client):
    u = _composer(client).explore_universe()
    # rotation-tracked ETFs with no names still appear, tickers empty —
    # the gap must be visible, not invisible
    empties = [s for s in u["sectors"] if not s["tickers"]]
    for s in empties:
        assert s["etf"] not in _composer(client).watchlist or \
            _composer(client).watchlist.get(s["etf"]) == []


# ---------------- per-ticker cards ----------------

def test_explore_reports_every_gate(client):
    comp = _composer(client)
    sym = next(iter(next(iter(comp.watchlist.values()))))
    r = comp.explore(sym)
    names = {g["name"] for g in r["gates"]}
    if r["card"] is None:
        # honest refusal path: gates evaluated up to the construction stop
        assert "error" in r and "level structure" in r["error"]
    else:
        assert names == GATE_NAMES
        assert isinstance(r["in_composed"], bool)
        # the card has the same fields the composed setups carry
        for k in ("entry_trigger", "stop", "target_1", "target_2",
                  "risk_reward_t1", "confidence", "thesis", "invalidation"):
            assert k in r["card"], k
        assert r["card"]["exploratory"] is True


def test_explore_direction_override(client):
    comp = _composer(client)
    sym = next(iter(next(iter(comp.watchlist.values()))))
    long = comp.explore(sym, direction="long")
    short = comp.explore(sym, direction="short")
    if long["card"] and short["card"]:
        # a long entry sits above its stop; a short entry below its stop
        assert long["card"]["entry_trigger"] > long["card"]["stop"]
        assert short["card"]["entry_trigger"] < short["card"]["stop"]


def test_in_composed_agrees_with_compose(client):
    """A ticker explore() says passes every gate must actually appear in
    compose() output — the two views must not contradict each other."""
    comp = _composer(client)
    out = comp.compose()
    composed = {s["symbol"] for s in out.get("setups", [])}
    for sym in list(composed)[:2]:                # spot-check, keep it fast
        r = comp.explore(sym)
        assert r["card"] is not None
        assert r["in_composed"] is True, \
            f"{sym} is composed but explore() reports a failed gate: " \
            f"{[g for g in r['gates'] if not g['passed']]}"


def test_pinned_bypasses_rotation_gate_only(client):
    comp = _composer(client)
    if not comp.pinned:
        pytest.skip("no pinned tickers configured")
    r = comp.explore(comp.pinned[0])
    if r["card"] is None:
        pytest.skip("no level structure for pinned symbol in this world")
    rot = next(g for g in r["gates"] if g["name"] == "sector_rotation")
    # the gate is still REPORTED; only in_composed excuses it for pinned
    assert "pinned bypasses" in rot["detail"] or rot["passed"]


def test_compose_is_untouched_by_explorer(client):
    """explore() must have zero effect on the gated pipeline."""
    comp = _composer(client)
    before = comp.compose()
    sym = next(iter(next(iter(comp.watchlist.values()))))
    comp.explore(sym)
    comp.explore_universe()
    after = comp.compose()
    assert [s["symbol"] for s in before.get("setups", [])] == \
           [s["symbol"] for s in after.get("setups", [])]
    assert before.get("no_trade") == after.get("no_trade")


# ---------------- API ----------------

def test_api_explore_universe(client):
    r = client.get("/api/explore")
    assert r.status_code == 200
    body = r.json()
    assert body["sectors"] and "direction" in body
    # cache: second call returns the same payload
    assert client.get("/api/explore").json() == body


def test_api_explore_symbol_and_direction(client):
    from apps.api.main import get_state
    comp = get_state()["toolbox"].composer
    sym = next(iter(next(iter(comp.watchlist.values()))))
    r = client.get(f"/api/explore/{sym.lower()}")     # case-insensitive
    assert r.status_code == 200
    assert r.json()["symbol"] == sym
    r2 = client.get(f"/api/explore/{sym}", params={"direction": "short"})
    assert r2.status_code == 200
    assert r2.json()["direction"] == "short"


def test_api_explore_engine_failure_is_honest(client, monkeypatch):
    """In synthetic mode every symbol gets deterministic bars by design,
    so the refusal path is exercised by making the engine fail the way it
    would live (unknown ticker -> provider raises). The contract: a clean
    422, never a fabricated card."""
    from apps.api.main import get_state
    comp = get_state()["toolbox"].composer

    def boom(sym):
        raise ValueError(f"no data for {sym}")

    monkeypatch.setattr(comp.levels, "get_levels", boom)
    r = client.get("/api/explore/FAILME", params={"refresh": 1})
    assert r.status_code == 422
    assert "FAILME" in r.json()["detail"]


# ---------------- wiring ----------------

def test_explorer_panel_wired():
    page = (REPO / "apps/web/app/page.jsx").read_text()
    assert 'components/Explorer"' in page
    assert "<Explorer />" in page
    assert (REPO / "apps/web/components/Explorer.jsx").exists()
