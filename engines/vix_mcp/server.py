"""vix-mcp — MCP server for the VIX framework (design doc §4.1).

Run:  python -m engines.vix_mcp.server          (stdio transport)
Use:  add to Claude Desktop / Claude Code MCP config, or attach to the
      orchestrator's Anthropic SDK tool-use loop.
"""

from __future__ import annotations

import json
import os

from mcp.server.fastmcp import FastMCP

from .logic import VixEngine
from ..shared.providers import SyntheticProvider, YFinanceProvider

mcp = FastMCP("vix-mcp")

_provider = (
    SyntheticProvider(drift_map={"^VIX": -0.004, "QQQ": 0.0015},
                      start_price_map={"^VIX": 18.0, "QQQ": 520.0})
    if os.environ.get("CONFLUENCE_DATA", "yfinance") == "synthetic"
    else YFinanceProvider()
)
_engine = VixEngine(_provider)


@mcp.tool()
def get_vix_levels() -> str:
    """Today's VIX pivot, upside targets 1/2, downside targets 1/2, and the
    fractal clusters they were derived from. All levels are computed from
    Williams fractals on daily VIX bars — deterministic, with timestamps."""
    return json.dumps(_engine.get_levels(), indent=2)


@mcp.tool()
def get_vix_alignment(symbol: str = "QQQ") -> str:
    """Classify whether VIX is confirming or diverging from an index's price
    action. Returns one of: confirming_bullish, confirming_bearish,
    diverging_warning, diverging_supportive, neutral_chop — with the
    underlying numbers as evidence."""
    return json.dumps(_engine.get_alignment(symbol), indent=2)


if __name__ == "__main__":
    mcp.run()
