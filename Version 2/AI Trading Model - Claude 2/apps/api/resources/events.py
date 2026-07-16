"""Events resource: the alert audit trail, read-only.

    GET /api/resources/events                       list
    GET /api/resources/events?trade_id=abc123def0   per-trade history

Events are evidence — there is no create/update/delete surface by design.
Rows get a synthetic sequential `id` (their position in the store's ordered
log) so admin frameworks that key rows by id can render them.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from apps.api.auth import require_api_key
from apps.api.resources.common import (ListParams, apply_list_params,
                                        confluence_state)

router = APIRouter(prefix="/api/resources/events", tags=["events"],
                   dependencies=[Depends(require_api_key)])


def _rows(request: Request) -> list[dict]:
    store = confluence_state(request)["live_alerts"].engine.store
    return [{"id": i + 1, **e} for i, e in enumerate(store.events())]


@router.get("")
def list_events(request: Request, response: Response,
                params: ListParams = Depends()):
    return apply_list_params(_rows(request), params, response)


@router.get("/{event_id}")
def get_event(event_id: int, request: Request):
    rows = _rows(request)
    if 1 <= event_id <= len(rows):
        return rows[event_id - 1]
    raise HTTPException(404, f"event {event_id} not found")
