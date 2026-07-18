"""Phase 12 — position sizing.

Deterministic arithmetic over engine-produced prices and user config.
Every number carries its formula and inputs, extending the
anti-hallucination invariant to the assistant layer: nothing here is
opinion, everything traces.
"""

from __future__ import annotations

from config import get_config


def size_position(entry: float, stop: float, cfg: dict | None = None) -> dict:
    """Shares + dollar risk for one trade.

    shares = floor((account_size * risk_pct/100) / |entry - stop|),
    then capped so position value <= account_size * max_position_pct/100.
    """
    cfg = cfg or get_config()
    risk = cfg["risk"]
    account = float(risk["account_size"])
    risk_pct = float(risk["risk_per_trade_pct"])
    max_pos_pct = float(risk["max_position_pct"])

    per_share_risk = abs(entry - stop)
    if per_share_risk <= 0:
        return {"shares": 0, "error": "entry equals stop — no defined risk"}

    risk_budget = account * risk_pct / 100.0
    shares_by_risk = int(risk_budget // per_share_risk)

    max_position_value = account * max_pos_pct / 100.0
    shares_by_cap = int(max_position_value // entry) if entry > 0 else 0

    shares = max(0, min(shares_by_risk, shares_by_cap))
    capped = shares_by_cap < shares_by_risk

    return {
        "shares": shares,
        "per_share_risk": round(per_share_risk, 4),
        "dollar_risk": round(shares * per_share_risk, 2),
        "position_value": round(shares * entry, 2),
        "risk_budget": round(risk_budget, 2),
        "capped_by_position_limit": capped,
        "evidence": {
            "formula": "floor(account*risk_pct% / |entry-stop|), "
                       "capped at account*max_position_pct% / entry",
            "inputs": {
                "entry": entry, "stop": stop,
                "account_size": account,
                "risk_per_trade_pct": risk_pct,
                "max_position_pct": max_pos_pct,
            },
        },
    }
