"""Watchlist resource: pinned sector -> ticker mapping as REST.

    GET    /api/resources/watchlist          list  [{id, sector_etf, tickers}]
    GET    /api/resources/watchlist/{etf}    one
    POST   /api/resources/watchlist          {"sector_etf": "SMH", "tickers": [...]}
    PUT    /api/resources/watchlist/{etf}    replace a sector's tickers
    DELETE /api/resources/watchlist/{etf}    remove the custom entry

Writes go to watchlist.json (env CONFLUENCE_WATCHLIST overrides the path,
otherwise repo root — the same file composer.load_watchlist() merges over
its defaults). Edits take effect on the next snapshot rebuild; the response
says so explicitly instead of pretending to be instant.

Records are keyed by sector ETF symbol: id == sector_etf.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import threading

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, field_validator

from apps.api.auth import require_api_key
from apps.api.resources.common import ListParams, apply_list_params

router = APIRouter(prefix="/api/resources/watchlist", tags=["watchlist"],
                   dependencies=[Depends(require_api_key)])

_LOCK = threading.Lock()
_SYMBOL = re.compile(r"^[A-Z0-9.^-]{1,10}$")
HINT = "takes effect on next snapshot rebuild (POST /api/snapshot?refresh=1)"


def _path() -> pathlib.Path:
    env = os.environ.get("CONFLUENCE_WATCHLIST")
    if env:
        return pathlib.Path(env)
    # repo root, matching orchestrator.composer.load_watchlist resolution
    return pathlib.Path(__file__).resolve().parents[3] / "watchlist.json"


def _read() -> dict[str, list[str]]:
    p = _path()
    if not p.exists():
        return {}
    return {k.upper(): [s.upper() for s in v]
            for k, v in json.loads(p.read_text()).items()}


def _write(data: dict[str, list[str]]) -> None:
    _path().write_text(json.dumps(data, indent=2) + "\n")


def _record(etf: str, tickers: list[str]) -> dict:
    return {"id": etf, "sector_etf": etf, "tickers": tickers,
            "ticker_count": len(tickers)}


class WatchlistEntry(BaseModel):
    sector_etf: str
    tickers: list[str]

    @field_validator("sector_etf")
    @classmethod
    def _etf(cls, v: str) -> str:
        v = v.strip().upper()
        if not _SYMBOL.match(v):
            raise ValueError(f"invalid symbol: {v!r}")
        return v

    @field_validator("tickers")
    @classmethod
    def _tickers(cls, v: list[str]) -> list[str]:
        out = []
        for s in v:
            s = s.strip().upper()
            if not _SYMBOL.match(s):
                raise ValueError(f"invalid ticker: {s!r}")
            out.append(s)
        return list(dict.fromkeys(out))   # dedupe, keep order


class TickersOnly(BaseModel):
    tickers: list[str]

    _tickers = field_validator("tickers")(WatchlistEntry._tickers.__func__)


@router.get("")
def list_watchlist(response: Response, params: ListParams = Depends()):
    rows = [_record(k, v) for k, v in _read().items()]
    return apply_list_params(rows, params, response)


@router.get("/{etf}")
def get_entry(etf: str):
    data = _read()
    etf = etf.upper()
    if etf not in data:
        raise HTTPException(404, f"{etf} not in watchlist.json")
    return _record(etf, data[etf])


@router.post("", status_code=201)
def create_entry(entry: WatchlistEntry):
    with _LOCK:
        data = _read()
        if entry.sector_etf in data:
            raise HTTPException(
                409, f"{entry.sector_etf} exists; use PUT to replace it")
        data[entry.sector_etf] = entry.tickers
        _write(data)
    return {**_record(entry.sector_etf, entry.tickers), "note": HINT}


@router.put("/{etf}")
def replace_entry(etf: str, body: TickersOnly):
    etf = etf.upper()
    if not _SYMBOL.match(etf):
        raise HTTPException(422, f"invalid symbol: {etf!r}")
    with _LOCK:
        data = _read()
        data[etf] = body.tickers
        _write(data)
    return {**_record(etf, body.tickers), "note": HINT}


@router.delete("/{etf}")
def delete_entry(etf: str):
    etf = etf.upper()
    with _LOCK:
        data = _read()
        if etf not in data:
            raise HTTPException(404, f"{etf} not in watchlist.json")
        del data[etf]
        _write(data)
    return {"id": etf, "deleted": True, "note": HINT}
