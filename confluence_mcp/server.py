"""confluence-mcp — the composite MCP server (design doc §8 integration
surface). The whole system as one server: plug it into Claude Desktop,
Claude Code, or any MCP client and ask for the game plan.

Run:  CONFLUENCE_DATA=synthetic python -m confluence_mcp.server
"""
import json
import os

from mcp.server.fastmcp import FastMCP

from apps.api.main import get_state
from scripts.snapshot import build_snapshot

mcp = FastMCP("confluence-mcp")


def _tb():
    return get_state()["toolbox"]


@mcp.tool()
def get_game_plan() -> str:
    """The full daily game plan: regime + risk score, VIX framework,
    QQQ/SPY levels, sector rotation board, composed trade setups with
    entries/stops/targets/confidence, options positioning, and the alert
    feed. This is the same payload the dashboard renders."""
    return json.dumps(build_snapshot(), indent=2, default=str)


@mcp.tool()
def get_regime() -> str:
    """Market regime (risk_on/risk_off/chop), -10..+10 risk score, and every
    component's contribution with evidence."""
    return json.dumps(_tb().call("get_regime", {}), indent=2, default=str)


@mcp.tool()
def get_levels(symbol: str = "QQQ") -> str:
    """Key levels for an index or stock: bullish/bearish triggers, weekly
    pivot/ceiling/floor, session levels, fractal clusters, MA status, RVOL."""
    return json.dumps(_tb().call("get_index_levels", {"symbol": symbol}),
                      indent=2, default=str)


@mcp.tool()
def get_setups() -> str:
    """Today's composed, validated trade setups — or the stand-aside reason
    when the regime gate says no-trade."""
    return json.dumps(_tb().call("get_setups", {}), indent=2, default=str)


@mcp.tool()
def get_rotation() -> str:
    """Leading sectors, improving laggards, deteriorating leaders."""
    return json.dumps(_tb().call("get_rotation", {}), indent=2, default=str)


@mcp.tool()
def get_dealer_zones(symbol: str = "QQQ") -> str:
    """Gamma regime, zero-gamma flip, call/put walls, and the reading."""
    return json.dumps(_tb().call("get_dealer_zones", {"symbol": symbol}),
                      indent=2, default=str)


@mcp.tool()
def get_vol_forecast(symbol: str, horizon_days: int = 21) -> str:
    """GARCH(1,1) volatility forecast: fitted parameters, next-day and
    horizon-averaged annualized vol, mean-reversion half-life, and the 1-sigma
    expected move. Deterministic — the same bars always give the same fit."""
    from engines.volatility_mcp.logic import VolatilityEngine
    from scripts.snapshot import build_provider
    provider, _ = build_provider()
    return json.dumps(
        VolatilityEngine(provider).get_forecast(symbol, horizon_days),
        indent=2, default=str)


@mcp.tool()
def compare_iv_to_forecast(symbol: str, implied_vol: float,
                           dte: int = 30) -> str:
    """Variance risk premium: is a contract's implied vol rich or cheap versus
    the GARCH forecast for its horizon? IV rank only says whether IV is high
    for this name; this says whether it is high relative to the volatility
    likely to be realized. Rich favors debit spreads, cheap favors a single
    long leg. Pass implied_vol as a decimal (0.30 = 30%)."""
    from engines.volatility_mcp.logic import VolatilityEngine
    from scripts.snapshot import build_provider
    provider, _ = build_provider()
    return json.dumps(
        VolatilityEngine(provider).get_iv_comparison(symbol, implied_vol, dte),
        indent=2, default=str)


@mcp.tool()
def ask(question: str) -> str:
    """Ask the Confluence chat service a PRD-style question (regime, levels,
    calls vs puts, sectors, setups, extension, invalidation, phase, gamma)."""
    return json.dumps(get_state()["chat"].ask(question), indent=2, default=str)


if __name__ == "__main__":
    mcp.run()
