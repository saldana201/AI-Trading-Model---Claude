"""screener-mcp — CANSLIM-style technical screen (design doc §4.8)."""
import json, os
from mcp.server.fastmcp import FastMCP
from .logic import ScreenerEngine
from ..shared.providers import SyntheticProvider, YFinanceProvider

mcp = FastMCP("screener-mcp")
_provider = SyntheticProvider() if os.environ.get("CONFLUENCE_DATA") == "synthetic" else YFinanceProvider()
_engine = ScreenerEngine(_provider)

@mcp.tool()
def screen(symbols: str) -> str:
    """Run the CANSLIM-style technical screen on a comma-separated symbol list.
    Returns the full filter checklist per symbol plus a classification:
    canslim_leader / laggard_turn / speculative_momentum / overextended / no_setup."""
    return json.dumps(_engine.screen([s.strip().upper() for s in symbols.split(",") if s.strip()]), indent=2)

if __name__ == "__main__":
    mcp.run()
