"""Run a backtest over the live (or synthetic) world.

Usage:
    CONFLUENCE_DATA=synthetic python -m backtest.run
    python -m backtest.run --span 252 --step 5 --horizon 15      # live yfinance
    CONFLUENCE_FORCE_DIRECTION=long python -m backtest.run        # bypass chop gate

Writes backtest/results.json and prints the calibration report.
"""
from __future__ import annotations

import argparse
import json
import pathlib
from datetime import date

from backtest.harness import Backtest, render_text
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
from scripts.snapshot import build_provider


def composer_factory_for(source: str):
    def factory(replay):
        rotation = RotationEngine(replay)
        return SetupComposer(
            provider=replay,
            regime_engine=RegimeEngine(replay),   # MA-proxy breadth: cheap per step
            rotation_engine=rotation,
            levels_engine=LevelsEngine(replay),
            volume_engine=VolumeEngine(replay),
            momentum_engine=MomentumEngine(replay),
            fundamentals_engine=FundamentalsEngine(
                SyntheticFundamentals() if source == "synthetic"
                else YFinanceFundamentals()),
            screener_engine=ScreenerEngine(replay),
        )
    return factory


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--span", type=int, default=252, help="bars of history")
    ap.add_argument("--step", type=int, default=5, help="compose every N bars")
    ap.add_argument("--horizon", type=int, default=15, help="max bars per trade")
    ap.add_argument("--trials", type=int, default=1,
                    help="distinct weight/threshold configs tried against this "
                         "data, for the Deflated Sharpe Ratio (selection-bias "
                         "correction). Bump this each time you tune and re-run.")
    args = ap.parse_args()

    provider, source = build_provider()
    bt = Backtest(provider, composer_factory_for(source),
                  span_bars=args.span, step_bars=args.step,
                  horizon_bars=args.horizon, n_trials=args.trials)
    rep = bt.run()

    out = pathlib.Path(__file__).resolve().parent / "results.json"
    out.write_text(json.dumps({"ran_at": str(date.today()), "source": source,
                               "params": vars(args), **rep}, indent=2))
    print(f"[backtest] {source} · span {args.span} · step {args.step} · "
          f"horizon {args.horizon}\n")
    print(render_text(rep))
    print(f"\n[backtest] full results -> {out}")


if __name__ == "__main__":
    main()
