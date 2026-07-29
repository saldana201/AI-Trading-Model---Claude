"""Phase 29 — calibration disclosure: make the system tell the truth about itself.

Why this exists
---------------
Phases 15-28 established, on 506 real trades over four years:

  - the system returns +37.4% vs QQQ's +111.7%, with a DEEPER drawdown
    (-33.0% vs -22.8%) and worse Sharpe (0.55 vs 1.00);
  - component "edges" collapse to ~0 at adequate sample size — no single signal
    reliably separates winners from losers;
  - the confidence score is at best weakly monotonic and was ANTI-predictive in
    several runs.

The engines remain genuinely useful: VIX pivots, fractal S/R clusters, GEX
walls, GARCH vol forecasts, sector rotation. Those are *facts a discretionary
trader can use*. What failed is the synthesis step that turns them into "take
this trade with 8.2 confidence."

So the score must stop being presented as a bare number that reads like a
probability of profit. Every confidence value the system emits now carries the
measured reality alongside it. This is the PRD's own §19 position — decision
support, not advice — enforced in code rather than stated in a footnote.

This module holds no opinion of its own. It reads a calibration file produced by
the backtest (`backtest/results.json`) and reports what actually happened for
setups in each confidence band. When no calibration exists, it says so rather
than inventing reassurance.
"""

from __future__ import annotations

import json
import os

CALIBRATION_PATH = os.environ.get("CONFLUENCE_CALIBRATION",
                                  "backtest/results.json")

# Measured on 506 trades, 2022-08 to 2026-07, chop_soft, 143-ticker watchlist,
# costs modelled. Used only when no results.json is present, so the system is
# never silently uncalibrated. Update by re-running validate_real.
FALLBACK = {
    "source": "Phase 28 reference run (506 trades, 2022-08..2026-07)",
    "overall": {"n": 506, "avg_r": 0.109, "win_rate": 0.556},
    "benchmark": {"symbol": "QQQ", "total_return_pct": 111.7,
                  "strategy_total_return_pct": 37.4,
                  "strategy_max_dd_pct": -33.0, "benchmark_max_dd_pct": -22.8,
                  "strategy_sharpe": 0.548, "benchmark_sharpe": 0.995},
}


def load_calibration(path: str | None = None) -> dict:
    p = path or CALIBRATION_PATH
    try:
        with open(p) as fh:
            rep = json.load(fh)
        return {"available": True, "source": p,
                "overall": rep.get("overall"),
                "by_confidence": rep.get("by_confidence"),
                "rigor": rep.get("rigor"), "costs": rep.get("costs")}
    except Exception:
        return {"available": False, "source": "fallback reference run",
                "fallback": FALLBACK}


def band_for(confidence: float) -> str:
    if confidence is None:
        return "unknown"
    if confidence < 6.5:
        return "<6.5"
    if confidence < 7.5:
        return "6.5-7.5"
    return ">=7.5"


def disclose(confidence: float, calibration: dict | None = None) -> dict:
    """What the historical record actually says about setups scored like this.

    Returns a dict intended to travel WITH the confidence value everywhere it is
    displayed — dashboard card, chat answer, morning brief, alert payload.
    """
    cal = calibration or load_calibration()
    band = band_for(confidence)
    out = {"confidence": confidence, "band": band,
           "calibration_source": cal.get("source")}

    bucket = None
    if cal.get("available") and isinstance(cal.get("by_confidence"), dict):
        bucket = cal["by_confidence"].get(band)

    if bucket and bucket.get("n"):
        out["historical"] = {
            "n": bucket.get("n"), "avg_r": bucket.get("avg_r"),
            "win_rate": bucket.get("win_rate"),
        }
        n = bucket.get("n") or 0
        avg = bucket.get("avg_r")
        if n < 30:
            out["reliability"] = (f"only {n} historical trades in this band — "
                                  "too few to mean anything")
        elif avg is not None and avg <= 0:
            out["reliability"] = ("this band has historically LOST money — a "
                                  "higher score here has not meant a better trade")
        else:
            out["reliability"] = (f"historically {avg:+.3f}R average over {n} "
                                  "trades, net of modelled costs")
    else:
        f = (cal.get("fallback") or FALLBACK)["overall"]
        out["historical"] = {"n": f["n"], "avg_r": f["avg_r"],
                             "win_rate": f["win_rate"]}
        out["reliability"] = (f"no per-band calibration loaded; system-wide "
                             f"average is {f['avg_r']:+.3f}R over {f['n']} trades")

    out["caveat"] = (
        "Confidence is a CONFLUENCE measure — how many engines agree — not a "
        "probability of profit. Measured component edges are near zero at "
        "adequate sample size, and the score has not reliably ranked outcomes.")
    return out


def benchmark_context(calibration: dict | None = None) -> dict:
    """The comparison a user deserves to see next to any trade suggestion."""
    cal = calibration or load_calibration()
    b = (cal.get("fallback") or FALLBACK)["benchmark"]
    return {
        "headline": (f"Over the validated window this system returned "
                     f"{b['strategy_total_return_pct']}% with a "
                     f"{b['strategy_max_dd_pct']}% drawdown, versus "
                     f"{b['symbol']} at {b['total_return_pct']}% with "
                     f"{b['benchmark_max_dd_pct']}%."),
        "verdict": ("Buying and holding the index outperformed this system on "
                    "return, drawdown and Sharpe. Treat its output as research "
                    "input for your own decision, not as a signal to follow."),
        **b,
    }


def annotate_setup(setup: dict, calibration: dict | None = None) -> dict:
    """Attach disclosure to a composed setup without altering its numbers."""
    s = dict(setup)
    s["calibration"] = disclose(setup.get("confidence"), calibration)
    return s


def render(confidence: float, calibration: dict | None = None) -> str:
    d = disclose(confidence, calibration)
    h = d.get("historical") or {}
    return (f"confidence {confidence} (band {d['band']}) — "
            f"{d['reliability']}. {d['caveat']}")
