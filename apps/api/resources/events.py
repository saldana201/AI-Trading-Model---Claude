"""Phase 9 — `events` resource: the audit trail, read-only.

Lifecycle transitions, `manual_update` operator edits, `manual_fill` user
entries, and `config_update` changes all land here. Nothing mutates it over
HTTP — an audit log you can edit is not an audit log.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from apps.api.auth import require_api_key
from apps.api.resources.common import collection

router = APIRouter(
                   dependencies=[Depends(require_api_key)])


def _rows(request: Request) -> list[dict]:
    store = request.app.state.confluence["live_alerts"].engine.store
    rows = store.events()
    for i, r in enumerate(rows):
        # events have no natural key; a stable index keeps Refine happy
        r.setdefault("id", str(i))
    return rows


@router.get("/api/resources/events")
def list_events(request: Request, response: Response):
    return collection(_rows(request), request, response)


@router.get("/api/resources/events/{event_id}")
def get_event(event_id: str, request: Request):
    row = next((r for r in _rows(request) if str(r.get("id")) == event_id), None)
    if row is None:
        raise HTTPException(404, f"unknown event '{event_id}'")
    return row
