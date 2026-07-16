"""Shared plumbing for resource routers.

The list endpoints speak the "simple REST" dialect Refine's data providers
(and most admin frameworks) expect:

    GET /api/resources/trades?_start=0&_end=10&_sort=updated_at&_order=desc
    GET /api/resources/trades?state=TRIGGERED&symbol=NVDA

- _start/_end   slice-style pagination (end exclusive)
- _sort/_order  single-key sort, asc|desc
- any other query param is an equality filter on that field
- the response carries the pre-pagination total in the X-Total-Count header
  (exposed via CORS so the browser can read it)

Everything operates on plain list[dict] in Python. At current scale (a
prototype's SQLite tables) that is honest and sufficient; when the store
moves to TimescaleDB, push these into SQL and keep the HTTP contract.
"""

from __future__ import annotations

from typing import Any

from fastapi import Query, Request, Response

RESERVED = {"_start", "_end", "_sort", "_order"}


def confluence_state(request: Request) -> dict:
    """The gateway's per-process state, initialized lazily if the lifespan
    hasn't run (TestClient without a context manager). Deferred import
    avoids a circular dependency on apps.api.main."""
    if not hasattr(request.app.state, "confluence"):
        from apps.api.main import _ensure_state
        return _ensure_state(request.app)
    return request.app.state.confluence


class ListParams:
    """Extracts pagination/sort/filter from the query string."""

    def __init__(self, request: Request,
                 _start: int = Query(0, ge=0),
                 _end: int = Query(100, ge=1),
                 _sort: str | None = None,
                 _order: str = Query("asc", pattern="^(asc|desc)$")):
        self.start, self.end = _start, _end
        self.sort, self.order = _sort, _order
        self.filters: dict[str, str] = {
            k: v for k, v in request.query_params.items()
            if k not in RESERVED}


def _matches(row: dict, filters: dict[str, str]) -> bool:
    for field, want in filters.items():
        have = row.get(field)
        if have is None:
            return False
        if isinstance(have, bool):
            if str(have).lower() != want.lower():
                return False
        elif str(have) != want:
            return False
    return True


def apply_list_params(rows: list[dict], p: ListParams,
                      response: Response) -> list[dict]:
    """Filter -> sort -> count -> paginate. Sets X-Total-Count."""
    if p.filters:
        rows = [r for r in rows if _matches(r, p.filters)]
    if p.sort:
        def key(r: dict) -> Any:
            v = r.get(p.sort)
            # None sorts last regardless of direction; mixed types sort as str
            return (v is None, v if isinstance(v, (int, float)) else str(v))
        rows = sorted(rows, key=key, reverse=(p.order == "desc"))
    response.headers["X-Total-Count"] = str(len(rows))
    return rows[p.start:p.end]
