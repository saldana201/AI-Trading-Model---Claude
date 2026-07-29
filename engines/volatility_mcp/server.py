"""volatility-mcp — MCP server for the GARCH/realized-volatility engine.

Run:  python -m engines.volatility_mcp.server          (stdio transport)
Use:  add to Claude Desktop / Claude Code MCP config, or attach to the
      orchestrator's Anthropic SDK tool-use loop.

The point of this engine: `iv_rank` tells you IV is high for this name; it
cannot tell you whether IV is high *relative to the volatility that will
actually happen*. These tools supply the other half of that comparison.
"""

from __future__ import annotations

import json
import os

from mcp.server.fastmcp import FastMCP

from .logic import VolatilityEngine
from ..shared.providers import SyntheticProvider, YFinanceProvider

mcp = FastMCP("volatility-mcp")

_provider = (
    SyntheticProvider(drift_map={"QQQ": 0.0015, "SPY": 0.001},
                      start_price_map={"QQQ": 520.0, "SPY": 580.0})
    if os.environ.get("CONFLUENCE_DATA", "yfinance") == "synthetic"
    else YFinanceProvider()
)
_engine = VolatilityEngine(_provider)


@mcp.tool()
def get_realized_vol(symbol: str) -> str:
    """Annualized realized volatility over 10/21/63 days via three estimators
    (close-to-close, Parkinson, Garman-Klass) plus RiskMetrics EWMA(0.94).
    Close-to-close is the one that captures overnight gap risk; Parkinson and
    Garman-Klass are more efficient but blind to gaps."""
    return json.dumps(_engine.get_realized(symbol), indent=2)


@mcp.tool()
def get_vol_forecast(symbol: str, horizon_days: int = 21) -> str:
    """Fit GARCH(1,1) to daily log returns and forecast volatility over the
    horizon. Returns fitted parameters (omega/alpha/beta/persistence), the
    next-day and horizon-averaged annualized vol, the mean-reversion half-life,
    and the 1-sigma expected move in price terms. Deterministic grid MLE — the
    same bars always produce the same parameters."""
    return json.dumps(_engine.get_forecast(symbol, horizon_days), indent=2)


@mcp.tool()
def get_vol_cone(symbol: str) -> str:
    """Realized-vol percentiles across 10/21/42/63/126-day horizons — where
    current volatility sits in its own historical distribution per horizon."""
    return json.dumps(_engine.get_cone(symbol), indent=2)


@mcp.tool()
def compare_iv_to_forecast(symbol: str, implied_vol: float,
                           dte: int = 30) -> str:
    """The variance risk premium: compare a contract's implied vol against the
    GARCH forecast for a horizon matched to its DTE. Returns rich / slightly
    rich / fair / slightly cheap / cheap with the ratio and both expected
    moves. Rich favors debit spreads; cheap favors a single long leg.

    Pass implied_vol as a decimal (0.30 for 30%), not a percentage."""
    return json.dumps(_engine.get_iv_comparison(symbol, implied_vol, dte),
                      indent=2)


if __name__ == "__main__":
    mcp.run()
