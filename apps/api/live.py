"""Live feed layer for the gateway (Phase 7).

- Broadcaster: fan-out of server-sent events to connected dashboard clients.
- build_quotes(): lightweight spot/change/RVOL for the ticker strip.
- LiveAlerts: the Phase 4 AlertEngine armed from the current game plan,
  ticked on an interval, with events broadcast to the stream and persisted.

The pump only does work when someone is listening (quotes) or something is
armed (alerts) — idle costs nothing, which also keeps the test suite fast.
"""

from __future__ import annotations

import asyncio
import json
import time

from alerts.engine import AlertEngine
from alerts.store import Store
from alerts.templates import render_event
from engines.shared.levels import rvol
from engines.shared.providers import BarRequest

DEFAULT_TICKER_SYMBOLS = ["QQQ", "SPY", "^VIX"]


class Broadcaster:
    def __init__(self):
        self.clients: set[asyncio.Queue] = set()

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=200)
        self.clients.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self.clients.discard(q)

    def publish(self, event_type: str, data: dict) -> None:
        msg = f"event: {event_type}\ndata: {json.dumps(data, default=str)}\n\n"
        for q in list(self.clients):
            try:
                q.put_nowait(msg)
            except asyncio.QueueFull:
                self.unsubscribe(q)   # slow consumer: drop, EventSource reconnects


def build_quotes(provider, symbols: list[str]) -> dict:
    out, errors = {}, {}
    for sym in symbols:
        try:
            bars = provider.get_bars(BarRequest(sym, "1d", 40))
            spot = float(bars["close"].iloc[-1])
            prev = float(bars["close"].iloc[-2])
            out[sym] = {
                "spot": round(spot, 2),
                "change_pct": round((spot / prev - 1) * 100, 2),
                "rvol_20d": rvol(bars, 20),
                "bar_time": str(bars.index[-1]),
            }
        except Exception as exc:
            errors[sym] = str(exc)
    return {"quotes": out, "errors": errors, "at": time.time()}


class BroadcastSink:
    """Phase 4 sink interface -> SSE."""

    def __init__(self, broadcaster: Broadcaster):
        self.broadcaster = broadcaster

    def emit(self, event: dict, trade: dict | None = None) -> None:
        self.broadcaster.publish("alert", {
            **event, "message": render_event(event, trade)})


class LiveAlerts:
    def __init__(self, provider, levels_engine, vix_engine,
                 broadcaster: Broadcaster, db_path: str = ":memory:"):
        self.engine = AlertEngine(
            provider, levels_engine, vix_engine,
            store=Store(db_path), sinks=[BroadcastSink(broadcaster)])

    def arm(self, game_plan: dict) -> dict:
        ids = self.engine.arm_setups(game_plan)
        return {"armed": len(ids), "trade_ids": ids}

    def tick(self) -> list[dict]:
        return self.engine.tick()

    def state(self, max_events: int = 50) -> dict:
        return {
            "trades": [t.to_dict() for t in self.engine.trades.values()],
            "events": self.engine.store.events()[-max_events:],
        }

    @property
    def has_active(self) -> bool:
        from alerts.lifecycle import TERMINAL
        return any(t.state not in TERMINAL for t in self.engine.trades.values())


async def pump(state: dict, quote_interval: float, alert_interval: float,
               stop: asyncio.Event) -> None:
    """Background loop: quotes to listeners, alert ticks while armed."""
    last_alert = 0.0
    while not stop.is_set():
        try:
            broadcaster: Broadcaster = state["broadcaster"]
            if broadcaster.clients:
                quotes = await asyncio.to_thread(
                    build_quotes, state["quote_provider"],
                    state.get("ticker_symbols", DEFAULT_TICKER_SYMBOLS))
                broadcaster.publish("quote", quotes)
            live: LiveAlerts = state["live_alerts"]
            if live.has_active and time.time() - last_alert >= alert_interval:
                await asyncio.to_thread(live.tick)   # sink broadcasts events
                last_alert = time.time()
        except Exception:
            pass   # the pump never dies; next loop retries
        try:
            await asyncio.wait_for(stop.wait(), timeout=quote_interval)
        except asyncio.TimeoutError:
            continue
