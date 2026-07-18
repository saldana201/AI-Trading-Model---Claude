"""Phase 12 — trade plan builder.

Turns a composed setup (already validated against engine evidence) into an
actionable order checklist: entry order, initial stop, T1 trim with
quantity, breakeven move, T2 exit, trailing rule. Prices come only from
the setup; quantities only from sizing; management rules only from config
and the lifecycle contract — the same rules `alerts/lifecycle.py` will
enforce, stated up front so the user can pre-stage orders.
"""

from __future__ import annotations

from config import get_config
from .sizing import size_position

TRIM_FRACTION = 0.5  # lifecycle trims at T1 and trails the rest


def build_plan(setup: dict, cfg: dict | None = None) -> dict:
    cfg = cfg or get_config()
    d = setup["direction"]
    long = d == "long"
    entry = setup["entry_trigger"]
    stop = setup["stop"]
    t1, t2 = setup["target_1"], setup["target_2"]

    sizing = size_position(entry, stop, cfg)
    shares = sizing.get("shares", 0)
    trim_qty = int(shares * TRIM_FRACTION)
    runner_qty = shares - trim_qty

    entry_order = "buy stop" if long else "sell stop (short)"
    stop_order = "sell stop" if long else "buy stop (cover)"
    trim_side = "sell" if long else "buy to cover"

    steps = [
        {"step": 1, "action": "enter",
         "order": f"{entry_order} {shares} {setup['symbol']} @ {entry}",
         "note": "trigger must HOLD: a close back through the level re-arms "
                 "once; a second failure invalidates the setup"},
        {"step": 2, "action": "protect",
         "order": f"{stop_order} {shares} @ {stop}",
         "note": f"initial risk {sizing.get('per_share_risk')} per share, "
                 f"${sizing.get('dollar_risk')} total"},
        {"step": 3, "action": "trim",
         "order": f"{trim_side} {trim_qty} @ {t1} (limit)",
         "note": "on fill: move remaining stop to breakeven "
                 f"({entry}) — the lifecycle engine does this automatically "
                 "for tracked trades"},
        {"step": 4, "action": "trail",
         "order": f"trail remaining {runner_qty} by "
                  f"{cfg['lifecycle']['trail_atr']} * ATR14 from the "
                  f"{'high' if long else 'low'}-water mark, never "
                  f"{'below' if long else 'above'} breakeven"},
        {"step": 5, "action": "exit",
         "order": f"{trim_side} remaining {runner_qty} @ {t2} (limit), "
                  "or on trailing stop, whichever comes first"},
    ]

    text = "\n".join(
        f"{s['step']}. [{s['action'].upper()}] {s['order']}"
        + (f"\n   {s['note']}" if s.get("note") else "")
        for s in steps
    )

    return {
        "symbol": setup["symbol"],
        "direction": d,
        "confidence": setup.get("confidence"),
        "risk_reward_t1": setup.get("risk_reward_t1"),
        "risk_reward_t2": setup.get("risk_reward_t2"),
        "sizing": sizing,
        "bracket": {
            "entry": entry, "stop": stop,
            "target_1": t1, "target_2": t2,
            "trim_quantity": trim_qty, "runner_quantity": runner_qty,
        },
        "steps": steps,
        "text": text,
        "invalidation": setup.get("invalidation"),
        "derived_levels": setup.get("derived_levels", {}),
    }
