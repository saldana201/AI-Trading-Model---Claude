"""Phase 16 — Book HTTP surface.

Drift-safe integration: two lines in main.py, whatever local phase it is at.

    from apps.api.book import install as install_book
    install_book(app, get_state, _ensure_snapshot)

Endpoints:
  GET /api/book                 the current snapshot's setups grouped by
                                direction (long/short) with options and shares
                                as cross-cutting lenses
  GET /api/book/both            compose both directions explicitly, so the
                                short side is populated even when the regime
                                only hunts longs (opt-in: costs a second pass)
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from orchestrator.book import build_book


def install(app, get_state, ensure_snapshot) -> None:
    router = APIRouter()

    def _plan_from_snapshot() -> dict:
        s = get_state()
        snap = ensure_snapshot(s)
        plan = snap.get("setups")
        # snapshot["setups"] is the whole compose() plan dict; tolerate a bare
        # list from older snapshot builders rather than 500 on shape drift.
        if isinstance(plan, list):
            return {"setups": plan}
        return plan or {"setups": []}

    @router.get("/api/book")
    def book():
        return build_book(_plan_from_snapshot())

    @router.get("/api/book/both")
    def book_both():
        """Compose the opposite direction too, so both sides are real.

        The regime gate deliberately picks one side per run; this endpoint runs
        the funnel a second time with the direction forced, purely for the
        book view. It does not arm anything and does not change the game plan.
        """
        s = get_state()
        base = _plan_from_snapshot()
        active = base.get("direction")
        other = "short" if active == "long" else "long"

        composer = s.get("composer")
        if composer is None:
            from scripts.snapshot import build_composer
            composer, *_ = build_composer()

        merged = dict(base)
        setups = list(base.get("setups") or [])
        try:
            alt = composer.compose(force_direction=other)
        except TypeError:
            # composer predates the force_direction kwarg
            raise HTTPException(
                501, "this composer build cannot force a direction per call; "
                     "set gates.force_direction in config instead")
        except Exception as exc:
            raise HTTPException(502, f"could not compose {other}s: {exc}")

        setups.extend(alt.get("setups") or [])
        merged["setups"] = setups
        merged["suppressed"] = list(base.get("suppressed") or []) + \
            list(alt.get("suppressed") or [])
        merged["both_directions"] = True
        out = build_book(merged)
        out["generated_from"]["second_pass"] = other
        return out

    app.include_router(router)
