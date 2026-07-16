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
import os
import pathlib
import time
from datetime import datetime
from zoneinfo import ZoneInfo

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
                 broadcaster: Broadcaster, db_path: str = ":memory:",
                 data_source: str = "unknown"):
        self.data_source = data_source
        self.engine = AlertEngine(
            provider, levels_engine, vix_engine,
            store=Store(db_path), sinks=[BroadcastSink(broadcaster)])
        # Restart resilience: re-arm every non-terminal trade from the store
        # so a gateway restart never orphans an open position's monitoring.
        from alerts.lifecycle import Trade
        for stored in self.engine.store.load_trades(active_only=True):
            # A trade armed under synthetic prices must never tick against
            # live bars (or vice versa): mismatched/unknown source -> skip.
            if (stored.get("setup_meta") or {}).get("data_source") != data_source:
                continue
            try:
                trade = Trade(**stored)
                self.engine.trades[trade.id] = trade
            except TypeError:
                pass   # schema drift in an old row: skip rather than crash

    def arm(self, game_plan: dict) -> dict:
        ids = self.engine.arm_setups(game_plan)
        for tid in ids:
            trade = self.engine.trades[tid]
            trade.setup_meta["data_source"] = self.data_source
            self.engine.store.save_trade(trade.to_dict())
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


EASTERN = ZoneInfo("America/New_York")


def maybe_autoarm(state: dict, now_et: datetime, arm_time: str | None,
                  build_snapshot_fn, briefs_dir: str | None = None) -> dict | None:
    """Once per day at/after arm_time (ET, "HH:MM"): rebuild the snapshot,
    arm the game plan, write the markdown brief, broadcast, optional Discord.

    Pure-ish and injected for testability: the pump supplies real time and
    the real snapshot builder; tests supply fakes."""
    if not arm_time:
        return None
    try:
        hh, mm = (int(x) for x in arm_time.split(":"))
    except ValueError:
        return None
    if (now_et.hour, now_et.minute) < (hh, mm):
        return None
    today = now_et.date().isoformat()
    if state.get("autoarm_date") == today:
        return None
    state["autoarm_date"] = today   # set first: a failure shouldn't retry-spam

    snap = build_snapshot_fn()
    state["snapshot"] = snap
    state["snapshot_at"] = time.time()
    armed = state["live_alerts"].arm(snap.get("setups") or {})

    from orchestrator.brief import render_brief
    brief = render_brief(snap)
    out_dir = pathlib.Path(briefs_dir or
                           pathlib.Path(__file__).resolve().parents[2] / "briefs")
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{today}.md"
    path.write_text(brief, encoding="utf-8")

    result = {"date": today, "armed": armed.get("armed", 0),
              "brief_path": str(path)}
    broadcaster = state.get("broadcaster")
    if broadcaster is not None:
        broadcaster.publish("brief", result)

    hook = os.environ.get("CONFLUENCE_DISCORD_WEBHOOK")
    if hook:
        try:
            import urllib.request
            body = json.dumps({"content": brief[:1900]}).encode()
            req = urllib.request.Request(
                hook, data=body, headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=10)
            result["discord"] = "sent"
        except Exception as exc:
            result["discord"] = f"failed: {exc}"
    return result


async def pump(state: dict, quote_interval: float, alert_interval: float,
               stop: asyncio.Event) -> None:
    """Background loop: quotes to listeners, alert ticks while armed,
    auto-arm once per day when CONFLUENCE_AUTOARM_ET is set."""
    last_alert = 0.0
    while not stop.is_set():
        try:
            arm_time = os.environ.get("CONFLUENCE_AUTOARM_ET")
            if arm_time:
                from scripts.snapshot import build_snapshot
                await asyncio.to_thread(
                    maybe_autoarm, state, datetime.now(EASTERN), arm_time,
                    build_snapshot)
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
