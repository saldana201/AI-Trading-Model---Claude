"""Phase 12 — the "what do I do right now" advisor.

Given a tracked trade and the latest price, simulate the lifecycle state
machine on a *copy* (never mutating the engine's record — engine ownership
of lifecycle transitions is preserved) and translate the resulting events
into one concrete instruction with the evidence chain attached.

The advisor invents nothing: recommendations are the lifecycle contract
plus config formulas, restated as an action.
"""

from __future__ import annotations

import copy
import datetime as _dt

from alerts.lifecycle import (Trade, step, TERMINAL, WATCHING, TRIGGERED,
                              ACTIVE, TRAILING, TRIMMED_T1)
from config import get_config
from .sizing import size_position


def _clone(trade: Trade) -> Trade:
    return Trade(**copy.deepcopy(trade.to_dict()))


def _bar(price: float) -> dict:
    return {"close": price,
            "time": _dt.datetime.now(_dt.timezone.utc).isoformat()}


def advise(trade: Trade, price: float, market_guard=None,
           cfg: dict | None = None) -> dict:
    """One concrete instruction for this trade at this price."""
    cfg = cfg or get_config()
    long = trade.direction == "long"

    if trade.state in TERMINAL:
        return _rec(trade, price, "done",
                    f"trade is terminal ({trade.state}) — nothing to manage",
                    events=[])

    # simulate: what would the engine do with a bar at this price?
    sim = _clone(trade)
    events = step(sim, _bar(price), market_guard=market_guard)
    kinds = [e["to_state"] for e in events]

    # --- terminal outcomes the simulation reached ---
    if "DETERIORATED" in kinds:
        return _rec(trade, price, "exit",
                    "EXIT NOW — market guard fired: setup conditions broke "
                    "even though the stop is intact", events)
    if "STOPPED" in kinds:
        return _rec(trade, price, "exit",
                    f"EXIT — price is through the stop ({trade.stop_current}); "
                    "if your stop order didn't fill, close at market", events)
    if "CLOSED" in kinds:
        why = events[-1]["reason"]
        return _rec(trade, price, "exit",
                    f"CLOSE remaining position — {why}", events)
    if "INVALIDATED" in kinds:
        return _rec(trade, price, "stand_down",
                    "CANCEL entry orders — trigger failed twice, "
                    "the setup is suspect", events)

    # --- in-flight guidance ---
    if "TRIMMED_T1" in kinds:
        return _rec(trade, price, "trim",
                    f"TRIM ~50% at target 1 ({trade.target_1}) and move the "
                    f"remaining stop to breakeven ({sim.entry_price}); "
                    "trailing engages from here", events)
    if "ACTIVE" in kinds and trade.state == TRIGGERED:
        return _rec(trade, price, "hold",
                    "ENTRY CONFIRMED — trigger held. Ensure your stop is "
                    f"working at {sim.stop_current}", events)
    if "TRIGGERED" in kinds:
        return _rec(trade, price, "enter",
                    f"TRIGGER TAGGED at {trade.entry_trigger} — enter per "
                    "plan, but the level must hold through the next bar; "
                    "a close back through it re-arms the setup", events)
    if "WATCHING" in kinds:
        return _rec(trade, price, "wait",
                    "STAND ASIDE — trigger failed to hold; setup re-armed "
                    f"({sim.trigger_attempts} of "
                    f"{cfg['lifecycle']['max_trigger_attempts']} attempts "
                    "used)", events)

    # no transition: state-specific holding advice
    if trade.state == WATCHING:
        sizing = size_position(trade.entry_trigger, trade.stop, cfg)
        dist = abs(price - trade.entry_trigger)
        return _rec(trade, price, "wait",
                    f"WAIT — price {price} is {round(dist, 2)} from the "
                    f"{trade.entry_trigger} trigger. Pre-stage: "
                    f"{'buy' if long else 'sell'} stop {sizing['shares']} "
                    f"@ {trade.entry_trigger}, protective stop @ {trade.stop}",
                    events, sizing=sizing)
    if trade.state in (ACTIVE, TRIMMED_T1, TRAILING):
        stop_now = sim.stop_current if sim.stop_current is not None else trade.stop
        trail_note = ""
        if trade.state == TRAILING and sim.water_mark is not None:
            raw = (sim.water_mark - trade.trail_distance if long
                   else sim.water_mark + trade.trail_distance)
            eff = (max(raw, stop_now) if long else min(raw, stop_now))
            trail_note = (f"; trailing stop computes to {round(eff, 2)} "
                          f"(water mark {sim.water_mark} "
                          f"{'-' if long else '+'} {trade.trail_distance})")
            stop_now = round(eff, 2)
        return _rec(trade, price, "hold",
                    f"HOLD — stop {stop_now}, next objective "
                    f"{trade.target_1 if trade.state == ACTIVE else trade.target_2}"
                    f"{trail_note}", events,
                    stop_current=stop_now)

    return _rec(trade, price, "hold", f"HOLD — no transition at {price}", events)


def _rec(trade: Trade, price: float, action: str, instruction: str,
         events: list[dict], **extra) -> dict:
    return {
        "trade_id": trade.id, "symbol": trade.symbol,
        "direction": trade.direction, "state": trade.state,
        "price": price, "action": action, "instruction": instruction,
        "evidence": {
            "lifecycle_events": events,
            "levels": {"entry_trigger": trade.entry_trigger,
                       "stop": trade.stop, "stop_current": trade.stop_current,
                       "target_1": trade.target_1, "target_2": trade.target_2,
                       "trail_distance": trade.trail_distance},
        },
        **extra,
    }


def record_fill(trade: Trade, price: float, shares: int | None = None,
                actor: str = "user") -> dict:
    """Log the user's actual fill so management tracks *their* trade.

    Allowed only pre-entry (WATCHING/TRIGGERED): the user is reporting
    reality — "I'm in at X". Post-entry state transitions remain the
    engine's alone. Returns a `manual_fill` audit event.
    """
    if trade.state not in (WATCHING, TRIGGERED):
        raise ValueError(
            f"fill can only be recorded from WATCHING/TRIGGERED "
            f"(trade is {trade.state}) — lifecycle stays engine-owned")
    trade.state = ACTIVE
    trade.entry_price = price
    trade.stop_current = trade.stop
    trade.water_mark = price
    trade.setup_meta = {**(trade.setup_meta or {}),
                        "user_fill": {"price": price, "shares": shares}}
    return {
        "trade_id": trade.id, "symbol": trade.symbol,
        "direction": trade.direction,
        "from_state": WATCHING, "to_state": ACTIVE,
        "reason": "manual_fill: user reported actual entry",
        "price": price,
        "bar_time": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "details": {"actor": actor, "shares": shares},
    }
