"""Generate the dashboard data feed by running every engine.

Usage:
    CONFLUENCE_DATA=synthetic python -m scripts.snapshot     # offline
    python -m scripts.snapshot                               # live yfinance

Writes dashboard/data.json — the same payload a future Next.js API route
(/api/snapshot) will serve. The dashboard reads this file directly in Phase 2.
"""

from __future__ import annotations

import json
import os
import pathlib

from engines.shared.providers import SyntheticProvider, YFinanceProvider
from engines.vix_mcp.logic import VixEngine
from engines.levels_mcp.logic import LevelsEngine
from engines.volume_mcp.logic import VolumeEngine
from engines.momentum_mcp.logic import MomentumEngine
from engines.regime_mcp.logic import RegimeEngine
from engines.rotation_mcp.logic import RotationEngine
from engines.screener_mcp.logic import ScreenerEngine
from engines.fundamentals_mcp.logic import (
    FundamentalsEngine, SyntheticFundamentals, YFinanceFundamentals)
from orchestrator.composer import SetupComposer
from orchestrator.llm import make_thesis_writer

INDEX_SYMBOLS = ["QQQ", "SPY"]


def build_provider():
    if os.environ.get("CONFLUENCE_DATA", "yfinance") == "synthetic":
        return SyntheticProvider(
            drift_map={"^VIX": -0.005, "QQQ": 0.0025, "SPY": 0.0015,
                       "SMH": 0.0045, "IGV": 0.0035, "XLK": 0.003, "NLR": 0.003,
                       "NVDA": 0.005, "AVGO": 0.0045, "AMD": 0.004,
                       "CRM": 0.0035, "NOW": 0.0035, "PLTR": 0.004,
                       "MSFT": 0.0035, "CEG": 0.004, "VST": 0.0045,
                       "XLU": -0.002, "XLP": -0.001},
            drift_change_map={"URA": (-0.008, 0.012, 0.95)},
            start_price_map={"^VIX": 18.0, "QQQ": 520.0, "SPY": 600.0},
        ), "synthetic"
    return YFinanceProvider(), "yfinance"


def build_snapshot() -> dict:
    provider, source = build_provider()
    vix = VixEngine(provider)
    levels = LevelsEngine(provider)
    volume = VolumeEngine(provider)
    momentum = MomentumEngine(provider)
    regime = RegimeEngine(provider)
    rotation = RotationEngine(provider)
    fundamentals = FundamentalsEngine(
        SyntheticFundamentals() if source == "synthetic" else YFinanceFundamentals())
    composer = SetupComposer(
        provider=provider, regime_engine=regime, rotation_engine=rotation,
        levels_engine=levels, volume_engine=volume, momentum_engine=momentum,
        fundamentals_engine=fundamentals, screener_engine=ScreenerEngine(provider),
        thesis_writer=make_thesis_writer())

    vix_levels = vix.get_levels()
    snapshot = {
        "source": source,
        "generated_at": vix_levels["computed_at"],
        "regime": regime.get_regime(),
        "vix": {
            "levels": vix_levels,
            "alignment": vix.get_alignment("QQQ"),
        },
        "indices": {},
        "rotation": rotation.get_leaderboard(),
        "setups": composer.compose(),
    }
    for sym in INDEX_SYMBOLS:
        snapshot["indices"][sym] = {
            "levels": levels.get_levels(sym),
            "phase": volume.get_phase(sym),
            "rsi": momentum.get_rsi_stack(sym),
            "divergences": momentum.get_divergences(sym)["divergences"],
        }
    return snapshot


def main() -> None:
    out_dir = pathlib.Path(__file__).resolve().parent.parent / "dashboard"
    out_dir.mkdir(exist_ok=True)
    snap = build_snapshot()
    path = out_dir / "data.json"
    path.write_text(json.dumps(snap, indent=2))
    print(f"[snapshot] wrote {path} ({snap['source']}, regime={snap['regime']['regime']}, "
          f"score={snap['regime']['risk_score']})")


if __name__ == "__main__":
    main()
