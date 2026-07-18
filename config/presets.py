"""Phase 12 — named presets.

A preset is just a config patch. `balanced` is exactly the historical
defaults; `conservative` and `aggressive` shift the gates and risk floors,
never the anti-hallucination or validation machinery — those are not
tunable by design.
"""

from __future__ import annotations

PRESETS: dict[str, dict] = {
    "balanced": {
        "description": "The historical defaults. Chop gate hard, 6.0 "
                       "confidence floor, 1% risk per trade.",
        "patch": {
            "setup": {"entry_buffer_atr": 0.25, "stop_atr": 1.2,
                      "max_stop_atr": 2.0, "t1_atr": 1.5, "t2_atr": 2.5},
            "risk": {"min_score": 6.0, "min_rr_t1": 1.0, "min_rr_t2": 2.0,
                     "risk_per_trade_pct": 1.0, "max_position_pct": 25.0},
            "gates": {"chop_mode": "hard"},
            "lifecycle": {"max_trigger_attempts": 2, "trail_atr": 1.5},
            "compose": {"max_setups": 6},
        },
    },
    "conservative": {
        "description": "Fewer, higher-conviction setups: 7.0 confidence "
                       "floor, 1.5:1 / 2.5:1 R:R floors, 0.5% risk per "
                       "trade, tighter trail, one trigger attempt.",
        "patch": {
            "risk": {"min_score": 7.0, "min_rr_t1": 1.5, "min_rr_t2": 2.5,
                     "risk_per_trade_pct": 0.5, "max_position_pct": 15.0},
            "gates": {"chop_mode": "hard"},
            "lifecycle": {"max_trigger_attempts": 1, "trail_atr": 1.0},
            "compose": {"max_setups": 4},
        },
    },
    "aggressive": {
        "description": "More candidates, softer gate: 5.0 confidence floor, "
                       "chop composes with a warning instead of a hard "
                       "no-trade, 2% risk per trade, wider trail.",
        "patch": {
            "risk": {"min_score": 5.0, "min_rr_t1": 1.0, "min_rr_t2": 1.8,
                     "risk_per_trade_pct": 2.0, "max_position_pct": 35.0},
            "gates": {"chop_mode": "soft"},
            "lifecycle": {"max_trigger_attempts": 2, "trail_atr": 2.0},
            "compose": {"max_setups": 8},
        },
    },
}


def list_presets() -> dict:
    return {name: {"description": p["description"], "patch": p["patch"]}
            for name, p in PRESETS.items()}


def get_preset(name: str) -> dict:
    if name not in PRESETS:
        raise KeyError(f"unknown preset '{name}' "
                       f"(available: {', '.join(sorted(PRESETS))})")
    return PRESETS[name]["patch"]
