"""Fundamentals confluence (design doc §4.8, PRD §14-15).

Deterministic. No LLM, no network, stdlib only. Turns the fundamentals-mcp
snapshot into a graded assessment plus an earnings-window gate.

Three things this module refuses to do, on purpose
--------------------------------------------------
1. It never scores missing data as zero. A component with no input is
   reported in ``unavailable`` with a reason and dropped from the weighted
   average, and the renormalization is recorded in ``evidence``. "Not
   measured" and "measured and bad" are different claims; conflating them
   is how a grade starts lying.

2. It never reads ``snapshot["in_earnings_window"]``. That flag is the
   engine's own display flag at a fixed 7 days (engines/fundamentals_mcp/
   logic.py::EARNINGS_WINDOW_DAYS) and drives ``setup["earnings_flag"]``
   and the legacy scoring penalty. The gate computes its own window from
   ``days_to_earnings`` so the two can be configured apart without either
   silently overriding the other.

3. It never invents an input. The real snapshot carries no margin trend, no
   guidance, no sponsorship *trend* and no history (see FIELD NOTES below),
   so profitability, valuation and sponsorship are single point-in-time
   readings and are labelled as such in their rule strings.

FIELD NOTES — the actual snapshot contract
------------------------------------------
    symbol, revenue_growth, eps_growth, profit_margin, forward_pe,
    institutional_pct, sector, industry, earnings_date, days_to_earnings,
    in_earnings_window, growth_grade, source

The yfinance provider swallows every exception into ``info = {}``, so an
all-None snapshot is a common live path rather than an edge case. The
all-unavailable branch is therefore a first-class outcome, not a fallback.
"""

from __future__ import annotations

from datetime import date

# ---------------------------------------------------------------- defaults
# In-module fallbacks so the module works with config absent, mirroring how
# scoring.py degrades.
DEFAULT_WEIGHTS = {
    "growth": 0.40,
    "profitability": 0.20,
    "valuation": 0.20,
    "sponsorship": 0.20,
}
DEFAULT_CFG = {
    "enabled": True,
    "earnings_gate": "suppress",     # suppress | flag | ignore
    "earnings_window_days": 7,       # matches engine EARNINGS_WINDOW_DAYS
    "score_mode": "legacy",          # legacy | assessment
    "strict_validation": False,
    "weights": DEFAULT_WEIGHTS,
}

GATE_MODES = ("suppress", "flag", "ignore")
SCORE_MODES = ("legacy", "assessment")

# Grade bands over quality_score.
GRADE_BANDS = ((0.80, "A"), (0.65, "B"), (0.50, "C"), (0.35, "D"))


def get_cfg(cfg: dict | None = None) -> dict:
    """Layered read: explicit arg > unified config > in-module defaults."""
    if cfg is not None:
        return {**DEFAULT_CFG, **cfg,
                "weights": {**DEFAULT_WEIGHTS, **(cfg.get("weights") or {})}}
    try:
        from config import get_config
        section = get_config().get("fundamentals", {}) or {}
    except Exception:
        section = {}
    return {**DEFAULT_CFG, **section,
            "weights": {**DEFAULT_WEIGHTS, **(section.get("weights") or {})}}


# ------------------------------------------------------------- primitives
def _piecewise(x: float, points: list[tuple[float, float]]) -> float:
    """Linear interpolation through (input, score) anchors, clamped at both
    ends. Anchors must be sorted by input ascending."""
    if x <= points[0][0]:
        return points[0][1]
    if x >= points[-1][0]:
        return points[-1][1]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if x0 <= x <= x1:
            if x1 == x0:
                return y1
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return points[-1][1]


def _num(value) -> float | None:
    """None for anything that isn't a usable finite number (bools included —
    a bool is not a growth rate)."""
    if value is None or isinstance(value, bool):
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if f != f or f in (float("inf"), float("-inf")):
        return None
    return f


# ------------------------------------------------------------- components
# Anchors are chosen so the growth component agrees with the engine's own
# _grade() bands: revenue >=0.20 with eps >=0.25 ("strong") always lands
# >=0.75, and revenue >=0.08 with eps >=0.10 ("moderate") always lands
# >=0.35. test_growth_component_agrees_with_engine_grade pins that.
_REVENUE_ANCHORS = [(0.0, 0.0), (0.08, 0.35), (0.20, 0.75), (0.40, 1.0)]
_EPS_ANCHORS = [(0.0, 0.0), (0.10, 0.35), (0.25, 0.75), (0.50, 1.0)]
_MARGIN_ANCHORS = [(0.0, 0.0), (0.05, 0.30), (0.15, 0.60), (0.30, 1.0)]
_PE_ANCHORS = [(5.0, 1.0), (15.0, 1.0), (25.0, 0.70),
               (40.0, 0.40), (60.0, 0.15), (80.0, 0.0)]
_INST_ANCHORS = [(0.0, 0.0), (0.30, 0.20), (0.50, 0.50),
                 (0.70, 0.80), (0.85, 1.0)]


def _growth(snap: dict) -> dict:
    rev, eps = _num(snap.get("revenue_growth")), _num(snap.get("eps_growth"))
    if rev is None and eps is None:
        return {"score": None, "inputs": {"revenue_growth": None, "eps_growth": None},
                "rule": "unavailable: neither revenue_growth nor eps_growth present",
                "reason": "no revenue or EPS growth in snapshot"}
    parts, inputs = [], {}
    if rev is not None:
        parts.append(_piecewise(rev, _REVENUE_ANCHORS))
        inputs["revenue_growth"] = rev
    if eps is not None:
        parts.append(_piecewise(eps, _EPS_ANCHORS))
        inputs["eps_growth"] = eps
    inputs["engine_growth_grade"] = snap.get("growth_grade")
    return {
        "score": round(sum(parts) / len(parts), 4),
        "inputs": inputs,
        "rule": ("mean of revenue-growth and EPS-growth curves, anchored on the "
                 "same bands the fundamentals engine uses for growth_grade "
                 "(rev 8%/20%, eps 10%/25%); missing legs are dropped, not zeroed"),
    }


def _profitability(snap: dict) -> dict:
    margin = _num(snap.get("profit_margin"))
    if margin is None:
        return {"score": None, "inputs": {"profit_margin": None},
                "rule": "unavailable: profit_margin absent",
                "reason": "no profit_margin in snapshot"}
    return {
        "score": round(_piecewise(margin, _MARGIN_ANCHORS), 4),
        "inputs": {"profit_margin": margin},
        "rule": ("net profit margin, single point-in-time reading (the snapshot "
                 "carries no margin history, so this is a level, not a trend): "
                 "0% -> 0.0, 5% -> 0.30, 15% -> 0.60, 30%+ -> 1.0"),
    }


def _valuation(snap: dict) -> dict:
    pe = _num(snap.get("forward_pe"))
    if pe is None:
        return {"score": None, "inputs": {"forward_pe": None},
                "rule": "unavailable: forward_pe absent",
                "reason": "no forward_pe in snapshot"}
    if pe <= 0:
        return {"score": None, "inputs": {"forward_pe": pe},
                "rule": "unavailable: non-positive forward_pe carries no ranking information",
                "reason": f"forward_pe {pe} is non-positive (no forward earnings)"}
    return {
        "score": round(_piecewise(pe, _PE_ANCHORS), 4),
        "inputs": {"forward_pe": pe, "sector": snap.get("sector")},
        "rule": ("forward P/E against ABSOLUTE bands (<=15 -> 1.0, 25 -> 0.70, "
                 "40 -> 0.40, 60 -> 0.15, 80+ -> 0.0). LOW CONFIDENCE: the repo "
                 "has no peer set, so this is not sector-relative and a cheap "
                 "utility scores the same as a cheap semi"),
        "low_confidence": True,
    }


def _sponsorship(snap: dict) -> dict:
    pct = _num(snap.get("institutional_pct"))
    if pct is None:
        return {"score": None, "inputs": {"institutional_pct": None},
                "rule": "unavailable: institutional_pct absent",
                "reason": "no institutional_pct in snapshot"}
    return {
        "score": round(_piecewise(pct, _INST_ANCHORS), 4),
        "inputs": {"institutional_pct": pct},
        "rule": ("institutional ownership as a LEVEL, not a trend — the snapshot "
                 "carries no ownership history, so rising and falling sponsorship "
                 "at the same percentage score identically: 30% -> 0.20, "
                 "50% -> 0.50, 70% -> 0.80, 85%+ -> 1.0"),
        "low_confidence": True,
    }


_BUILDERS = {
    "growth": _growth,
    "profitability": _profitability,
    "valuation": _valuation,
    "sponsorship": _sponsorship,
}


# ------------------------------------------------------------------ public
def _days_until_earnings(snap: dict, today: date | None = None) -> int | None:
    days = snap.get("days_to_earnings")
    if isinstance(days, int) and not isinstance(days, bool):
        return days
    raw = snap.get("earnings_date")
    if not raw:
        return None
    try:
        return (date.fromisoformat(str(raw)[:10]) - (today or date.today())).days
    except (ValueError, TypeError):
        return None


def assess(snapshot: dict, direction: str, cfg: dict | None = None,
           today: date | None = None) -> dict:
    """Grade a fundamentals snapshot and express it as direction alignment.

    Returns grade "unavailable" (NOT "F") when no component could be scored.
    """
    snapshot = snapshot or {}
    conf = get_cfg(cfg)
    weights = conf["weights"]

    components, unavailable = {}, []
    for name, build in _BUILDERS.items():
        result = build(snapshot)
        reason = result.pop("reason", None)
        components[name] = result
        if result["score"] is None:
            unavailable.append({"component": name,
                                "reason": reason or "no input available"})

    available = {k: v["score"] for k, v in components.items()
                 if v["score"] is not None}
    applied = {k: w for k, w in weights.items() if k in available}
    total_w = sum(applied.values())

    if not available or total_w <= 0:
        quality = alignment = None
        grade = "unavailable"
        applied_norm = {}
    else:
        quality = round(
            sum(available[k] * applied[k] for k in available) / total_w, 4)
        grade = next((g for cut, g in GRADE_BANDS if quality >= cut), "F")
        alignment = round(1.0 - quality, 4) if direction == "short" else quality
        applied_norm = {k: round(w / total_w, 4) for k, w in applied.items()}

    days = _days_until_earnings(snapshot, today)
    window = int(conf["earnings_window_days"])

    return {
        "grade": grade,
        "quality_score": quality,
        "alignment_score": alignment,
        "direction": direction,
        "components": components,
        "unavailable": unavailable,
        "earnings": {
            "date": snapshot.get("earnings_date"),
            "days_until": days,
            "in_gate_window": days is not None and 0 <= days <= window,
            "window_days": window,
        },
        "evidence": {
            "weights_declared": dict(weights),
            "weights_applied": applied_norm,
            "renormalized": bool(applied_norm) and len(applied) != len(weights),
            "formula": ("quality = sum(component_score * weight) / sum(weight) "
                        "over AVAILABLE components only; alignment = quality for "
                        "long, 1 - quality for short"),
            "direction_caveat": ("shorting weak fundamentals is a weaker inference "
                                 "than buying strong ones — weak fundamentals can "
                                 "persist for years without the price confirming"),
            "source": snapshot.get("source"),
        },
    }


def gate(setup: dict, assessment: dict, cfg: dict | None = None) -> dict:
    """Earnings-window gate (PRD §14). Never reads in_earnings_window."""
    conf = get_cfg(cfg)
    earnings = assessment.get("earnings", {})

    if not conf.get("enabled", True):
        return {"allowed": True, "action": "disabled",
                "reason": "fundamentals.enabled is false", "warning": None}

    mode = str(conf.get("earnings_gate", "suppress")).lower()
    if mode not in GATE_MODES:
        mode = "suppress"

    if not earnings.get("in_gate_window"):
        return {"allowed": True, "action": "pass",
                "reason": "no earnings inside the gate window", "warning": None}

    days = earnings.get("days_until")
    window = earnings.get("window_days")
    detail = (f"earnings in {days}d (gate window {window}d, "
              f"date {earnings.get('date')})")

    if mode == "ignore":
        return {"allowed": True, "action": "ignore",
                "reason": f"{detail} — gate set to ignore", "warning": None}
    if mode == "flag":
        return {"allowed": True, "action": "flag", "reason": detail,
                "warning": f"{detail} — binary-event risk"}
    return {"allowed": False, "action": "suppress",
            "reason": f"suppressed by earnings gate: {detail}", "warning": None}


def enrich_setup(setup: dict, assessment: dict) -> dict:
    """Attach the assessment as flat setup metadata.

    Deliberately NOT setup["setup_meta"]: setup_meta is a field on the Trade
    dataclass (alerts/lifecycle.py), populated at arm time by
    alerts/engine.py::arm_from_setup. Composer setups are flat dicts, so
    writing setup_meta here would create a key nothing reads.
    """
    setup["fundamentals_assessment"] = assessment
    return setup


def apply(setup: dict, snapshot: dict, direction: str,
          cfg: dict | None = None, today: date | None = None) -> dict:
    """Single entry point for the composer: assess -> gate -> enrich.

    Exists so each composer call site is one call rather than three.
    """
    assessment = assess(snapshot, direction, cfg, today)
    verdict = gate(setup, assessment, cfg)
    if setup is not None:
        enrich_setup(setup, assessment)
    return {
        "allowed": verdict["allowed"],
        "action": verdict["action"],
        "reason": verdict["reason"],
        "warnings": [verdict["warning"]] if verdict["warning"] else [],
        "assessment": assessment,
    }
