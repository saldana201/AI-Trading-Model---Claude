"""rotation-mcp — 31-ETF sector rotation engine (design doc §4.5)."""
import json, os
from mcp.server.fastmcp import FastMCP
from .logic import RotationEngine
from ..shared.providers import SyntheticProvider, YFinanceProvider

mcp = FastMCP("rotation-mcp")
_provider = SyntheticProvider() if os.environ.get("CONFLUENCE_DATA") == "synthetic" else YFinanceProvider()
_engine = RotationEngine(_provider)

@mcp.tool()
def get_leaderboard() -> str:
    """Full sector board: relative performance vs SPY over 1/4/12/24/48 weeks,
    RVOL, MA-stack status, and rotation classification (leading / improving /
    neutral / deteriorating / lagging) for all 31 tracked ETFs."""
    return json.dumps(_engine.get_leaderboard(), indent=2)

@mcp.tool()
def get_rotation_candidates() -> str:
    """Just the actionable rotation: leading sectors, improving laggards
    (the early-rotation flag), and deteriorating leaders."""
    return json.dumps(_engine.get_rotation_candidates(), indent=2)

if __name__ == "__main__":
    mcp.run()
