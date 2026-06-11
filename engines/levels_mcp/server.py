"""levels-mcp — MCP server for the SPY/QQQ and stock level engine (design doc §4.2).

Run:  python -m engines.levels_mcp.server
"""

from __future__ import annotations

import json
import os

from mcp.server.fastmcp import FastMCP

from .logic import LevelsEngine
from ..shared.providers import SyntheticProvider, YFinanceProvider

mcp = FastMCP("levels-mcp")

_provider = (
    SyntheticProvider(start_price_map={"QQQ": 520.0, "SPY": 600.0})
    if os.environ.get("CONFLUENCE_DATA", "yfinance") == "synthetic"
    else YFinanceProvider()
)
_engine = LevelsEngine(_provider)


@mcp.tool()
def get_index_levels(symbol: str = "QQQ") -> str:
    """Full daily level set for an index ETF (or any symbol): high/low of day,
    prior day high/low, weekly pivot/ceiling/floor, ATR outlier levels, gap
    levels, fractal support/resistance clusters with strength scores, bullish
    and bearish trigger candidates, MA reclaim/loss status, and RVOL. Every
    level carries its computation method and timestamp."""
    return json.dumps(_engine.get_levels(symbol), indent=2)


@mcp.tool()
def get_stock_levels(symbol: str) -> str:
    """Same level computation as get_index_levels, for an individual stock."""
    return json.dumps(_engine.get_levels(symbol), indent=2)


@mcp.tool()
def check_level_break(symbol: str, level: float, direction: str = "above") -> str:
    """Check whether the latest bar has broken a level ('above' or 'below'),
    with volume context (RVOL) and whether the bar held through the level.
    This is the primitive the alert engine polls."""
    return json.dumps(_engine.check_break(symbol, level, direction), indent=2)


if __name__ == "__main__":
    mcp.run()
