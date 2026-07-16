"""Confidence scoring (design doc §5.2, PRD §17).

Deterministic weighted score over the PRD's eleven components, each
normalized 0..1. Options-positioning and contract-liquidity components are
explicit Phase 5 placeholders (scored neutral, weight reduced, and labeled) —
the score never silently pretends to know what it doesn't.
"""

from __future__ import annotations

WEIGHTS = {
    "vix_alignment": 1.4,
    "index_alignment": 1.2,
    "options_alignment": 1.1,    # real when options-mcp data present
    "sector_strength": 1.2,
    "stock_relative_strength": 1.2,
    "volume_rvol": 1.0,
    "rsi_confirmation": 0.9,
    "ma_structure": 1.0,
    "risk_reward": 1.3,
    "liquidity": 0.8,            # contract-based when options-mcp present
    "catalyst_fundamental": 1.0,
}

ALIGN_VALUE = {
    "confirming_bullish": 1.0, "diverging_supportive": 0.7, "neutral_chop": 0.45,
    "diverging_warning": 0.25, "confirming_bearish": 0.0,
}
ROTATION_VALUE = {"leading": 1.0, "improving": 0.8, "neutral": 0.45,
                  "pinned": 0.5,
                  "deteriorating": 0.15, "lagging": 0.1}
GRADE_VALUE = {"strong": 1.0, "moderate": 0.6, "weak": 0.25, "unknown": 0.45}


def _clamp(v, lo=0.0, hi=1.0):
    return max(lo, min(hi, v))


def score_setup(direction: str, ctx: dict) -> dict:
    """ctx carries engine outputs; every component reports value + evidence."""
    flip = direction == "short"

    def directional(v):  # invert bullish-keyed values for shorts
        return 1.0 - v if flip else v

    comps = {}

    comps["vix_alignment"] = {
        "value": directional(ALIGN_VALUE[ctx["vix_alignment_state"]]),
        "evidence": {"state": ctx["vix_alignment_state"]},
    }
    rs = ctx["regime_risk_score"]
    comps["index_alignment"] = {
        "value": _clamp(0.5 + (rs if not flip else -rs) / 20),
        "evidence": {"regime": ctx["regime"], "risk_score": rs},
    }
    oa = ctx.get("options_alignment")
    if oa:
        comps["options_alignment"] = {
            "value": oa["value"],
            "evidence": {"reasons": oa["reasons"], "flip": oa["flip"],
                         "call_wall": oa["call_wall"], "put_wall": oa["put_wall"]},
        }
    else:
        comps["options_alignment"] = {
            "value": 0.5, "placeholder": True,
            "evidence": {"note": "options data unavailable; scored neutral"},
        }
    comps["sector_strength"] = {
        "value": directional(ROTATION_VALUE.get(ctx["sector_status"], 0.45)),
        "evidence": {"sector_etf": ctx["sector_etf"], "status": ctx["sector_status"],
                     "rank_4w": ctx.get("sector_rank_4w")},
    }
    screen = ctx["screen"]
    comps["stock_relative_strength"] = {
        "value": directional(_clamp(screen["passes"] / screen["total_checks"])),
        "evidence": {"classification": screen["classification"],
                     "passes": f'{screen["passes"]}/{screen["total_checks"]}'},
    }
    rv = ctx["rvol_20d"]
    comps["volume_rvol"] = {
        "value": _clamp((rv - 0.7) / 1.3),   # 0.7x -> 0, 2.0x -> 1
        "evidence": {"rvol_20d": rv, "phase": ctx["phase"]},
    }
    rsi = ctx["daily_rsi"]
    if flip:
        rsi_v = _clamp((55 - rsi) / 25) if not ctx["bullish_divergence"] else 0.2
    else:
        rsi_v = _clamp((rsi - 45) / 25) if not ctx["bearish_divergence"] else 0.2
    comps["rsi_confirmation"] = {
        "value": rsi_v,
        "evidence": {"daily_rsi": rsi,
                     "bearish_divergence": ctx["bearish_divergence"],
                     "bullish_divergence": ctx["bullish_divergence"]},
    }
    ma_above = ctx["mas_above"]
    comps["ma_structure"] = {
        "value": directional(_clamp(ma_above / 6)),
        "evidence": {"mas_above_of_6": ma_above},
    }
    rr2 = ctx.get("risk_reward_t2") or ctx["risk_reward_t1"] * 1.6
    comps["risk_reward"] = {
        "value": _clamp((rr2 - 1.5) / 2.5),   # 1.5:1 -> 0, 4:1 -> 1 (vs T2 objective)
        "evidence": {"rr_t1": ctx["risk_reward_t1"], "rr_t2": ctx.get("risk_reward_t2")},
    }
    contract = ctx.get("contract")
    if contract and contract.get("instrument") not in (None, "stock"):
        liq = _clamp(min(contract["oi"] / 2000, 1.0)
                     * _clamp(1.0 - contract["spread_pct"] * 10))
        comps["liquidity"] = {
            "value": liq,
            "evidence": {"oi": contract["oi"],
                         "spread_pct": contract["spread_pct"],
                         "instrument": contract["instrument"]},
        }
    else:
        dv = ctx["avg_dollar_volume_m"]
        comps["liquidity"] = {
            "value": _clamp(dv / 500), "placeholder": True,
            "evidence": {"avg_dollar_volume_$m": dv,
                         "note": "no liquid contract — dollar-volume proxy"},
        }
    fund = ctx["fundamentals"]
    cat_v = GRADE_VALUE[fund["growth_grade"]]
    if fund["in_earnings_window"]:
        cat_v *= 0.5  # binary-event risk inside the window
    comps["catalyst_fundamental"] = {
        "value": cat_v,
        "evidence": {"growth_grade": fund["growth_grade"],
                     "days_to_earnings": fund["days_to_earnings"],
                     "in_earnings_window": fund["in_earnings_window"]},
    }

    total_w = sum(WEIGHTS.values())
    raw = sum(comps[k]["value"] * WEIGHTS[k] for k in WEIGHTS)
    score = round(raw / total_w * 10, 1)
    for k in comps:
        comps[k]["weight"] = WEIGHTS[k]
        comps[k]["value"] = round(comps[k]["value"], 2)

    risks = []
    ext = screen.get("extension_vs_21d_pct")
    if ext is not None and ext > 9:
        risks.append(f"extended {ext}% above 21d MA — avoid chasing unless the break holds")
    if fund["in_earnings_window"]:
        risks.append(f"earnings in {fund['days_to_earnings']}d — binary-event risk")
    if ctx["bearish_divergence"] and not flip:
        risks.append("daily bearish RSI divergence active")
    if ctx["bullish_divergence"] and flip:
        risks.append("daily bullish RSI divergence active")
    if oa and oa["value"] < 0.4:
        risks.append("options positioning headwind: " + "; ".join(oa["reasons"]))
    if contract and contract.get("t1_within_expected_move") is False:
        risks.append("target 1 sits outside the contract's expected move")

    return {"score": score, "components": comps, "risks": risks}
