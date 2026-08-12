"""Phase 34 — fundamentals confluence API surface.

Mount with the drift-safe pattern (two lines appended to main.py):

    from apps.api.fundamentals import install as install_fundamentals
    install_fundamentals(app, get_state, _ensure_snapshot)

Endpoints:
  GET /api/fundamentals/{symbol}   assessment for one symbol
  GET /api/setups/suppressed       suppressed setups + the gate reason

NOTE ON THE PATTERN: the MOUNT shape is copied from apps/api/honest.py, but
the AUTH comes from apps/api/resources/trades.py — honest.py carries no auth
dependency, and copying it wholesale would silently leave these routes open.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from apps.api.auth import require_api_key
from engines.fundamentals_mcp.logic import (
    FundamentalsEngine, SyntheticFundamentals, YFinanceFundamentals)
from orchestrator import fundamentals_confluence


def _engine(state) -> FundamentalsEngine:
    """Reuse the gateway's engine when it has one, so the API and the
    composer read the same cache rather than opening a second one."""
    existing = getattr(state, "fundamentals", None)
    if isinstance(existing, FundamentalsEngine):
        return existing
    composer = getattr(state, "composer", None)
    if composer is not None and isinstance(
            getattr(composer, "fundamentals", None), FundamentalsEngine):
        return composer.fundamentals
    import os
    return FundamentalsEngine(
        SyntheticFundamentals() if os.environ.get("CONFLUENCE_DATA") == "YFINANCE"
        else YFinanceFundamentals())


def install(app, get_state, ensure_snapshot) -> None:
    router = APIRouter(dependencies=[Depends(require_api_key)])

    @router.get("/api/fundamentals/{symbol}")
    def fundamentals(symbol: str, direction: str = "long"):
        if direction not in ("long", "short"):
            raise HTTPException(400, "direction must be 'long' or 'short'")
        snapshot = _engine(get_state()).get_snapshot(symbol.upper())
        assessment = fundamentals_confluence.assess(snapshot, direction)
        verdict = fundamentals_confluence.gate({}, assessment)
        return {"symbol": symbol.upper(), "direction": direction,
                "snapshot": snapshot, "assessment": assessment, "gate": verdict}

    @router.get("/api/setups/suppressed")
    def suppressed():
        state = get_state()
        snap = ensure_snapshot(state)
        plan = snap.get("setups") or {}
        if not isinstance(plan, dict):
            plan = {}
        rows = plan.get("suppressed") or []
        return {
            "direction": plan.get("direction"),
            "no_trade": bool(plan.get("no_trade")),
            "count": len(rows),
            "suppressed": rows,
            "note": ("setups the gates removed, with the reason each was "
                     "removed. Avoided trades are output, not absence of it."),
        }

    app.include_router(router)
