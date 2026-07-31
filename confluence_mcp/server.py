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


def _all_engines():
    """Construct every engine once, sharing one provider."""
    from scripts.snapshot import build_provider
    from engines.vix_mcp.logic import VixEngine
    from engines.levels_mcp.logic import LevelsEngine
    from engines.volume_mcp.logic import VolumeEngine
    from engines.momentum_mcp.logic import MomentumEngine
    from engines.regime_mcp.logic import RegimeEngine
    from engines.rotation_mcp.logic import RotationEngine
    from engines.screener_mcp.logic import ScreenerEngine
    from engines.volatility_mcp.logic import VolatilityEngine
    from engines.fundamentals_mcp.logic import (
        FundamentalsEngine, YFinanceFundamentals, SyntheticFundamentals)
    from engines.options_mcp.logic import OptionsEngine
    from engines.options_mcp.providers import SyntheticOptions, YFinanceOptions
    provider, source = build_provider()
    rot = RotationEngine(provider)
    fund_p = SyntheticFundamentals() if source == "synthetic" else YFinanceFundamentals()
    opt_p = SyntheticOptions(iv_rank=0.62) if source == "synthetic" else YFinanceOptions()
    vol = VolatilityEngine(provider)
    return {
        "vix": VixEngine(provider),
        "levels": LevelsEngine(provider),
        "volume": VolumeEngine(provider),
        "momentum": MomentumEngine(provider),
        "regime": RegimeEngine(provider, rotation_engine=rot),
        "rotation": rot,
        "screener": ScreenerEngine(provider),
        "volatility": vol,
        "fundamentals": FundamentalsEngine(fund_p),
        "options": OptionsEngine(provider, opt_p, volatility_engine=vol),
    }


@mcp.tool()
def engine_brief(symbol: str) -> str:
    """EVERYTHING the deterministic engines know about one symbol: support and
    resistance clusters, VIX pivot and alignment, RVOL and volume phase, RSI
    stack and divergences, market regime, sector rotation, GARCH volatility
    forecast and vol cone, gamma walls and the zero-gamma flip, fundamentals and
    screen classification.

    Facts only — no score, no direction, no suggested trade. Every value carries
    the method that produced it. This is the recommended entry point: the
    engines are what survived validation, while the system's composed setups
    underperformed buy-and-hold over the tested window."""
    from orchestrator.engine_brief import build_brief, assert_no_recommendation
    b = build_brief(symbol, _all_engines())
    assert_no_recommendation(b)
    return json.dumps(b, indent=2, default=str)


@mcp.tool()
def get_vix() -> str:
    """VIX pivot, upside/downside targets from fractal clusters, and term
    structure state (contango / flat / backwardation)."""
    from engines.vix_mcp.logic import VixEngine
    from scripts.snapshot import build_provider
    return json.dumps(VixEngine(build_provider()[0]).get_levels(),
                      indent=2, default=str)


@mcp.tool()
def get_volume(symbol: str) -> str:
    """Relative volume vs 20/50-day averages and the Wyckoff-style phase
    classification (accumulation / mark-up / distribution / consolidation /
    exhaustion / failed breakout)."""
    from engines.volume_mcp.logic import VolumeEngine
    from scripts.snapshot import build_provider
    p = build_provider()[0]
    e = VolumeEngine(p)
    return json.dumps({"rvol": e.get_rvol(symbol), "phase": e.get_phase(symbol)},
                      indent=2, default=str)


@mcp.tool()
def get_momentum(symbol: str) -> str:
    """RSI across timeframes plus price/RSI divergences, with the pivot pairs
    used to detect them."""
    from engines.momentum_mcp.logic import MomentumEngine
    from scripts.snapshot import build_provider
    e = MomentumEngine(build_provider()[0])
    return json.dumps({"rsi_stack": e.get_rsi_stack(symbol),
                       "divergences": e.get_divergences(symbol)},
                      indent=2, default=str)


@mcp.tool()
def get_fundamentals(symbol: str) -> str:
    """EPS/revenue growth, margins, valuation, institutional sponsorship and the
    earnings date (a hard input to any swing timing decision)."""
    from scripts.snapshot import build_provider
    from engines.fundamentals_mcp.logic import (
        FundamentalsEngine, YFinanceFundamentals, SyntheticFundamentals)
    _, source = build_provider()
    p = SyntheticFundamentals() if source == "synthetic" else YFinanceFundamentals()
    return json.dumps(FundamentalsEngine(p).get_snapshot(symbol),
                      indent=2, default=str)


@mcp.tool()
def ask(question: str) -> str:
    """Ask the Confluence chat service a PRD-style question (regime, levels,
    calls vs puts, sectors, setups, extension, invalidation, phase, gamma)."""
    return json.dumps(get_state()["chat"].ask(question), indent=2, default=str)


if __name__ == "__main__":
    mcp.run()
