"""Setup composer (design doc §5.1, PRD §8).

The confluence pipeline:

  1. Regime gate — chop with conflicting VIX alignment emits "no-trade
     conditions" and stops. Avoiding low-quality setups is a feature.
  2. Candidates — leading + improving sector ETFs -> watchlist stocks in
     those sectors -> screener.
  3. Construction — entry trigger, stop, invalidation, targets from the
     levels engine's fractal clusters (ATR fallbacks declared as derivations).
  4. Scoring — the 11-component confidence score; setups below threshold
     or under the R:R floor are suppressed, with the reason recorded.
  5. Validation — every emitted setup passes the anti-hallucination check.

Phase 3 scope: stock setups, long in risk_on / short in risk_off. The thesis
is template-rendered from evidence; orchestrator/llm.py upgrades it to a
Claude-written thesis when an API key is configured (the validator applies
either way).
"""

from __future__ import annotations

from engines.shared.fractals import atr
from engines.shared.indicators import rsi
from engines.shared.providers import BarRequest
from .scoring import score_setup
from .validator import validate_setup

import os as _os

from config import get_config

# Phase 12: floors live in the unified config (which still honors the
# legacy CONFLUENCE_MIN_SCORE / _MIN_RR_T1 / _MIN_RR_T2 env vars).
# Module-level names are kept importable for backwards compatibility.
_CFG_ATTRS = {"MIN_SCORE": ("risk", "min_score"),
              "MIN_RR_T1": ("risk", "min_rr_t1"),
              "MIN_RR_T2": ("risk", "min_rr_t2")}


def __getattr__(name):  # PEP 562 — live values, importable names
    if name in _CFG_ATTRS:
        sec, key = _CFG_ATTRS[name]
        return get_config()[sec][key]
    raise AttributeError(name)

# Sector ETF -> representative liquid names. User-configurable; the real app
# derives membership from fundamentals-mcp sector tags.
DEFAULT_WATCHLIST = {
    "SMH": ["NVDA", "AVGO", "AMD", "MU"],
    "SOXX": ["NVDA", "AVGO", "AMD"],
    "XLK": ["MSFT", "AAPL", "ORCL"],
    "IGV": ["CRM", "NOW", "PLTR"],
    "MAGS": ["META", "GOOGL", "AMZN"],
    "XLE": ["XOM", "CVX"],
    "XOP": ["FANG", "DVN"],
    "URA": ["CCJ", "LEU"],
    "URNM": ["CCJ", "UEC"],
    "NLR": ["CEG", "VST"],
    "PAVE": ["PWR", "ETN"],
    "GRID": ["ETN", "VRT"],
    "XLV": ["LLY", "UNH"],
    "XLF": ["JPM", "GS"],
}


def load_watchlist(path: str = "watchlist.json") -> dict[str, list[str]]:
    """Merge an optional repo-root watchlist.json over the defaults.
    Keys are sector ETFs from the rotation universe; values are tickers.
    A custom key REPLACES that sector's default list."""
    import json
    import pathlib
    p = pathlib.Path(path)
    if not p.is_absolute():
        p = pathlib.Path(__file__).resolve().parent.parent / path
    if not p.exists():
        return DEFAULT_WATCHLIST
    custom = {k.upper(): [s.upper() for s in v]
              for k, v in json.loads(p.read_text()).items()}
    return {**DEFAULT_WATCHLIST, **custom}


class SetupComposer:
    def __init__(self, provider, regime_engine, rotation_engine, levels_engine,
                 volume_engine, momentum_engine, fundamentals_engine,
                 screener_engine, watchlist: dict[str, list[str]] | None = None,
                 thesis_writer=None, options_engine=None):
        self.provider = provider
        self.regime = regime_engine
        self.rotation = rotation_engine
        self.levels = levels_engine
        self.volume = volume_engine
        self.momentum = momentum_engine
        self.fundamentals = fundamentals_engine
        self.screener = screener_engine
        self.watchlist = watchlist or load_watchlist()
        self.thesis_writer = thesis_writer  # optional LLM upgrade (orchestrator/llm.py)
        self.options = options_engine       # optional until a chain feed exists

    # ---------- construction ----------

    def _construct(self, symbol: str, direction: str, level_payload: dict) -> dict | None:
        su = get_config()["setup"]   # Phase 12: named, tunable geometry
        buf, stop_k, max_stop_k = su["entry_buffer_atr"], su["stop_atr"], su["max_stop_atr"]
        t1_k, t2_k, step_k = su["t1_atr"], su["t2_atr"], su["target_step_atr"]
        spot = level_payload["spot"]
        clusters = level_payload["fractal_clusters"]
        a = level_payload["outliers"]["atr14"]
        hod = level_payload["session"]["high_of_day"]
        lod = level_payload["session"]["low_of_day"]
        res = sorted((c["price"] for c in clusters if c["kind"] in ("resistance", "mixed")
                      and c["price"] > spot))
        sup = sorted((c["price"] for c in clusters if c["kind"] in ("support", "mixed")
                      and c["price"] < spot), reverse=True)

        derived = {}

        def pick(seq, floor, fallback, key, formula):
            """First level past `floor`, else a declared ATR derivation."""
            for p in seq:
                if (p >= floor) if direction == "long" else (p <= floor):
                    return p
            derived[key] = formula
            return fallback

        if direction == "long":
            # Entry: nearest meaningful resistance; at 52w highs (no clusters
            # above) the trigger is a break of the day high — both in evidence.
            entry = next((p for p in res if p >= spot + buf * a), None) or hod
            # Stop: nearest support, but never more than max_stop_atr of risk.
            near_sup = next((p for p in sup if p >= entry - max_stop_k * a), None)
            if near_sup is None:
                derived["stop"] = {"formula": f"entry - {stop_k}*ATR14", "inputs": [entry, a]}
            stop = near_sup if near_sup is not None else round(entry - stop_k * a, 2)
            t1 = pick(res, entry + step_k * a, round(entry + t1_k * a, 2),
                      "target_1", {"formula": f"entry + {t1_k}*ATR14", "inputs": [entry, a]})
            t2 = pick(res, t1 + step_k * a, round(entry + t2_k * a, 2),
                      "target_2", {"formula": f"entry + {t2_k}*ATR14", "inputs": [entry, a]})
        else:
            entry = next((p for p in sup if p <= spot - buf * a), None) or lod
            near_res = next((p for p in res if p <= entry + max_stop_k * a), None)
            if near_res is None:
                derived["stop"] = {"formula": f"entry + {stop_k}*ATR14", "inputs": [entry, a]}
            stop = near_res if near_res is not None else round(entry + stop_k * a, 2)
            t1 = pick(sup, entry - step_k * a, round(entry - t1_k * a, 2),
                      "target_1", {"formula": f"entry - {t1_k}*ATR14", "inputs": [entry, a]})
            t2 = pick(sup, t1 - step_k * a, round(entry - t2_k * a, 2),
                      "target_2", {"formula": f"entry - {t2_k}*ATR14", "inputs": [entry, a]})

        risk = abs(entry - stop)
        if risk <= 0:
            return None
        # Geometry vs the live market: a long whose stop sits at/above spot
        # (entry far overhead) would invalidate on its first bar — not a
        # tradeable setup, suppress at construction.
        if direction == "long" and stop >= spot:
            return None
        if direction == "short" and stop <= spot:
            return None
        return {
            "symbol": symbol, "direction": direction, "instrument": "stock",
            "entry_trigger": round(entry, 2), "stop": round(stop, 2),
            "target_1": round(t1, 2), "target_2": round(t2, 2),
            "risk_reward_t1": round(abs(t1 - entry) / risk, 2),
            "risk_reward_t2": round(abs(t2 - entry) / risk, 2),
            "derived_levels": derived,
        }

    @staticmethod
    def _template_thesis(setup, ctx) -> str:
        d = setup["direction"]
        verb = "reclaims" if d == "long" else "loses"
        inval = ("a daily close back below the 21-day MA or VIX reclaiming its pivot"
                 if d == "long" else
                 "a daily close back above the 21-day MA or VIX losing its pivot")
        return (
            f"{setup['symbol']} {d}: {ctx['sector_etf']} is {ctx['sector_status']} and the "
            f"stock screens {ctx['screen']['classification']} "
            f"({ctx['screen']['passes']}/{ctx['screen']['total_checks']} checks). "
            f"Trade is live only if price {verb} {setup['entry_trigger']} — regime is "
            f"{ctx['regime']} ({ctx['regime_risk_score']:+.1f}) with VIX "
            f"{ctx['vix_alignment_state'].replace('_', ' ')}. Risk {setup['stop']}, "
            f"targets {setup['target_1']} then {setup['target_2']} "
            f"(R:R {setup['risk_reward_t1']}). Invalidated by {inval}."
        )

    # ---------- pipeline ----------

    def compose(self, max_setups: int | None = None) -> dict:
        cfg = get_config()
        if max_setups is None:
            max_setups = cfg["compose"]["max_setups"]
        min_score = cfg["risk"]["min_score"]
        min_rr_t1, min_rr_t2 = cfg["risk"]["min_rr_t1"], cfg["risk"]["min_rr_t2"]
        chop_mode = cfg["gates"]["chop_mode"]

        regime = self.regime.get_regime()
        vix_state = next(c for c in regime["components"]
                         if c["name"] == "vix_alignment")["evidence"]["state"]

        # config gate honors the legacy env var through the loader overlay
        forced = str(cfg["gates"]["force_direction"]).lower()
        if forced not in ("long", "short"):
            forced = None

        chop_warning = None
        if regime["regime"] == "chop" and not forced:
            chop_reason = (f"Regime is chop (score {regime['risk_score']:+.1f}) "
                           f"with VIX {vix_state.replace('_', ' ')} — "
                           "no-trade conditions. Standing aside is the setup.")
            if chop_mode == "hard":
                return {"regime": regime, "setups": [], "suppressed": [],
                        "no_trade": True, "forced": False,
                        "chop_gate": "hard", "reason": chop_reason}
            # soft/off: compose anyway (Phase 11 transparency, now a dial);
            # direction follows the risk score's lean
            if chop_mode == "soft":
                chop_warning = ("CHOP GATE OVERRIDDEN (soft mode): " + chop_reason
                                + " Setups below are counter-policy — size down "
                                  "or stand aside.")

        direction = forced or ("long" if (
            regime["regime"] == "risk_on"
            or (regime["regime"] == "chop" and regime["risk_score"] >= 0)
        ) else "short")
        candidates = self.rotation.get_rotation_candidates()
        active_etfs = candidates["leading"] + candidates["improving"]

        stock_to_etf: dict[str, dict] = {}
        for etf in active_etfs:
            for stock in self.watchlist.get(etf["symbol"], []):
                if stock not in stock_to_etf:  # keep the strongest sector link
                    stock_to_etf[stock] = etf

        screened = self.screener.screen(list(stock_to_etf)) if stock_to_etf else {"results": []}
        keep_classes = ({"canslim_leader", "laggard_turn"} if direction == "long"
                        else {"no_setup", "overextended"})  # shorts hunt broken structure

        setups, suppressed = [], []
        for screen in screened["results"]:
            if screen["classification"] not in keep_classes:
                continue
            sym = screen["symbol"]
            etf = stock_to_etf[sym]
            level_payload = self.levels.get_levels(sym)
            setup = self._construct(sym, direction, level_payload)
            if setup is None:
                suppressed.append({"symbol": sym, "reason": "no usable level structure"})
                continue
            if setup["risk_reward_t1"] < min_rr_t1 or setup["risk_reward_t2"] < min_rr_t2:
                suppressed.append({"symbol": sym,
                                   "reason": f"R:R T1 {setup['risk_reward_t1']} / "
                                             f"T2 {setup['risk_reward_t2']} below "
                                             f"{min_rr_t1}/{min_rr_t2} floors"})
                continue

            daily = self.provider.get_bars(BarRequest(sym, "1d", 400))
            phase = self.volume.get_phase(sym)
            divs = self.momentum.get_divergences(sym)["divergences"]
            fund = self.fundamentals.get_snapshot(sym)
            dollar_vol = float((daily["close"] * daily["volume"]).tail(20).mean() / 1e6)

            ctx = {
                "regime": regime["regime"], "regime_risk_score": regime["risk_score"],
                "vix_alignment_state": vix_state,
                "sector_etf": etf["symbol"], "sector_status": etf["status"],
                "sector_rank_4w": etf.get("rank_4w"),
                "screen": screen, "phase": phase["phase"],
                "rvol_20d": level_payload["rvol_20d"],
                "daily_rsi": round(float(rsi(daily["close"]).dropna().iloc[-1]), 1),
                "bearish_divergence": any(d["type"] == "bearish_divergence" for d in divs),
                "bullish_divergence": any(d["type"] == "bullish_divergence" for d in divs),
                "mas_above": sum(m["state"] == "above" for m in level_payload["moving_averages"]),
                "risk_reward_t1": setup["risk_reward_t1"],
                "risk_reward_t2": setup["risk_reward_t2"],
                "avg_dollar_volume_m": round(dollar_vol, 1),
                "fundamentals": fund,
            }
            options_payload = None
            if self.options is not None:
                try:
                    ctx["options_alignment"] = self.options.get_alignment(
                        sym, direction, setup["entry_trigger"], setup["target_1"])
                    ctx["contract"] = self.options.select_contract(
                        sym, direction, setup["entry_trigger"],
                        setup["target_1"], setup["target_2"])
                    options_payload = self.options.get_dealer_zones(sym)
                except Exception:
                    options_payload = None   # degrade to placeholder scoring
            scored = score_setup(direction, ctx)
            if scored["score"] < min_score:
                suppressed.append({"symbol": sym,
                                   "reason": f"confidence {scored['score']} below {min_score} floor"})
                continue

            evidence = {"levels": level_payload, "regime": regime, "screen": screen,
                        "phase": phase, "fundamentals": fund, "sector": etf,
                        "options": options_payload}
            check = validate_setup(setup, evidence)
            if not check["valid"]:
                suppressed.append({"symbol": sym, "reason": "failed evidence validation",
                                   "violations": check["violations"]})
                continue

            setup |= {
                "options": options_payload,
                "instrument_suggestion": ctx.get("contract"),
                "instrument": (ctx.get("contract") or {}).get("instrument", "stock"),
                "confidence": scored["score"],
                "score_components": scored["components"],
                "risks": scored["risks"],
                "sector_etf": etf["symbol"], "sector_status": etf["status"],
                "classification": screen["classification"],
                "structure": screen["structure"],
                "invalidation": ("daily close below 21d MA or VIX reclaims pivot"
                                 if direction == "long" else
                                 "daily close above 21d MA or VIX loses pivot"),
                "earnings_flag": fund["in_earnings_window"],
                "thesis": (self.thesis_writer(setup, ctx, evidence)
                           if self.thesis_writer else self._template_thesis(setup, ctx)),
                "validated": True,
                "computed_at": level_payload["computed_at"],
            }
            setups.append(setup)

        setups.sort(key=lambda s: -s["confidence"])
        out = {"regime": regime, "direction": direction,
               "setups": setups[:max_setups], "suppressed": suppressed,
               "no_trade": False, "forced": bool(forced)}
        if chop_warning:
            out["chop_gate"] = "soft"
            out["chop_warning"] = chop_warning
        return out
