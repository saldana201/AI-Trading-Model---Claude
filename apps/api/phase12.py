"""Phase 12 — config + trade-assistant HTTP surface.

Drift-safe integration: everything mounts through one call so main.py
needs exactly two lines, whatever local phase it's at:

    from apps.api.phase12 import install as install_phase12
    install_phase12(app, get_state)          # after `app = FastAPI(...)`

`get_state` is the existing accessor returning the app state dict with
"live_alerts" and "quote_provider" (pass `lambda: app.state`-style adapter
if your local gateway moved to app.state — see PATCHES.md).

Endpoints:
  GET  /api/config                  effective config + source path
  PUT  /api/config                  partial update {"patch": {...}}
  GET  /api/config/presets          named presets
  POST /api/config/presets/{name}   apply a preset
  GET  /api/assistant/plans         trade plans for current snapshot setups
  POST /api/assistant/plan          plan for one posted setup
  POST /api/assistant/fill          {"trade_id", "price", "shares"?}
  GET  /api/assistant/advise/{id}   ?price=... (defaults to latest quote)
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from config import (get_config, update_config, config_path,
                    list_presets, get_preset)
from assistant import build_plan, advise, record_fill


class ConfigPatch(BaseModel):
    patch: dict


class SetupIn(BaseModel):
    setup: dict


class FillIn(BaseModel):
    trade_id: str
    price: float
    shares: int | None = None


def _find_trade(live_alerts, trade_id: str):
    trade = live_alerts.engine.trades.get(trade_id)
    if trade is None:
        raise HTTPException(404, f"unknown trade_id '{trade_id}'")
    return trade


def install(app, get_state, ensure_snapshot=None) -> APIRouter:
    router = APIRouter()

    # ---------------- config ----------------

    @router.get("/api/config")
    def read_config():
        return {"config": get_config(), "path": config_path()}

    @router.put("/api/config")
    def write_config(body: ConfigPatch):
        try:
            result = update_config(body.patch)
        except ValueError as e:
            raise HTTPException(422, str(e))
        _audit(get_state, result["event"])
        return result

    @router.get("/api/config/presets")
    def presets():
        return {"presets": list_presets(),
                "active_config": get_config()}

    @router.post("/api/config/presets/{name}")
    def apply_preset(name: str):
        try:
            patch = get_preset(name)
        except KeyError as e:
            raise HTTPException(404, str(e))
        result = update_config(patch, actor=f"preset:{name}")
        _audit(get_state, result["event"])
        return result

    # ---------------- assistant ----------------

    @router.get("/api/assistant/plans")
    def plans():
        s = get_state()
        snap = (ensure_snapshot(s) if ensure_snapshot
                else s.get("snapshot") or {})
        setups = (snap.get("setups") or {}).get("setups") \
            if isinstance(snap.get("setups"), dict) else snap.get("setups")
        setups = setups or []
        return {"plans": [build_plan(x) for x in setups],
                "chop_warning": (snap.get("setups") or {}).get("chop_warning")
                if isinstance(snap.get("setups"), dict) else None}

    @router.post("/api/assistant/plan")
    def plan_one(body: SetupIn):
        required = {"symbol", "direction", "entry_trigger", "stop",
                    "target_1", "target_2"}
        missing = required - set(body.setup)
        if missing:
            raise HTTPException(422, f"setup missing fields: {sorted(missing)}")
        return build_plan(body.setup)

    @router.post("/api/assistant/fill")
    def fill(body: FillIn):
        s = get_state()
        trade = _find_trade(s["live_alerts"], body.trade_id)
        try:
            event = record_fill(trade, body.price, body.shares)
        except ValueError as e:
            raise HTTPException(409, str(e))
        # persist through the engine's store so the audit trail is complete
        try:
            store = s["live_alerts"].engine.store
            store.save_trade(trade.to_dict())
            store.save_event(event)
        except Exception:
            pass  # store API drift — the in-memory trade is authoritative
        return {"trade": trade.to_dict(), "event": event}

    @router.get("/api/assistant/advise/{trade_id}")
    def advise_trade(trade_id: str, price: float | None = None):
        s = get_state()
        trade = _find_trade(s["live_alerts"], trade_id)
        if price is None:
            price = _latest_price(s, trade.symbol)
            if price is None:
                raise HTTPException(422, "no live quote available — pass "
                                         "?price= explicitly")
        return advise(trade, float(price),
                      market_guard=_build_guard(s["live_alerts"].engine))

    @router.get("/api/assistant/advise")
    def advise_all():
        s = get_state()
        engine = s["live_alerts"].engine
        guard = _build_guard(engine)
        out = []
        for trade in list(engine.trades.values()):
            price = _latest_price(s, trade.symbol)
            if price is None:
                continue
            out.append(advise(trade, price, market_guard=guard))
        return {"advice": out}

    app.include_router(router)
    return router


def _build_guard(engine):
    """Same construction tick() uses — fresh evidence cache per call."""
    try:
        from alerts.engine import AlertContext, market_guard_factory
        return market_guard_factory(AlertContext(engine.levels, engine.vix),
                                    engine.index_symbol)
    except Exception:
        return None


def _latest_price(state: dict, symbol: str) -> float | None:
    try:
        from apps.api.live import build_quotes
        quotes = build_quotes(state["quote_provider"], [symbol])
        q = (quotes.get("quotes") or [{}])[0] if isinstance(quotes, dict) \
            else (quotes or [{}])[0]
        for key in ("price", "last", "close", "spot"):
            if isinstance(q, dict) and q.get(key) is not None:
                return float(q[key])
    except Exception:
        return None
    return None


def _audit(get_state, event: dict) -> None:
    """Broadcast config changes on the SSE feed if a broadcaster exists."""
    try:
        get_state()["broadcaster"].publish("config", event)
    except Exception:
        pass
