"""Phase 29 — honest-mode API surface.

Mount with the drift-safe pattern (two lines appended to main.py):

    from apps.api.honest import install as install_honest
    install_honest(app, get_state, _ensure_snapshot)

Endpoints:
  GET /api/calibration            what the backtest actually measured
  GET /api/benchmark-context      how the system compares to buy-and-hold
  GET /api/setups/annotated       current setups with calibration attached
"""
from __future__ import annotations
from fastapi import APIRouter
from orchestrator.calibration import (load_calibration, disclose,
                                      benchmark_context, annotate_setup)


def install(app, get_state, ensure_snapshot) -> None:
    router = APIRouter()

    @router.get("/api/calibration")
    def calibration():
        cal = load_calibration()
        return {**cal,
                "bands": {b: disclose_band(b, cal)
                          for b in ("<6.5", "6.5-7.5", ">=7.5")}}

    def disclose_band(band, cal):
        mid = {"<6.5": 6.0, "6.5-7.5": 7.0, ">=7.5": 8.0}[band]
        return disclose(mid, cal)

    @router.get("/api/benchmark-context")
    def bench():
        return benchmark_context()

    @router.get("/api/setups/annotated")
    def annotated():
        s = get_state()
        snap = ensure_snapshot(s)
        plan = snap.get("setups") or {}
        setups = plan.get("setups") if isinstance(plan, dict) else (plan or [])
        cal = load_calibration()
        return {"benchmark_context": benchmark_context(cal),
                "setups": [annotate_setup(x, cal) for x in (setups or [])]}

    app.include_router(router)
