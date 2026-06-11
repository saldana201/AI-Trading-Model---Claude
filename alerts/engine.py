"""Alert engine (design doc §6): arm setups from the composer's game plan,
then tick. Each tick pulls the latest bar per symbol, evaluates the market
guard (VIX pivot + index trigger), steps every armed trade through the
lifecycle, persists, and emits events to sinks.

Detection is deterministic; message language is templates (or an LLM rewrite
after the fact — never in the detection path).
"""

from __future__ import annotations

import pandas as pd

from engines.shared.providers import BarRequest
from engines.shared.levels import rvol
from .lifecycle import Trade, step, TERMINAL
from .predicates import AlertContext, evaluate
from .store import Store


def market_guard_factory(ctx: AlertContext, index_symbol: str = "QQQ"):
    """PRD §16's deterioration rule: VIX reclaims its pivot AND the index
    loses its weekly pivot (mirrored for shorts)."""
    def guard(direction: str):
        v = ctx.vix_levels()
        idx = ctx.symbol_levels(index_symbol)
        wp = idx["weekly"]["weekly_pivot"]
        if direction == "long":
            bad = (v["pivot"] is not None and v["spot"] > v["pivot"]
                   and idx["spot"] < wp)
        else:
            bad = (v["pivot"] is not None and v["spot"] < v["pivot"]
                   and idx["spot"] > wp)
        return bad, {"vix_spot": v["spot"], "vix_pivot": v["pivot"],
                     "index_spot": idx["spot"], "index_weekly_pivot": wp}
    return guard


def arm_from_setup(setup: dict, atr14: float, min_rvol: float = 1.2) -> Trade:
    """Convert one composer setup into an armed lifecycle trade."""
    return Trade(
        symbol=setup["symbol"], direction=setup["direction"],
        entry_trigger=setup["entry_trigger"], stop=setup["stop"],
        target_1=setup["target_1"], target_2=setup["target_2"],
        trail_distance=round(1.5 * atr14, 4), min_rvol=min_rvol,
        setup_meta={"confidence": setup.get("confidence"),
                    "thesis": setup.get("thesis"),
                    "sector_etf": setup.get("sector_etf"),
                    "invalidation": setup.get("invalidation")},
    )


class AlertEngine:
    def __init__(self, provider, levels_engine, vix_engine,
                 store: Store | None = None, sinks: list | None = None,
                 index_symbol: str = "QQQ"):
        self.provider = provider
        self.levels = levels_engine
        self.vix = vix_engine
        self.store = store or Store()
        self.sinks = sinks or []
        self.index_symbol = index_symbol
        self.trades: dict[str, Trade] = {}
        self.conditions: list[dict] = []   # standalone predicate trees

    # ---------- arming ----------

    def arm_setups(self, game_plan: dict) -> list[str]:
        armed = []
        for setup in game_plan.get("setups", []):
            payload = self.levels.get_levels(setup["symbol"])
            trade = arm_from_setup(setup, payload["outliers"]["atr14"])
            self.trades[trade.id] = trade
            self.store.save_trade(trade.to_dict())
            armed.append(trade.id)
        return armed

    def arm_condition(self, condition: dict) -> None:
        """Arm a standalone PRD §11 conditional (predicate tree + label)."""
        self.conditions.append(condition)

    # ---------- ticking ----------

    def _latest_bar(self, symbol: str) -> dict:
        bars = self.provider.get_bars(BarRequest(symbol, "1d", 120))
        last = bars.iloc[-1]
        return {"close": float(last["close"]), "high": float(last["high"]),
                "low": float(last["low"]), "time": bars.index[-1],
                "rvol": rvol(bars, 20)}

    def tick(self) -> list[dict]:
        ctx = AlertContext(self.levels, self.vix)   # fresh cache per tick
        guard = market_guard_factory(ctx, self.index_symbol)
        emitted: list[dict] = []

        for trade in list(self.trades.values()):
            if trade.state in TERMINAL:
                continue
            bar = self._latest_bar(trade.symbol)
            for event in step(trade, bar, market_guard=guard):
                self.store.save_event(event)
                for sink in self.sinks:
                    try:
                        sink.emit(event, trade.to_dict())
                    except Exception:
                        pass   # one broken sink never blocks the others
                emitted.append(event)
            self.store.save_trade(trade.to_dict())

        for condition in list(self.conditions):
            fired, evidence = evaluate(condition["when"], ctx)
            if fired:
                event = {"trade_id": condition.get("id", "condition"),
                         "symbol": condition.get("symbol", "—"),
                         "direction": condition.get("direction", "—"),
                         "from_state": "ARMED", "to_state": "CONDITION_FIRED",
                         "reason": condition.get("label", "condition met"),
                         "price": None, "bar_time": str(pd.Timestamp.now("UTC")),
                         "details": {"evidence": evidence}}
                self.store.save_event(event)
                for sink in self.sinks:
                    try:
                        sink.emit(event)
                    except Exception:
                        pass
                emitted.append(event)
                if condition.get("once", True):
                    self.conditions.remove(condition)

        return emitted
