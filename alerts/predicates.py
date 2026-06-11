"""Alert predicates (design doc §6).

Armed conditions are JSON predicate trees evaluated every bar by a plain
evaluator — the LLM is never in the latency path. Trees compose with
all / any / not over registered leaf checks, and every evaluation returns
its evidence so the eventual alert can explain exactly what fired.

Example tree (the PRD §11 conditional):

    {"all": [
        {"check": "level_break", "symbol": "QQQ", "level": 719.25, "direction": "above"},
        {"check": "vix_below_pivot"},
        {"check": "rvol_min", "symbol": "QQQ", "min": 1.3}
    ]}
"""

from __future__ import annotations

from typing import Callable


class AlertContext:
    """Per-tick engine access with caching, injected into leaf checks."""

    def __init__(self, levels_engine, vix_engine):
        self.levels = levels_engine
        self.vix = vix_engine
        self._cache: dict = {}

    def vix_levels(self) -> dict:
        if "vix" not in self._cache:
            self._cache["vix"] = self.vix.get_levels()
        return self._cache["vix"]

    def symbol_levels(self, symbol: str) -> dict:
        key = ("lvl", symbol)
        if key not in self._cache:
            self._cache[key] = self.levels.get_levels(symbol)
        return self._cache[key]

    def check_break(self, symbol: str, level: float, direction: str) -> dict:
        key = ("brk", symbol, level, direction)
        if key not in self._cache:
            self._cache[key] = self.levels.check_break(symbol, level, direction)
        return self._cache[key]


# ---------- leaf checks: each returns (bool, evidence_dict) ----------

def _level_break(ctx: AlertContext, symbol: str, level: float, direction: str,
                 min_rvol: float | None = None, require_hold: bool = False, **_):
    res = ctx.check_break(symbol, level, direction)
    ok = res["broken"] and (res["held_through_bar"] if require_hold else True)
    if ok and min_rvol is not None:
        ok = res["rvol"] >= min_rvol
    return ok, res


def _vix_below_pivot(ctx: AlertContext, **_):
    v = ctx.vix_levels()
    ok = v["pivot"] is not None and v["spot"] < v["pivot"]
    return ok, {"vix_spot": v["spot"], "vix_pivot": v["pivot"]}


def _vix_above_pivot(ctx: AlertContext, **_):
    v = ctx.vix_levels()
    ok = v["pivot"] is not None and v["spot"] > v["pivot"]
    return ok, {"vix_spot": v["spot"], "vix_pivot": v["pivot"]}


def _rvol_min(ctx: AlertContext, symbol: str, min: float, **_):
    rv = ctx.symbol_levels(symbol)["rvol_20d"]
    return rv >= min, {"symbol": symbol, "rvol_20d": rv, "min": min}


def _price_above(ctx: AlertContext, symbol: str, level: float, **_):
    spot = ctx.symbol_levels(symbol)["spot"]
    return spot > level, {"symbol": symbol, "spot": spot, "level": level}


def _price_below(ctx: AlertContext, symbol: str, level: float, **_):
    spot = ctx.symbol_levels(symbol)["spot"]
    return spot < level, {"symbol": symbol, "spot": spot, "level": level}


REGISTRY: dict[str, Callable] = {
    "level_break": _level_break,
    "vix_below_pivot": _vix_below_pivot,
    "vix_above_pivot": _vix_above_pivot,
    "rvol_min": _rvol_min,
    "price_above": _price_above,
    "price_below": _price_below,
}


def evaluate(tree: dict, ctx: AlertContext) -> tuple[bool, list[dict]]:
    """Evaluate a predicate tree. Returns (fired, evidence_trail)."""
    if "all" in tree:
        trail = []
        for sub in tree["all"]:
            ok, ev = evaluate(sub, ctx)
            trail.extend(ev)
            if not ok:
                return False, trail
        return True, trail
    if "any" in tree:
        trail = []
        for sub in tree["any"]:
            ok, ev = evaluate(sub, ctx)
            trail.extend(ev)
            if ok:
                return True, trail
        return False, trail
    if "not" in tree:
        ok, ev = evaluate(tree["not"], ctx)
        return not ok, ev
    if "check" in tree:
        name = tree["check"]
        fn = REGISTRY.get(name)
        if fn is None:
            raise ValueError(f"Unknown check: {name}")
        params = {k: v for k, v in tree.items() if k != "check"}
        ok, evidence = fn(ctx, **params)
        return ok, [{"check": name, "ok": ok, **evidence}]
    raise ValueError(f"Malformed predicate node: {tree}")
