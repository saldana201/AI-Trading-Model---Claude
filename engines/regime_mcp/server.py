"""regime-mcp — composite market regime + risk-on score (design doc §4.7)."""
import json, os
from mcp.server.fastmcp import FastMCP
from .logic import RegimeEngine
from ..shared.providers import SyntheticProvider, YFinanceProvider

mcp = FastMCP("regime-mcp")
_provider = (
    SyntheticProvider(drift_map={"^VIX": -0.004, "QQQ": 0.0015, "SPY": 0.001},
                      start_price_map={"^VIX": 18.0, "QQQ": 520.0, "SPY": 600.0})
    if os.environ.get("CONFLUENCE_DATA") == "synthetic" else YFinanceProvider()
)
_engine = RegimeEngine(_provider)

@mcp.tool()
def get_regime() -> str:
    """Current market regime (risk_on / risk_off / chop) with a -10..+10
    risk-on score, volatility modifiers, and every component's score, weight,
    contribution, and evidence. Rules-first and reproducible bar by bar."""
    return json.dumps(_engine.get_regime(), indent=2)

if __name__ == "__main__":
    mcp.run()
