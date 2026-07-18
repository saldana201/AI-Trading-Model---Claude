"""Phase 12 — unified configuration schema (glass-box tuning surface).

Every previously hardcoded magic number in the composer, scorer, and
lifecycle is a named parameter here. Defaults are byte-identical to the
pre-Phase-12 constants, so applying this upgrade with no config file
changes nothing — all prior tests stay green.

Dependency-free by design (stdlib only): the config package must be
importable by engines, orchestrator, alerts, and scripts without pulling
in FastAPI/pydantic.
"""

from __future__ import annotations

import copy

CHOP_MODES = ("hard", "soft", "off")
DIRECTIONS = ("", "long", "short")

DEFAULTS: dict = {
    "setup": {
        # entry: nearest cluster at least this many ATRs beyond spot
        "entry_buffer_atr": 0.25,
        # stop fallback when no support/resistance inside max_stop_atr
        "stop_atr": 1.2,
        # never accept a structural stop further than this many ATRs
        "max_stop_atr": 2.0,
        # target fallbacks (declared ATR derivations, per anti-hallucination)
        "t1_atr": 1.5,
        "t2_atr": 2.5,
        # a target cluster must clear the prior level by this many ATRs
        "target_step_atr": 0.75,
    },
    "risk": {
        "min_score": 6.0,        # confidence floor (was CONFLUENCE_MIN_SCORE)
        "min_rr_t1": 1.0,        # trim-level R:R floor
        "min_rr_t2": 2.0,        # 2:1 objective floor
        "account_size": 25000.0,           # used by the trade assistant
        "risk_per_trade_pct": 1.0,         # % of account risked per trade
        "max_position_pct": 25.0,          # position value cap, % of account
    },
    "scoring": {
        "weights": {
            "vix_alignment": 1.4,
            "index_alignment": 1.2,
            "options_alignment": 1.1,
            "sector_strength": 1.2,
            "stock_relative_strength": 1.2,
            "volume_rvol": 1.0,
            "rsi_confirmation": 0.9,
            "ma_structure": 1.0,
            "risk_reward": 1.3,
            "liquidity": 0.8,
            "catalyst_fundamental": 1.0,
        },
    },
    "lifecycle": {
        "max_trigger_attempts": 2,
        "trail_atr": 1.5,        # trail_distance = trail_atr * ATR14 at arm
    },
    "gates": {
        "chop_mode": "hard",     # hard: no-trade | soft: compose + warn | off
        "force_direction": "",   # "" | "long" | "short"
    },
    "compose": {
        "max_setups": 6,
    },
}

# legacy env vars -> config paths (backwards compatibility)
ENV_MAP = {
    "CONFLUENCE_MIN_SCORE": ("risk", "min_score", float),
    "CONFLUENCE_MIN_RR_T1": ("risk", "min_rr_t1", float),
    "CONFLUENCE_MIN_RR_T2": ("risk", "min_rr_t2", float),
    "CONFLUENCE_FORCE_DIRECTION": ("gates", "force_direction", str),
    "CONFLUENCE_ACCOUNT_SIZE": ("risk", "account_size", float),
    "CONFLUENCE_RISK_PCT": ("risk", "risk_per_trade_pct", float),
}

_POSITIVE = {
    ("setup", "entry_buffer_atr"), ("setup", "stop_atr"), ("setup", "max_stop_atr"),
    ("setup", "t1_atr"), ("setup", "t2_atr"), ("setup", "target_step_atr"),
    ("risk", "min_rr_t1"), ("risk", "min_rr_t2"),
    ("risk", "account_size"), ("risk", "risk_per_trade_pct"),
    ("risk", "max_position_pct"), ("lifecycle", "trail_atr"),
}


def deep_merge(base: dict, patch: dict) -> dict:
    """Return a new dict: `patch` layered over `base` (nested dicts merge)."""
    out = copy.deepcopy(base)
    for k, v in (patch or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def validate(cfg: dict) -> list[str]:
    """Return a list of human-readable violations (empty == valid)."""
    errors: list[str] = []

    # unknown sections/keys — reject typos loudly rather than ignore them
    for section, values in cfg.items():
        if section not in DEFAULTS:
            errors.append(f"unknown section '{section}'")
            continue
        if not isinstance(values, dict):
            errors.append(f"section '{section}' must be an object")
            continue
        for key in values:
            if key not in DEFAULTS[section]:
                errors.append(f"unknown key '{section}.{key}'")

    def get(sec, key):
        return cfg.get(sec, {}).get(key, DEFAULTS[sec][key])

    # numeric type + positivity
    for sec, key in _POSITIVE:
        v = get(sec, key)
        if not isinstance(v, (int, float)) or isinstance(v, bool) or v <= 0:
            errors.append(f"'{sec}.{key}' must be a positive number (got {v!r})")

    ms = get("risk", "min_score")
    if not isinstance(ms, (int, float)) or isinstance(ms, bool) or not (0 <= ms <= 10):
        errors.append(f"'risk.min_score' must be in [0, 10] (got {ms!r})")

    mta = get("lifecycle", "max_trigger_attempts")
    if not isinstance(mta, int) or isinstance(mta, bool) or mta < 1:
        errors.append(f"'lifecycle.max_trigger_attempts' must be an int >= 1 (got {mta!r})")

    mx = get("compose", "max_setups")
    if not isinstance(mx, int) or isinstance(mx, bool) or mx < 1:
        errors.append(f"'compose.max_setups' must be an int >= 1 (got {mx!r})")

    if get("gates", "chop_mode") not in CHOP_MODES:
        errors.append(f"'gates.chop_mode' must be one of {CHOP_MODES}")
    if str(get("gates", "force_direction")).lower() not in DIRECTIONS:
        errors.append(f"'gates.force_direction' must be one of {DIRECTIONS}")

    # geometry sanity: T2 beyond T1, stop cap beyond stop fallback
    setup = deep_merge(DEFAULTS["setup"], cfg.get("setup", {}))
    if setup["t2_atr"] <= setup["t1_atr"]:
        errors.append("'setup.t2_atr' must exceed 'setup.t1_atr'")
    if setup["max_stop_atr"] < setup["stop_atr"]:
        errors.append("'setup.max_stop_atr' must be >= 'setup.stop_atr'")

    # scoring weights: known keys, non-negative numbers
    weights = cfg.get("scoring", {}).get("weights", {})
    if not isinstance(weights, dict):
        errors.append("'scoring.weights' must be an object")
    else:
        for k, v in weights.items():
            if k not in DEFAULTS["scoring"]["weights"]:
                errors.append(f"unknown scoring weight '{k}'")
            elif not isinstance(v, (int, float)) or isinstance(v, bool) or v < 0:
                errors.append(f"scoring weight '{k}' must be a non-negative number")

    if get("risk", "max_position_pct") > 100:
        errors.append("'risk.max_position_pct' cannot exceed 100")
    if get("risk", "risk_per_trade_pct") > 10:
        errors.append("'risk.risk_per_trade_pct' above 10% is rejected as unsafe")

    return errors
