"""Phase 9 — resource router registry.

Drift-safe integration, same pattern as `apps/api/phase12.py`: one call
mounts everything, so `main.py` needs two lines instead of a whole-file
replacement.

    from apps.api.resources import install as install_resources
    install_resources(app, get_state)
"""

from __future__ import annotations

import os

from fastapi.middleware.cors import CORSMiddleware

from apps.api.resources import trades, events, watchlist

ROUTERS = (trades.router, events.router, watchlist.router)


def cors_origins() -> list[str]:
    raw = os.environ.get("CONFLUENCE_CORS_ORIGINS",
                         "http://localhost:3000,http://127.0.0.1:3000")
    return [o.strip() for o in raw.split(",") if o.strip()]


def install(app, get_state=None, add_cors: bool = False):
    """Mount the resource routers and expose state via `app.state`.

    `app.state.confluence` is the accessor the routers use; `get_state()`
    remains the back-compat path for existing endpoints and scripts, so
    both views point at the same dict.
    """
    if get_state is not None:
        try:
            app.state.confluence = get_state()
        except Exception:
            # state may not be constructible at import time; the lifespan
            # handler will set it before any request is served
            pass

    if add_cors:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins(),
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
            expose_headers=["X-Total-Count"],   # Refine reads this for paging
        )

    for router in ROUTERS:
        app.include_router(router)
    return app
