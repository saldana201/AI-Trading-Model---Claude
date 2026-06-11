"""fundamentals-mcp — fundamental snapshot + earnings window (design doc §4.8)."""
import json, os
from mcp.server.fastmcp import FastMCP
from .logic import FundamentalsEngine, SyntheticFundamentals, YFinanceFundamentals

mcp = FastMCP("fundamentals-mcp")
_engine = FundamentalsEngine(
    SyntheticFundamentals() if os.environ.get("CONFLUENCE_DATA") == "synthetic"
    else YFinanceFundamentals())

@mcp.tool()
def get_snapshot(symbol: str) -> str:
    """Fundamental snapshot: revenue/EPS growth with a growth grade, margins,
    valuation, institutional sponsorship, sector, earnings date, and an
    in_earnings_window flag (a hard input to the setup composer)."""
    return json.dumps(_engine.get_snapshot(symbol.upper()), indent=2)

if __name__ == "__main__":
    mcp.run()
