"""Drive two scripted trades through the lifecycle and return the alert feed.

Used by scripts/snapshot.py so the dashboard's alert panel always has a real
(simulated) event trail: one winner (trigger -> T1 trim -> trail -> T2) and
one deterioration exit (VIX reclaims pivot while the index loses its weekly
pivot mid-trade).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from alerts.engine import AlertEngine
from alerts.lifecycle import Trade
from alerts.store import Store
from alerts.templates import render_event
from engines.shared.providers import ScriptedProvider, ReplayProvider
from engines.levels_mcp.logic import LevelsEngine
from engines.vix_mcp.logic import VixEngine


def _frame(path, base, n, idx, spread=0.6):
    k = n - len(path)
    # gentle wiggle on the base segment so fractal detection has pivots to find
    base_part = base + np.sin(np.arange(k) * 0.7) * spread * 1.2
    closes = np.concatenate([base_part, np.asarray(path, float)])
    return pd.DataFrame({"open": closes, "high": closes + spread,
                         "low": closes - spread, "close": closes,
                         "volume": np.full(n, 1_500_000.0)}, index=idx)


def run_demo() -> dict:
    # 8 replayed sessions: NVDA wins through T2; AMD's trade deteriorates when
    # VIX pops over its pivot zone (~18) while QQQ loses its weekly pivot.
    nvda = [141.0, 142.6, 143.5, 147.5, 149.0, 151.4, 151.8, 151.5]
    amd = [119.2, 119.5, 121.4, 122.0, 122.5, 122.2, 121.8, 121.5]
    vix = [15.0, 14.8, 14.6, 14.5, 14.4, 14.3, 19.4, 19.8]
    qqq = [531.0, 532.0, 533.0, 534.0, 533.5, 533.0, 518.0, 516.0]

    steps = len(nvda)
    n = steps + 70
    idx = pd.date_range("2026-02-23", periods=n, freq="B")
    frames = {
        "NVDA": _frame(nvda, 141.3, n, idx),
        "AMD": _frame(amd, 119.0, n, idx),
        "^VIX": _frame(vix, 16.5, n, idx, spread=0.4),
        "QQQ": _frame(qqq, 528.0, n, idx),
    }
    replay = ReplayProvider(ScriptedProvider(frames), start_offset=steps)
    engine = AlertEngine(replay, LevelsEngine(replay, lookback_days=70),
                         VixEngine(replay), store=Store())

    trades = [
        Trade(symbol="NVDA", direction="long", entry_trigger=142.5, stop=139.8,
              target_1=147.0, target_2=151.0, trail_distance=2.4,
              setup_meta={"confidence": 7.8, "sector_etf": "SMH",
                          "thesis": "Breakout over 142.50 with SMH leading and "
                                    "VIX below pivot; targets 147 then 151."}),
        Trade(symbol="AMD", direction="long", entry_trigger=120.8, stop=117.9,
              target_1=125.5, target_2=129.0, trail_distance=2.2,
              setup_meta={"confidence": 6.7, "sector_etf": "SMH",
                          "thesis": "Continuation over 120.80 while index "
                                    "alignment holds."}),
    ]
    for t in trades:
        engine.trades[t.id] = t
        engine.store.save_trade(t.to_dict())

    feed = []
    for _ in range(steps):
        for ev in engine.tick():
            trade = engine.trades.get(ev["trade_id"])
            feed.append({**ev, "message": render_event(
                ev, trade.to_dict() if trade else None)})
        replay.advance()

    return {"label": "simulated lifecycle demo (scripted bars)",
            "events": feed,
            "final_states": {t.symbol: t.state for t in trades}}


if __name__ == "__main__":
    out = run_demo()
    for e in out["events"]:
        print(e["message"], "\n")
    print("final:", out["final_states"])
