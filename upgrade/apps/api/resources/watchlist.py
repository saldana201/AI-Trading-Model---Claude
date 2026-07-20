"""Phase 9 — `watchlist` resource: full CRUD over `watchlist.json`.

Each row is a sector ETF and its symbol list; the `_pinned` key surfaces as
the pseudo-sector `PINNED` so pinned tickers are editable from the same
surface. Symbols are validated, upper-cased, and deduped.

Edits apply on the **next snapshot rebuild** — the composer reads the file
at construction. Responses say so explicitly rather than implying a change
took effect immediately.
"""

from __future__ import annotations

import json
import os

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from apps.api.auth import require_api_key
from apps.api.resources.common import collection

router = APIRouter(
                   dependencies=[Depends(require_api_key)])

PINNED_ROW = "PINNED"
NOTE = "applies on the next snapshot rebuild"


class WatchlistBody(BaseModel):
    id: str | None = None          # sector ETF, or "PINNED"
    symbols: list[str] = []


def path() -> str:
    return os.environ.get("CONFLUENCE_WATCHLIST", "watchlist.json")


def _read() -> dict:
    p = path()
    if not os.path.exists(p):
        return {}
    with open(p, "r", encoding="utf-8") as f:
        text = f.read().strip()
    return json.loads(text) if text else {}


def _write(data: dict) -> None:
    p = path()
    tmp = f"{p}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
    os.replace(tmp, p)


def _clean(symbols: list[str]) -> list[str]:
    out: list[str] = []
    for s in symbols:
        s = str(s).strip().upper()
        if not s:
            continue
        if not s.replace(".", "").replace("-", "").replace("^", "").isalnum():
            raise HTTPException(422, f"invalid symbol '{s}'")
        if s not in out:
            out.append(s)
    return out


def _rows() -> list[dict]:
    data = _read()
    rows = [{"id": PINNED_ROW, "symbols": data.get("_pinned", []),
             "pinned": True}]
    rows += [{"id": k, "symbols": v, "pinned": False}
             for k, v in sorted(data.items()) if not k.startswith("_")]
    return rows


@router.get("/api/resources/watchlist")
def list_watchlist(request: Request, response: Response):
    return collection(_rows(), request, response)


@router.get("/api/resources/watchlist/{row_id}")
def get_row(row_id: str):
    row = next((r for r in _rows() if r["id"] == row_id.upper()), None)
    if row is None:
        raise HTTPException(404, f"unknown watchlist entry '{row_id}'")
    return row


@router.post("/api/resources/watchlist")
def create_row(body: WatchlistBody):
    if not body.id:
        raise HTTPException(422, "id (sector ETF, or PINNED) is required")
    key = body.id.strip().upper()
    data = _read()
    store_key = "_pinned" if key == PINNED_ROW else key
    if store_key in data:
        raise HTTPException(409, f"'{key}' already exists — use PATCH")
    data[store_key] = _clean(body.symbols)
    _write(data)
    return {"id": key, "symbols": data[store_key], "note": NOTE}


@router.patch("/api/resources/watchlist/{row_id}")
def update_row(row_id: str, body: WatchlistBody):
    key = row_id.strip().upper()
    data = _read()
    store_key = "_pinned" if key == PINNED_ROW else key
    if store_key not in data and key != PINNED_ROW:
        raise HTTPException(404, f"unknown watchlist entry '{key}'")
    data[store_key] = _clean(body.symbols)
    _write(data)
    return {"id": key, "symbols": data[store_key], "note": NOTE}


@router.delete("/api/resources/watchlist/{row_id}")
def delete_row(row_id: str):
    key = row_id.strip().upper()
    data = _read()
    store_key = "_pinned" if key == PINNED_ROW else key
    if store_key not in data:
        raise HTTPException(404, f"unknown watchlist entry '{key}'")
    del data[store_key]
    _write(data)
    return {"id": key, "deleted": True, "note": NOTE}
