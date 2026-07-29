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
# Module-level names stay importable for backwards compatibility.
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


import logging as _logging

_log = _logging.getLogger("AI Trading Model - Claude.watchlist")
_REPO_ROOT = __import__("pathlib").Path(__file__).resolve().parent.parent


def _resolve_watchlist_path(path: str):
    """Find watchlist.json robustly: an absolute path as given, else the
    first hit among CWD and the repo root. Returns (Path|None, searched)."""
    import pathlib
    p = pathlib.Path(path)
    if p.is_absolute():
        return (p if p.exists() else None), [str(p)]
    # explicit override via env wins
    import os
    env = os.environ.get("CONFLUENCE_WATCHLIST")
    candidates = ([pathlib.Path(env)] if env else []) + [
        pathlib.Path.cwd() / path,
        _REPO_ROOT / path,
    ]
    for c in candidates:
        if c.exists():
            return c, [str(x) for x in candidates]
    return None, [str(x) for x in candidates]


def _read_watchlist_file(path: str = "watchlist.json") -> dict:
    import json
    resolved, searched = _resolve_watchlist_path(path)
    if resolved is None:
        _log.info("no watchlist.json found; using defaults. searched: %s",
                  ", ".join(searched))
        return {}
    try:
        data = json.loads(resolved.read_text())
        _log.info("loaded watchlist from %s (%d sector keys, %d pinned)",
                  resolved, sum(1 for k in data if not k.startswith("_")),
                  len(data.get("_pinned", [])))
        return data
    except (json.JSONDecodeError, OSError) as exc:
        _log.warning("watchlist.json at %s is unreadable (%s); using defaults",
                     resolved, exc)
        return {}


def load_pinned(path: str = "watchlist.json") -> list[str]:
    """Symbols under the "_pinned" key in watchlist.json: always screened,
    regardless of sector rotation status. Quality gates still apply."""
    return [s.upper() for s in _read_watchlist_file(path).get("_pinned", [])]


def load_watchlist(path: str = "watchlist.json") -> dict[str, list[str]]:
    """Merge an optional watchlist.json over the defaults (searched in CWD,
    repo root, or CONFLUENCE_WATCHLIST). Keys are sector ETFs; a custom key
    REPLACES that sector's default list. Underscore keys (e.g. _pinned) are
    config, not sectors."""
    data = _read_watchlist_file(path)
    if not data:
        return DEFAULT_WATCHLIST
    custom = {k.upper(): [s.upper() for s in v]
              for k, v in data.items() if not k.startswith("_")}
    return {**DEFAULT_WATCHLIST, **custom}


class SetupComposer:
    def __init__(self, provider, regime_engine, rotation_engine, levels_engine,
                 volume_engine, momentum_engine, fundamentals_engine,
                 screener_engine, watchlist: dict[str, list[str]] | None = None,
                 thesis_writer=None, options_engine=None,
                 pinned: list[str] | None = None):
        self.provider = provider
        self.regime = regime_engine
        self.rotation = rotation_engine
        self.levels = levels_engine
        self.volume = volume_engine
        self.momentum = momentum_engine
        self.fundamentals = fundamentals_engine
        self.screener = screener_engine
        self.watchlist = watchlist or load_watchlist()
        self.pinned = [s.upper() for s in pinned] if pinned is not None else load_pinned()
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

    def compose(self, max_setups: int | None = None,
                force_direction: str | None = None) -> dict:
        """force_direction ("long"/"short") overrides the regime's choice for
        this call only — used by the Book's both-sides view. None (default)
        preserves the existing config/regime resolution exactly."""
        cfg = get_config()
        if max_setups is None:
            max_setups = cfg["compose"]["max_setups"]
        min_score = cfg["risk"]["min_score"]
        min_rr_t1, min_rr_t2 = cfg["risk"]["min_rr_t1"], cfg["risk"]["min_rr_t2"]
        chop_mode = cfg["gates"]["chop_mode"]

        regime = self.regime.get_regime()
        vix_state = next(c for c in regime["components"]
                         if c["name"] == "vix_alignment")["evidence"]["state"]

        # config gate honors the legacy env var through the loader overlay;
        # an explicit per-call force_direction wins over both.
        forced = str(cfg["gates"]["force_direction"]).lower()
        if forced not in ("long", "short"):
            forced = None
        if force_direction in ("long", "short"):
            forced = force_direction

        chop_warning = None
        if regime["regime"] == "chop" and not forced:
            chop_reason = (f"Regime is chop (score {regime['risk_score']:+.1f}) "
                           f"with VIX {vix_state.replace('_', ' ')} — "
                           "no-trade conditions. Standing aside is the setup.")
            if chop_mode == "hard":
                return {"regime": regime, "setups": [], "suppressed": [],
                        "no_trade": True, "forced": False,
                        "chop_gate": "hard", "reason": chop_reason}
            # soft/off: fall through and compose anyway. This is the gate that
            # used to short-circuit before the funnel/pinned pool was ever
            # built — now it's a dial, and the funnel below still runs.
            if chop_mode == "soft":
                chop_warning = ("CHOP GATE OVERRIDDEN (soft mode): " + chop_reason
                                + " Setups below are counter-policy — size down "
                                  "or stand aside.")

        direction = forced or ("long" if (
            regime["regime"] == "risk_on"
            or (regime["regime"] == "chop" and regime["risk_score"] >= 0)
        ) else "short")
        board = self.rotation.get_leaderboard()
        status_by_etf = {e["symbol"]: e for e in board["etfs"]}
        active_etfs = [e for e in board["etfs"]
                       if e["status"] in ("leading", "improving")]

        stock_to_etf: dict[str, dict] = {}
        for etf in active_etfs:
            for stock in self.watchlist.get(etf["symbol"], []):
                if stock not in stock_to_etf:  # keep the strongest sector link
                    stock_to_etf[stock] = etf

        # Pinned symbols join the candidate pool regardless of rotation
        # status. Sector link: the watchlist sector containing the name (with
        # its REAL current status), else a "pinned" pseudo-sector.
        pinned_added = []
        for sym in self.pinned:
            if sym in stock_to_etf:
                continue
            home = next((etf_sym for etf_sym, names in self.watchlist.items()
                         if sym in names and etf_sym in status_by_etf), None)
            stock_to_etf[sym] = (status_by_etf[home] if home
                                 else {"symbol": "PINNED", "status": "pinned"})
            pinned_added.append(sym)

        screened = self.screener.screen(list(stock_to_etf)) if stock_to_etf else {"results": []}
        keep_classes = ({"canslim_leader", "laggard_turn"} if direction == "long"
                        else {"no_setup", "overextended"})  # shorts hunt broken structure

        class_counts: dict[str, int] = {}
        for r in screened["results"]:
            class_counts[r["classification"]] = class_counts.get(r["classification"], 0) + 1
        sectors_without_watchlist = sorted(
            e["symbol"] for e in active_etfs if not self.watchlist.get(e["symbol"]))
        funnel = {
            "active_sectors": [e["symbol"] for e in active_etfs],
            "pinned_candidates": pinned_added,
            "sectors_without_watchlist_entries": sectors_without_watchlist,
            "candidate_stocks": len(stock_to_etf),
            "screen_classifications": class_counts,
            "kept_classes": sorted(keep_classes),
            "passed_screen": sum(class_counts.get(k, 0) for k in keep_classes),
        }
        # pinned outcomes get summarized after the loop (see below)

        setups, suppressed = [], []
        for screen in screened["results"]:
            sym = screen["symbol"]
            if screen["classification"] not in keep_classes:
                # Pinned names never vanish silently: record why the screen
                # filtered them so the dashboard can explain it.
                if sym in self.pinned:
                    suppressed.append({
                        "symbol": sym, "pinned": True,
                        "reason": f"screen classified it {screen['classification']} "
                                  f"(need {' or '.join(sorted(keep_classes))})"})
                continue
            etf = stock_to_etf[sym]
            level_payload = self.levels.get_levels(sym)
            setup = self._construct(sym, direction, level_payload)
            if setup is None:
                suppressed.append({"symbol": sym, "pinned": sym in self.pinned,
                                   "reason": "no usable level structure"})
                continue
            if setup["risk_reward_t1"] < min_rr_t1 or setup["risk_reward_t2"] < min_rr_t2:
                suppressed.append({"symbol": sym, "pinned": sym in self.pinned,
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
                suppressed.append({"symbol": sym, "pinned": sym in self.pinned,
                                   "reason": f"confidence {scored['score']} below {min_score} floor"})
                continue

            evidence = {"levels": level_payload, "regime": regime, "screen": screen,
                        "phase": phase, "fundamentals": fund, "sector": etf,
                        "options": options_payload}
            check = validate_setup(setup, evidence)
            if not check["valid"]:
                suppressed.append({"symbol": sym, "pinned": sym in self.pinned,
                                   "reason": "failed evidence validation",
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
                "pinned": sym in self.pinned,
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
        pinned_setups = [s["symbol"] for s in setups if s.get("pinned")]
        pinned_suppressed = {s["symbol"]: s["reason"]
                             for s in suppressed if s.get("pinned")}
        funnel["pinned_outcomes"] = {
            sym: ("setup" if sym in pinned_setups
                  else pinned_suppressed.get(sym, "screened, no setup constructed"))
            for sym in self.pinned}

        out = {"regime": regime, "direction": direction,
               "setups": setups[:max_setups], "suppressed": suppressed,
               "no_trade": False, "forced": bool(forced), "funnel": funnel}
        if chop_warning:
            out["chop_gate"] = "soft"
            out["chop_warning"] = chop_warning
        return out

    # ------------------------------------------------------------------
    # Phase 14 — universe explorer.
    #
    # compose() answers "what should I trade today" and stays strictly
    # gated. explore() answers "show me the full picture": the same
    # pipeline for ANY watchlist ticker, with every gate EVALUATED and
    # REPORTED instead of silently dropping the card. Nothing is invented:
    # if the levels engine can't produce usable structure, the answer is
    # "no card", not a fabricated one.
    # ------------------------------------------------------------------

    def explore_universe(self) -> dict:
        """Every sector and ticker, cheap: rotation status only, no
        per-ticker engine work. The frontend expands lazily via explore()."""
        regime = self.regime.get_regime()
        board = self.rotation.get_leaderboard()
        status_by_etf = {e["symbol"]: e for e in board["etfs"]}

        sectors = []
        for etf_sym in sorted(self.watchlist):
            info = status_by_etf.get(etf_sym, {})
            sectors.append({
                "etf": etf_sym,
                "status": info.get("status", "unranked"),
                "rank_4w": info.get("rank_4w"),
                "active": info.get("status") in ("leading", "improving"),
                "tickers": [{"symbol": s, "pinned": s in self.pinned}
                            for s in self.watchlist[etf_sym]],
            })
        # rotation-tracked ETFs with no watchlist entries still show up,
        # so the gap is visible instead of invisible
        for e in board["etfs"]:
            if e["symbol"] not in self.watchlist:
                sectors.append({"etf": e["symbol"], "status": e["status"],
                                "rank_4w": e.get("rank_4w"),
                                "active": e["status"] in ("leading", "improving"),
                                "tickers": []})

        forced = str(get_config()["gates"]["force_direction"]).lower()
        direction = forced if forced in ("long", "short") else (
            "long" if (regime["regime"] == "risk_on"
                       or (regime["regime"] == "chop"
                           and regime["risk_score"] >= 0)) else "short")
        return {"regime": {"regime": regime["regime"],
                           "risk_score": regime["risk_score"]},
                "direction": direction,
                "pinned": list(self.pinned),
                "sectors": sectors}

    def explore(self, symbol: str, direction: str | None = None) -> dict:
        """Full setup card for one ticker regardless of gates, with a
        per-gate pass/fail report. Same construction, scoring, validation,
        and thesis as compose() — the card is real engine output; only the
        *filtering* is deferred to the reader."""
        sym = symbol.strip().upper()
        cfg = get_config()
        min_score = cfg["risk"]["min_score"]
        min_rr_t1, min_rr_t2 = cfg["risk"]["min_rr_t1"], cfg["risk"]["min_rr_t2"]

        regime = self.regime.get_regime()
        vix_state = next(c for c in regime["components"]
                         if c["name"] == "vix_alignment")["evidence"]["state"]

        if direction not in ("long", "short"):
            forced = str(cfg["gates"]["force_direction"]).lower()
            direction = forced if forced in ("long", "short") else (
                "long" if (regime["regime"] == "risk_on"
                           or (regime["regime"] == "chop"
                               and regime["risk_score"] >= 0)) else "short")

        gates: list[dict] = []

        def gate(name, passed, detail):
            gates.append({"name": name, "passed": bool(passed),
                          "detail": detail})

        chop_ok = not (regime["regime"] == "chop"
                       and cfg["gates"]["chop_mode"] == "hard")
        gate("regime", chop_ok,
             f"{regime['regime']} ({regime['risk_score']:+.1f})"
             + ("" if chop_ok else " — hard chop gate: nothing arms today"))

        # sector context (a ticker outside any active sector still explores)
        board = self.rotation.get_leaderboard()
        status_by_etf = {e["symbol"]: e for e in board["etfs"]}
        home = next((etf for etf, names in self.watchlist.items()
                     if sym in names), None)
        etf_info = status_by_etf.get(home, {}) if home else {}
        sector_status = etf_info.get("status", "unranked")
        gate("sector_rotation", sector_status in ("leading", "improving"),
             f"{home or 'no home sector'} is {sector_status}"
             + ("" if sym not in self.pinned else " (pinned bypasses this)"))

        # screen classification
        keep_classes = ({"canslim_leader", "laggard_turn"} if direction == "long"
                        else {"no_setup", "overextended"})
        screen = None
        try:
            results = self.screener.screen([sym])["results"]
            screen = results[0] if results else None
        except Exception:
            screen = None
        if screen is None:
            screen = {"symbol": sym, "classification": "unavailable",
                      "passes": 0, "total_checks": 0, "structure": {},
                      "relative_strength_vs_spy_pct": 0.0,
                      "extension_vs_21d_pct": 0.0}
        gate("screen_class", screen["classification"] in keep_classes,
             f"{screen['classification']} ({screen.get('passes', 0)}/"
             f"{screen.get('total_checks', 0)} checks; {direction} wants "
             f"{' or '.join(sorted(keep_classes))})")

        # levels + construction — the one hard stop: no structure, no card
        level_payload = self.levels.get_levels(sym)
        setup = self._construct(sym, direction, level_payload)
        if setup is None:
            return {"symbol": sym, "direction": direction, "card": None,
                    "gates": gates, "in_composed": False,
                    "error": "no usable level structure — the levels engine "
                             "found no cluster geometry to build entry/stop/"
                             "targets from, and inventing them is exactly "
                             "what this system refuses to do"}

        rr_ok = (setup["risk_reward_t1"] >= min_rr_t1
                 and setup["risk_reward_t2"] >= min_rr_t2)
        gate("risk_reward", rr_ok,
             f"T1 {setup['risk_reward_t1']} / T2 {setup['risk_reward_t2']} "
             f"vs floors {min_rr_t1}/{min_rr_t2}")

        # the same context compose() builds, with per-field degradation
        daily = self.provider.get_bars(BarRequest(sym, "1d", 400))
        phase = self.volume.get_phase(sym)
        divs = self.momentum.get_divergences(sym)["divergences"]
        fund = self.fundamentals.get_snapshot(sym)
        dollar_vol = float((daily["close"] * daily["volume"]).tail(20).mean() / 1e6)
        ctx = {
            "regime": regime["regime"], "regime_risk_score": regime["risk_score"],
            "vix_alignment_state": vix_state,
            "sector_etf": home or "N/A", "sector_status": sector_status,
            "sector_rank_4w": etf_info.get("rank_4w"),
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
                options_payload = None

        scored = score_setup(direction, ctx)
        gate("confidence", scored["score"] >= min_score,
             f"{scored['score']} vs {min_score} floor")

        evidence = {"levels": level_payload, "regime": regime, "screen": screen,
                    "phase": phase, "fundamentals": fund,
                    "sector": {"symbol": home or "N/A", "status": sector_status},
                    "options": options_payload}
        check = validate_setup(setup, evidence)
        gate("evidence_validation", check["valid"],
             "every price traces to engine evidence" if check["valid"]
             else f"violations: {check['violations']}")

        setup |= {
            "options": options_payload,
            "instrument_suggestion": ctx.get("contract"),
            "instrument": (ctx.get("contract") or {}).get("instrument", "stock"),
            "confidence": scored["score"],
            "score_components": scored["components"],
            "risks": scored["risks"],
            "sector_etf": home or "N/A", "sector_status": sector_status,
            "pinned": sym in self.pinned,
            "classification": screen["classification"],
            "structure": screen.get("structure", {}),
            "invalidation": ("daily close below 21d MA or VIX reclaims pivot"
                             if direction == "long" else
                             "daily close above 21d MA or VIX loses pivot"),
            "earnings_flag": fund["in_earnings_window"],
            "thesis": (self.thesis_writer(setup, ctx, evidence)
                       if self.thesis_writer else self._template_thesis(setup, ctx)),
            "validated": check["valid"],
            "computed_at": level_payload["computed_at"],
            "exploratory": True,
        }
        # pinned bypasses rotation, matching compose(); everything else must pass
        required = [g for g in gates
                    if not (g["name"] == "sector_rotation" and sym in self.pinned)]
        return {"symbol": sym, "direction": direction, "card": setup,
                "gates": gates,
                "in_composed": all(g["passed"] for g in required)}
