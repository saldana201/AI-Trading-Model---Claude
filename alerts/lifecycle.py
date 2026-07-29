"""Trade lifecycle state machine (design doc §5.3, PRD §16).

    WATCHING → TRIGGERED → ACTIVE → TRIMMED_T1 → TRAILING → CLOSED
        ↘ INVALIDATED (pre-entry)       ↘ STOPPED / DETERIORATED

Pure functions over bar data: `step(trade, bar, market_guard)` mutates the
trade record and returns the transition events it produced. The engine layer
feeds it bars; tests drive it with crafted sequences. Every event carries the
price, time, and reason — the audit trail is the product.

Management rules implemented (PRD §16):
- entry trigger must HOLD: a trigger bar that closes back through the level
  re-arms once; a second failed trigger invalidates the setup
- pre-entry move through the stop side invalidates
- T1 → trim, stop moves to breakeven, trailing engages (high-water minus
  trail_distance, never below breakeven)
- DETERIORATED: while active, the market guard (VIX reclaims pivot AND index
  loses its trigger) fires an exit-recommended alert even if the stop is intact
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field, asdict

WATCHING, TRIGGERED, ACTIVE = "WATCHING", "TRIGGERED", "ACTIVE"
TRIMMED_T1, TRAILING, CLOSED = "TRIMMED_T1", "TRAILING", "CLOSED"
INVALIDATED, STOPPED, DETERIORATED = "INVALIDATED", "STOPPED", "DETERIORATED"
TERMINAL = {CLOSED, INVALIDATED, STOPPED, DETERIORATED}
MAX_TRIGGER_ATTEMPTS = 2  # historical default; effective value from config


def _max_trigger_attempts() -> int:
    """Phase 12: configurable, defaulting to the historical constant."""
    try:
        from config import get
        return int(get("lifecycle", "max_trigger_attempts"))
    except Exception:
        return MAX_TRIGGER_ATTEMPTS


@dataclass
class Trade:
    symbol: str
    direction: str            # "long" | "short"
    entry_trigger: float
    stop: float
    target_1: float
    target_2: float
    trail_distance: float     # typically 1.5 * ATR14 at arm time
    min_rvol: float = 0.0
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])
    state: str = WATCHING
    entry_price: float | None = None
    stop_current: float | None = None
    water_mark: float | None = None   # high-water (long) / low-water (short)
    trigger_attempts: int = 0
    # Phase 23: the level that abandons a PENDING setup. Distinct from `stop`,
    # which exits a LIVE position. Historically these were the same level, which
    # meant ordinary noise against a not-yet-entered setup discarded it — 96% of
    # NO_FILLs on real data. None = never invalidate pre-entry (wait for the
    # trigger or the horizon). Defaults to `stop` for backwards compatibility.
    preentry_invalidation: float | None = None
    setup_meta: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def _event(trade: Trade, to_state: str, bar: dict, reason: str, **details) -> dict:
    return {
        "trade_id": trade.id, "symbol": trade.symbol, "direction": trade.direction,
        "from_state": trade.state, "to_state": to_state, "reason": reason,
        "price": bar["close"], "bar_time": str(bar["time"]), "details": details,
    }


def step(trade: Trade, bar: dict, market_guard=None) -> list[dict]:
    """Advance one bar. bar = {close, high, low, time, rvol?}.

    market_guard(direction) -> (deteriorated: bool, evidence: dict) | None.
    Returns the list of transition events (possibly several in one bar)."""
    if trade.state in TERMINAL:
        return []

    long = trade.direction == "long"
    close = float(bar["close"])
    rvol = float(bar.get("rvol", 99.0))
    events: list[dict] = []

    def move(to_state: str, reason: str, **details):
        events.append(_event(trade, to_state, bar, reason, **details))
        trade.state = to_state

    beyond = (lambda lvl: close > lvl) if long else (lambda lvl: close < lvl)
    against = (lambda lvl: close < lvl) if long else (lambda lvl: close > lvl)

    # ---------- pre-entry ----------
    if trade.state == WATCHING:
        # Phase 23: abandon a pending setup only at its own invalidation level.
        # When None, a pending setup is never invalidated by price — you are not
        # in the trade, so adverse movement has cost nothing; wait for the
        # trigger or let the horizon expire it.
        inval = (trade.preentry_invalidation if trade.preentry_invalidation
                 is not None else trade.stop)
        if inval is not None and against(inval):
            move(INVALIDATED, "price moved through the invalidation level "
                              "before entry", invalidation=inval)
        elif beyond(trade.entry_trigger) and rvol >= trade.min_rvol:
            trade.trigger_attempts += 1
            move(TRIGGERED, "entry trigger broken",
                 entry_trigger=trade.entry_trigger, rvol=rvol,
                 attempt=trade.trigger_attempts)
            trade.entry_price = close
            trade.stop_current = trade.stop
            trade.water_mark = close
        return events

    if trade.state == TRIGGERED:
        if beyond(trade.entry_trigger):
            move(ACTIVE, "trigger held through the next bar",
                 entry_price=trade.entry_price)
            # fall through: an entry bar can also tag T1/stop
        else:
            if trade.trigger_attempts >= _max_trigger_attempts():
                move(INVALIDATED, "trigger failed twice — setup is suspect",
                     attempts=trade.trigger_attempts)
            else:
                move(WATCHING, "trigger failed to hold — re-armed once",
                     attempts=trade.trigger_attempts)
                trade.entry_price = None
                trade.stop_current = None
                trade.water_mark = None
            return events

    # ---------- in-trade ----------
    if trade.state in (ACTIVE, TRAILING):
        trade.water_mark = (max(trade.water_mark, close) if long
                            else min(trade.water_mark, close))

        if market_guard is not None:
            bad, evidence = market_guard(trade.direction)
            if bad:
                move(DETERIORATED,
                     "market guard fired — setup conditions broke; exit recommended",
                     **evidence)
                return events

        if trade.state == ACTIVE:
            if against(trade.stop_current):
                move(STOPPED, "stop hit", stop=trade.stop_current)
                return events
            if beyond(trade.target_1):
                move(TRIMMED_T1, "target 1 reached — trim and move stop to breakeven",
                     target_1=trade.target_1, new_stop=trade.entry_price)
                trade.stop_current = trade.entry_price
                move(TRAILING, "trailing engaged",
                     trail_distance=trade.trail_distance)

        if trade.state == TRAILING:
            trail = (trade.water_mark - trade.trail_distance if long
                     else trade.water_mark + trade.trail_distance)
            trail = max(trail, trade.stop_current) if long else min(trail, trade.stop_current)
            if beyond(trade.target_2):
                move(CLOSED, "target 2 reached — full exit", target_2=trade.target_2)
            elif against(trail):
                at_be = abs(trail - (trade.entry_price or 0)) < 1e-9
                move(CLOSED,
                     "breakeven stop hit after trim" if at_be else "trailing stop hit",
                     trail_level=round(trail, 4), water_mark=trade.water_mark)

    return events
