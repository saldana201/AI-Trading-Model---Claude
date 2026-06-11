"""momentum-mcp — RSI stack + divergence detection (design doc §4.4)."""
import json, os
from mcp.server.fastmcp import FastMCP
from .logic import MomentumEngine
from ..shared.providers import SyntheticProvider, YFinanceProvider

mcp = FastMCP("momentum-mcp")
_provider = SyntheticProvider() if os.environ.get("CONFLUENCE_DATA") == "synthetic" else YFinanceProvider()
_engine = MomentumEngine(_provider)

@mcp.tool()
def get_rsi_stack(symbol: str) -> str:
    """RSI across monthly, weekly, daily (and 1h/30m when intraday bars are
    available) with overbought/oversold zone and 3-bar direction per timeframe."""
    return json.dumps(_engine.get_rsi_stack(symbol), indent=2)

@mcp.tool()
def find_divergences(symbol: str) -> str:
    """Detect bullish/bearish RSI divergences anchored to price fractal pivots.
    Output cites the exact pivot pair (time, price, RSI) behind each call."""
    return json.dumps(_engine.get_divergences(symbol), indent=2)

if __name__ == "__main__":
    mcp.run()
