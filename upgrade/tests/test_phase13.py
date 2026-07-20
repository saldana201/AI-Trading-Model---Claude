"""Phase 13 tests — assistant reachable from chat + panels wired."""

from __future__ import annotations

import os
import pathlib

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("CONFLUENCE_DATA", "synthetic")

from orchestrator.chat import EngineToolbox

REPO = pathlib.Path(__file__).resolve().parents[1]


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("CONFLUENCE_DATA", "synthetic")
    monkeypatch.delenv("CONFLUENCE_API_KEY", raising=False)
    from apps.api.main import app
    return TestClient(app)


def _first_setup_symbol(client) -> str | None:
    snap = client.get("/api/snapshot").json()
    setups = snap.get("setups", {}).get("setups", [])
    return setups[0]["symbol"] if setups else None


# ---------------- tool registration ----------------

def test_assistant_tools_are_registered():
    names = {s["name"] for s in EngineToolbox.SPECS}
    assert {"size_position", "get_trade_plan", "advise_open_trade"} <= names
    for spec in EngineToolbox.SPECS:
        assert spec["input_schema"]["type"] == "object"


def test_every_spec_has_an_implementation():
    for spec in EngineToolbox.SPECS:
        assert hasattr(EngineToolbox, f"tool_{spec['name']}"), spec["name"]


# ---------------- chat intents ----------------

def test_chat_answers_position_sizing(client):
    sym = _first_setup_symbol(client)
    if sym is None:
        pytest.skip("no composed setups in this synthetic regime")
    r = client.post("/api/chat",
                    json={"message": f"how many shares of {sym} should i buy"})
    body = r.json()
    assert "get_trade_plan" in body["tool_calls"]
    assert "shares" in body["reply"] and sym in body["reply"]


def test_chat_answers_trade_plan(client):
    sym = _first_setup_symbol(client)
    if sym is None:
        pytest.skip("no composed setups in this synthetic regime")
    body = client.post("/api/chat",
                       json={"message": f"what is my plan for {sym}"}).json()
    reply = body["reply"].lower()
    assert "stop" in reply and "trim" in reply


def test_chat_answers_exit_management(client):
    sym = _first_setup_symbol(client)
    if sym is None:
        pytest.skip("no composed setups in this synthetic regime")
    body = client.post(
        "/api/chat",
        json={"message": f"what do i do with my {sym} position"}).json()
    assert "advise_open_trade" in body["tool_calls"]
    # the action must be one of the lifecycle-derived instructions
    assert any(w in body["reply"] for w in
               ("HOLD", "EXIT", "TRIM", "WAIT", "ENTER", "CLOSE"))


def test_exit_intent_beats_generic_stop_branch(client):
    """'what do i do with my X position' must not fall into the old
    invalidation branch, which only quotes a stop level."""
    sym = _first_setup_symbol(client)
    if sym is None:
        pytest.skip("no composed setups in this synthetic regime")
    body = client.post(
        "/api/chat",
        json={"message": f"what do i do with my {sym} position"}).json()
    assert body["tool_calls"] != ["get_setups"]


def test_unknown_symbol_declines_instead_of_inventing(client):
    body = client.post(
        "/api/chat",
        json={"message": "what do i do with my ZZZZ position"}).json()
    reply = body["reply"].lower()
    assert "no composed setup" in reply or "no setup" in reply
    # must not fabricate levels
    assert "$" not in body["reply"]


# ---------------- toolbox units ----------------

def test_size_position_tool_math(client):
    from config import update_config
    update_config({"risk": {"account_size": 100000.0,
                            "risk_per_trade_pct": 1.0,
                            "max_position_pct": 100.0}}, persist=False)
    from apps.api.main import get_state
    tb = get_state()["chat"].toolbox
    out = tb.call("size_position", {"entry": 50.0, "stop": 48.0})
    assert out["shares"] == 500 and out["dollar_risk"] == 1000.0


def test_trade_plan_tool_reports_unknown_symbol(client):
    from apps.api.main import get_state
    tb = get_state()["chat"].toolbox
    out = tb.call("get_trade_plan", {"symbol": "ZZZZ"})
    assert "error" in out and "available" in out


# ---------------- UI wiring (the Phase 12 gap) ----------------

def test_panels_are_actually_rendered():
    page = (REPO / "apps/web/app/page.jsx").read_text()
    for component in ("Assistant", "Settings"):
        assert f'components/{component}"' in page, f"{component} not imported"
        assert f"<{component} />" in page, f"{component} imported but never rendered"


def test_panel_components_exist():
    for name in ("Assistant.jsx", "Settings.jsx"):
        assert (REPO / "apps/web/components" / name).exists()
