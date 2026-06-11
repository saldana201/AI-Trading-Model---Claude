"""Phase 1 demo — run both engines end to end and print their payloads.

Usage:
    CONFLUENCE_DATA=synthetic python demo.py        # offline, reproducible
    python demo.py                                  # live via yfinance
"""

import json
import os

from engines.shared.providers import SyntheticProvider, YFinanceProvider
from engines.vix_mcp.logic import VixEngine
from engines.levels_mcp.logic import LevelsEngine


def main() -> None:
    if os.environ.get("CONFLUENCE_DATA", "yfinance") == "synthetic":
        provider = SyntheticProvider(
            drift_map={"^VIX": -0.004, "QQQ": 0.0015, "SPY": 0.001},
            start_price_map={"^VIX": 18.0, "QQQ": 520.0, "SPY": 600.0},
        )
        print("[demo] using synthetic data (set CONFLUENCE_DATA=yfinance for live)\n")
    else:
        provider = YFinanceProvider()
        print("[demo] using live yfinance data\n")

    vix = VixEngine(provider)
    levels = LevelsEngine(provider)

    print("=== vix-mcp :: get_vix_levels ===")
    vl = vix.get_levels()
    print(json.dumps({k: v for k, v in vl.items() if k != "clusters"}, indent=2))

    print("\n=== vix-mcp :: get_vix_alignment(QQQ) ===")
    print(json.dumps(vix.get_alignment("QQQ"), indent=2))

    print("\n=== levels-mcp :: get_index_levels(QQQ) ===")
    ql = levels.get_levels("QQQ")
    summary = {k: ql[k] for k in (
        "symbol", "spot", "rvol_20d", "session", "weekly", "outliers",
        "bullish_trigger", "bearish_trigger", "chop_zone",
    )}
    summary["moving_averages"] = ql["moving_averages"]
    summary["n_fractal_clusters"] = len(ql["fractal_clusters"])
    print(json.dumps(summary, indent=2))

    if ql["bullish_trigger"]:
        print("\n=== levels-mcp :: check_level_break(QQQ, bullish_trigger, above) ===")
        print(json.dumps(levels.check_break("QQQ", ql["bullish_trigger"], "above"), indent=2))


if __name__ == "__main__":
    main()
