"""options-mcp — gamma/vanna positioning + contract selection (design doc §4.6)."""
import json, os
from mcp.server.fastmcp import FastMCP
from .logic import OptionsEngine
from .providers import SyntheticOptions, YFinanceOptions
from ..shared.providers import SyntheticProvider, YFinanceProvider

mcp = FastMCP("options-mcp")
if os.environ.get("CONFLUENCE_DATA") == "synthetic":
    _engine = OptionsEngine(SyntheticProvider(), SyntheticOptions())
else:
    _engine = OptionsEngine(YFinanceProvider(), YFinanceOptions())

@mcp.tool()
def get_gex_profile(symbol: str) -> str:
    """Per-strike net dealer gamma (GEX, $m per 1% move) and vanna, the
    zero-gamma flip, call/put walls, and the gamma regime. Computed in-house
    from the chain — a positioning estimate, not dealer ground truth."""
    return json.dumps(_engine.get_gex_profile(symbol.upper()), indent=2)

@mcp.tool()
def get_dealer_zones(symbol: str) -> str:
    """Flip, walls, and the interpretation: positive gamma = dealers dampen,
    walls pin; negative gamma = dealers amplify, breaks accelerate."""
    return json.dumps(_engine.get_dealer_zones(symbol.upper()), indent=2)

@mcp.tool()
def get_contract_quality(symbol: str, strike: float, expiry: str, opt_type: str) -> str:
    """Liquidity check for one contract: OI, volume, bid/ask spread as % of
    mid, and a liquid/illiquid verdict against the PRD §13 floors."""
    return json.dumps(_engine.get_contract_quality(symbol.upper(), strike, expiry, opt_type), indent=2)

@mcp.tool()
def select_contract(symbol: str, direction: str, entry: float,
                    target_1: float, target_2: float, horizon: str = "swing") -> str:
    """PRD §13 contract selection: call/put, strike at the entry zone, expiry
    by horizon, debit spread when IV rank is elevated, liquidity gates, and an
    expected-move check on target 1. Falls back to stock with the reason."""
    return json.dumps(_engine.select_contract(symbol.upper(), direction, entry,
                                              target_1, target_2, horizon), indent=2)

if __name__ == "__main__":
    mcp.run()
