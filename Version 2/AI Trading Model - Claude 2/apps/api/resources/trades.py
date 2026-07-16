"""Trades resource: the alert lifecycle store as REST.

    GET   /api/resources/trades          list (paginated/filtered/sorted)
    GET   /api/resources/trades/{id}     one
    PATCH /api/resources/trades/{id}     manual close/invalidate or annotate

Glass-box constraint: the lifecycle state machine owns transitions, so PATCH
deliberately does NOT accept arbitrary state writes. It allows exactly two
operator actions — moving a trade to a terminal state (a discretionary manual
close) and attaching a note. Anything else must happen through the engine so
every state change stays traceable to evidence. There is no DELETE: trades
are an audit trail.
"""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from alerts.lifecycle import TERMINAL
from apps.api.auth import require_api_key
from apps.api.resources.common import (ListParams, apply_list_params,
                                        confluence_state)

router = APIRouter(prefix="/api/resources/trades", tags=["trades"],
                   dependencies=[Depends(require_api_key)])


def _store(request: Request):
    return confluence_state(request)["live_alerts"].engine.store


def _rows(store) -> list[dict]:
    return store.load_trades(active_only=False)


@router.get("")
def list_trades(request: Request, response: Response,
                params: ListParams = Depends()):
    return apply_list_params(_rows(_store(request)), params, response)


@router.get("/{trade_id}")
def get_trade(trade_id: str, request: Request):
    for row in _rows(_store(request)):
        if row.get("id") == trade_id:
            return row
    raise HTTPException(404, f"trade {trade_id} not found")


class TradePatch(BaseModel):
    state: str | None = None   # terminal states only (manual close)
    note: str | None = None


@router.patch("/{trade_id}")
def patch_trade(trade_id: str, patch: TradePatch, request: Request):
    store = _store(request)
    row = next((r for r in _rows(store) if r.get("id") == trade_id), None)
    if row is None:
        raise HTTPException(404, f"trade {trade_id} not found")

    changed = {}
    if patch.state is not None:
        if patch.state not in TERMINAL:
            raise HTTPException(
                422, f"state must be terminal ({sorted(TERMINAL)}); "
                     "non-terminal transitions belong to the alert engine")
        changed["state"] = row["state"] = patch.state
    if patch.note is not None:
        changed["note"] = row["note"] = patch.note
    if not changed:
        raise HTTPException(422, "nothing to update: send state and/or note")

    store.save_trade(row)
    store.save_event({"trade_id": trade_id, "type": "manual_update",
                      "changed": changed, "at": time.time()})

    # keep the in-memory engine view consistent with the store
    engine = confluence_state(request)["live_alerts"].engine
    trade = engine.trades.get(trade_id)
    if trade is not None and patch.state is not None:
        trade.state = patch.state
    return row
