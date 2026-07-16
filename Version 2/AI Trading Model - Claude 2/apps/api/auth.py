"""API key auth for the gateway (fixes known issue: gateway had no auth).

Design: one shared secret via the CONFLUENCE_API_KEY environment variable.

- Key SET      -> protected routes require it (X-API-Key header, or
                  Authorization: Bearer <key>). Wrong/missing key -> 401.
- Key NOT set  -> auth is disabled and a warning is logged once. This keeps
                  local dev friction-free and degrades loudly, not silently —
                  the same philosophy as the chat service's two modes.

Usage:
    from apps.api.auth import require_api_key
    router = APIRouter(dependencies=[Depends(require_api_key)])

The comparison uses secrets.compare_digest to avoid timing side channels.
This is deliberately not a user system: Confluence is single-operator today.
When multi-user matters, swap this dependency for JWT/OIDC — the routers
don't change, only this module does.
"""

from __future__ import annotations

import logging
import os
import secrets

from fastapi import HTTPException, Request

log = logging.getLogger("confluence.auth")
_warned = False


def configured_key() -> str | None:
    return os.environ.get("CONFLUENCE_API_KEY") or None


def _extract_key(request: Request) -> str | None:
    key = request.headers.get("x-api-key")
    if key:
        return key
    authz = request.headers.get("authorization", "")
    if authz.lower().startswith("bearer "):
        return authz[7:].strip()
    return None


async def require_api_key(request: Request) -> None:
    """FastAPI dependency guarding a route or router."""
    global _warned
    expected = configured_key()
    if expected is None:
        if not _warned:
            log.warning(
                "CONFLUENCE_API_KEY is not set — API auth is DISABLED. "
                "Set it before exposing the gateway beyond localhost.")
            _warned = True
        return
    provided = _extract_key(request)
    if provided is None or not secrets.compare_digest(provided, expected):
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid API key. Send X-API-Key or "
                   "Authorization: Bearer <key>.")
