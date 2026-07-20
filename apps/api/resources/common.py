"""Phase 9 — the simple-REST dialect admin frameworks expect.

Refine's simple-REST data provider speaks:

    ?_start=0&_end=25          pagination (end is exclusive)
    ?_sort=field&_order=desc   sorting
    ?field=value               equality filters
    X-Total-Count: 137         pre-pagination total, in the response header

Kept in one small module so the entire HTTP contract is inspectable —
same glass-box philosophy as the engines.
"""

from __future__ import annotations

from typing import Any

from fastapi import Request, Response

RESERVED = {"_start", "_end", "_sort", "_order"}


def apply_filters(rows: list[dict], params: dict[str, str]) -> list[dict]:
    """Equality filters on any non-reserved query param.

    Values are compared as strings so `?state=ACTIVE` and `?symbol=NVDA`
    work without per-field type declarations. Unknown fields match nothing
    rather than silently returning everything — a typo'd filter should
    look empty, not look unfiltered.
    """
    out = rows
    for key, value in params.items():
        if key in RESERVED or value == "":
            continue
        out = [r for r in out if str(r.get(key, "")) == value]
    return out


def apply_sort(rows: list[dict], sort: str | None, order: str | None) -> list[dict]:
    if not sort:
        return rows
    reverse = (order or "asc").lower() == "desc"

    def key(row: dict):
        v = row.get(sort)
        # None sorts last in either direction; mixed types compare as strings
        return (v is None, v if isinstance(v, (int, float)) else str(v or ""))

    return sorted(rows, key=key, reverse=reverse)


def paginate(rows: list[dict], start: int | None, end: int | None) -> list[dict]:
    if start is None and end is None:
        return rows
    return rows[(start or 0):(end if end is not None else len(rows))]


def collection(rows: list[dict], request: Request, response: Response) -> list[dict]:
    """Filter -> sort -> paginate, setting X-Total-Count pre-pagination."""
    params = dict(request.query_params)
    rows = apply_filters(rows, params)
    rows = apply_sort(rows, params.get("_sort"), params.get("_order"))
    response.headers["X-Total-Count"] = str(len(rows))
    return paginate(rows, _int(params.get("_start")), _int(params.get("_end")))


def _int(v: Any) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None
