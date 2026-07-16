"""Resource-style REST routers (the headless CRUD surface).

Conventions match what admin frameworks like Refine expect out of the box:
_start/_end pagination, _sort/_order sorting, field=value filters, and an
X-Total-Count header on list responses. See common.py.
"""

from apps.api.resources.trades import router as trades_router
from apps.api.resources.events import router as events_router
from apps.api.resources.watchlist import router as watchlist_router

ALL_ROUTERS = [trades_router, events_router, watchlist_router]
