"""Phase 6 tests: API gateway, deterministic chat router, composite MCP server."""

import asyncio
import os

import pytest

os.environ["CONFLUENCE_DATA"] = "synthetic"   # before app state builds

from fastapi.testclient import TestClient

from apps.api import main as gateway
from orchestrator.chat import extract_symbols


@pytest.fixture(scope="module")
def client():
    return TestClient(gateway.app)


# ---------- symbol extraction ----------

def test_extract_symbols():
    assert extract_symbols("Is NVDA extended?") == ["NVDA"]
    assert extract_symbols("compare $amd and AVGO today") == ["AMD", "AVGO"]
    assert extract_symbols("What is the market regime today?") == []
    assert extract_symbols("are QQQ levels holding") == []   # index handled by intent


# ---------- gateway ----------

def test_health(client):
    r = client.get("/api/health").json()
    assert r["ok"] is True
    assert r["data_source"] == "synthetic"
    assert r["chat_mode"] in ("llm", "deterministic")


def test_snapshot_endpoint_shape_and_cache(client):
    r1 = client.get("/api/snapshot")
    assert r1.status_code == 200
    d = r1.json()
    for key in ("regime", "vix", "indices", "rotation", "setups", "options",
                "alert_feed"):
        assert key in d, key
    # cached second call returns the same generated_at
    r2 = client.get("/api/snapshot").json()
    assert r2["generated_at"] == d["generated_at"]


# ---------- deterministic chat (PRD §10 canonical questions) ----------

CASES = [
    ("What is the market regime today?", ["regime", "risk score"]),
    ("What are the key SPY and QQQ levels today?", ["QQQ", "SPY", "weekly pivot"]),
    ("Is today better for calls, puts, or no trade?", ["VIX"]),
    ("Which sectors are leading today?", ["Leading:"]),
    ("Which laggard sectors are starting to turn up?", ["Improving laggards:"]),
    ("Which stocks have the strongest setup for calls?", ["entry"]),
    ("Are we in accumulation, mark-up, distribution, or consolidation?", ["QQQ"]),
    ("What does dealer gamma positioning look like?", ["gamma", "wall"]),
]


@pytest.mark.parametrize("question,must_contain", CASES)
def test_chat_canonical_questions(client, question, must_contain):
    r = client.post("/api/chat", json={"message": question}).json()
    assert r["mode"] == "deterministic"
    for fragment in must_contain:
        assert fragment.lower() in r["reply"].lower(), (question, r["reply"])
    assert isinstance(r["tool_calls"], list)


def test_chat_extension_question_with_symbol(client):
    r = client.post("/api/chat",
                    json={"message": "Is NVDA extended right now?"}).json()
    assert "NVDA" in r["reply"] and "21d MA" in r["reply"]
    assert "screen" in r["tool_calls"]


def test_chat_invalidation_with_symbol(client):
    setups = client.get("/api/snapshot").json()["setups"]["setups"]
    if not setups:
        pytest.skip("no setups in this synthetic world")
    sym = setups[0]["symbol"]
    r = client.post("/api/chat",
                    json={"message": f"What level invalidates the {sym} trade?"}).json()
    assert sym in r["reply"] and "stop" in r["reply"].lower()


def test_chat_fallback_lists_capabilities(client):
    r = client.post("/api/chat", json={"message": "sing me a song"}).json()
    assert "regime" in r["reply"] and r["tool_calls"] == []


def test_chat_numbers_trace_to_engines(client):
    """Anti-hallucination at the chat layer: quoted levels must equal engine output."""
    levels = client.get("/api/snapshot").json()["indices"]["QQQ"]["levels"]
    r = client.post("/api/chat", json={"message": "key QQQ levels"}).json()
    assert str(levels["weekly"]["weekly_pivot"]) in r["reply"]
    if levels["bullish_trigger"]:
        assert str(levels["bullish_trigger"]) in r["reply"]


# ---------- composite MCP server ----------

def test_confluence_mcp_tools_registered():
    from confluence_mcp.server import mcp

    async def names():
        return [t.name for t in await mcp.list_tools()]

    tools = asyncio.run(names())
    assert {"get_game_plan", "get_regime", "get_levels", "get_setups",
            "get_rotation", "get_dealer_zones", "ask"} <= set(tools)
