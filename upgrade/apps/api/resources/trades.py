"""Phase 9 — `trades` resource.

Read the lifecycle store as a conventional REST collection. Writes are
deliberately narrow:

  * PATCH accepts only a **terminal** state (manual close) plus an optional
    note. Non-terminal transitions stay the engine's job — the alert
    lifecycle owns WATCHING -> TRIGGERED -> ACTIVE -> ... and a UI must not
    be able to fake one. Same glass-box constraint as the rest of the system.
  * Every manual change writes a `manual_update` audit event.
  * No DELETE. Trades are an audit trail.
"""

from __future__ import annotations

import datetime as _dt

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from alerts.lifecycle import TERMINAL
from apps.api.auth import require_api_key
from apps.api.resources.common import collection

router = APIRouter(
                   dependencies=[Depends(require_api_key)])


class TradePatch(BaseModel):
    state: str | None = None
    note: str | None = None


def _store(request: Request):
    return request.app.state.confluence["live_alerts"].engine.store


def _rows(request: Request) -> list[dict]:
    rows = _store(request).load_trades(active_only=False)
    for r in rows:
        r.setdefault("id", r.get("trade_id"))
    return rows


@router.get("/api/resources/trades")
def list_trades(request: Request, response: Response):
    return collection(_rows(request), request, response)


@router.get("/api/resources/trades/{trade_id}")
def get_trade(trade_id: str, request: Request):
    row = next((r for r in _rows(request) if r.get("id") == trade_id), None)
    if row is None:
        raise HTTPException(404, f"unknown trade '{trade_id}'")
    return row


@router.patch("/api/resources/trades/{trade_id}")
def patch_trade(trade_id: str, body: TradePatch, request: Request):
    store = _store(request)
    row = next((r for r in _rows(request) if r.get("id") == trade_id), None)
    if row is None:
        raise HTTPException(404, f"unknown trade '{trade_id}'")

    if body.state is not None and body.state not in TERMINAL:
        raise HTTPException(
            422, f"'{body.state}' is not a terminal state. Manual writes may "
                 f"only close a trade ({', '.join(sorted(TERMINAL))}); "
                 "lifecycle transitions are engine-owned.")

    before = row.get("state")
    if body.state:
        row["state"] = body.state
    if body.note is not None:
        row["note"] = body.note
    store.save_trade(row)

    event = {
        "trade_id": trade_id, "symbol": row.get("symbol"),
        "direction": row.get("direction"),
        "from_state": before, "to_state": row.get("state"),
        "reason": "manual_update: operator edit via admin",
        "price": row.get("entry_price"),
        "bar_time": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "details": {"note": body.note},
    }
    store.save_event(event)

    # keep the in-memory engine consistent with what the store now says
    engine = request.app.state.confluence["live_alerts"].engine
    live = engine.trades.get(trade_id)
    if live is not None and body.state:
        live.state = body.state

    return row
