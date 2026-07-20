"""Phase 9 — API key authentication.

`CONFLUENCE_API_KEY` set  -> protected routes require the key via
                             `X-API-Key: <key>` or `Authorization: Bearer <key>`.
`CONFLUENCE_API_KEY` unset -> auth disabled with a logged warning, so the
                             local dev flow is unchanged.

Comparison is constant-time: a timing side channel on an API key is a real
(if unglamorous) leak.
"""

from __future__ import annotations

import hmac
import logging
import os

from fastapi import Header, HTTPException

_log = logging.getLogger("confluence.auth")
_warned = False


def api_key() -> str | None:
    key = os.environ.get("CONFLUENCE_API_KEY", "").strip()
    return key or None


def auth_mode() -> str:
    return "api_key" if api_key() else "disabled"


def _warn_once() -> None:
    global _warned
    if not _warned:
        _log.warning("CONFLUENCE_API_KEY is unset — API authentication is "
                     "DISABLED. Set it before exposing this gateway.")
        _warned = True


def require_api_key(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    authorization: str | None = Header(default=None),
) -> None:
    """FastAPI dependency. No-op when auth is disabled."""
    expected = api_key()
    if expected is None:
        _warn_once()
        return

    presented = x_api_key
    if not presented and authorization:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() == "bearer":
            presented = token.strip()

    if not presented:
        raise HTTPException(
            401, "missing API key — send X-API-Key or Authorization: Bearer",
            headers={"WWW-Authenticate": "Bearer"})

    if not hmac.compare_digest(presented, expected):
        raise HTTPException(401, "invalid API key",
                            headers={"WWW-Authenticate": "Bearer"})
