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
from backtest.costs import CostModel
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


def composer_factory_for(source: str, with_options: bool = False):
    """with_options attaches the options engine so backtested setups carry the
    instrument the live system would actually trade (usually a debit spread)
    rather than defaulting to shares. Off by default: yfinance has no historical
    chains, so only the synthetic world gives an honest answer here."""
    def factory(replay):
        rotation = RotationEngine(replay)
        options = None
        if with_options:
            from engines.options_mcp.logic import OptionsEngine
            from engines.options_mcp.providers import (
                SyntheticOptions, YFinanceOptions)
            options = OptionsEngine(
                replay,
                SyntheticOptions(iv_rank=0.62) if source == "synthetic"
                else YFinanceOptions())
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
            options_engine=options,
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
    ap.add_argument("--slippage-bps", type=float, default=5.0,
                    help="per-side slippage in bps of price (stock trades)")
    ap.add_argument("--commission-per-share", type=float, default=0.005)
    ap.add_argument("--commission-per-contract", type=float, default=0.65)
    ap.add_argument("--option-spread-pct", type=float, default=None,
                    help="override the engine's per-contract spread")
    ap.add_argument("--no-costs", action="store_true",
                    help="report gross R only (the pre-Phase-17 behavior)")
    ap.add_argument("--with-options", action="store_true",
                    help="attach the options engine so setups carry the "
                         "instrument the live system would trade")
    args = ap.parse_args()

    cost_model = CostModel(
        slippage_bps=0.0 if args.no_costs else args.slippage_bps,
        commission_per_share=0.0 if args.no_costs else args.commission_per_share,
        commission_per_contract=(0.0 if args.no_costs
                                 else args.commission_per_contract),
        option_spread_pct=(0.0 if args.no_costs else args.option_spread_pct),
    )

    provider, source = build_provider()
    bt = Backtest(provider, composer_factory_for(source, args.with_options),
                  span_bars=args.span, step_bars=args.step,
                  horizon_bars=args.horizon, n_trials=args.trials,
                  cost_model=cost_model)
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
