"""volume-mcp — RVOL + price-volume phase classification (design doc §4.3)."""
import json, os
from mcp.server.fastmcp import FastMCP
from .logic import VolumeEngine
from ..shared.providers import SyntheticProvider, YFinanceProvider

mcp = FastMCP("volume-mcp")
_provider = SyntheticProvider() if os.environ.get("CONFLUENCE_DATA") == "synthetic" else YFinanceProvider()
_engine = VolumeEngine(_provider)

@mcp.tool()
def get_rvol(symbol: str) -> str:
    """Relative volume vs 20-day and 50-day averages, plus the up/down volume ratio."""
    return json.dumps(_engine.get_rvol(symbol), indent=2)

@mcp.tool()
def classify_phase(symbol: str) -> str:
    """Classify the symbol's price-volume phase: accumulation, mark_up,
    distribution, mark_down, consolidation, exhaustion, failed_breakout, or
    failed_breakdown — with the trend/volume evidence behind the call."""
    return json.dumps(_engine.get_phase(symbol), indent=2)

if __name__ == "__main__":
    mcp.run()
