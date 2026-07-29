"""options-mcp core logic (design doc §4.6, PRD §7 + §13).

GEX convention (documented approximation): dealers are assumed long customer-
bought calls and short customer-bought puts, so call OI contributes positive
dealer gamma and put OI negative. Dollar gamma per 1% move:

    GEX(k) = [Γ_call(k)·OI_call(k) − Γ_put(k)·OI_put(k)] · 100 · S² · 0.01

This is a positioning *estimate*, not dealer ground truth (design doc §11).

Interpretation rules baked into dealer zones: above the flip in positive
gamma, dealers dampen moves and big-OI strikes act as magnets/pins; below the
flip in negative gamma, dealers amplify and breaks accelerate.
"""

from __future__ import annotations

from collections import defaultdict

from .greeks import gamma, vanna, expected_move
from .providers import OptionsProvider
from ..shared.providers import BarRequest, DataProvider

MAX_SPREAD_PCT = 0.08    # bid/ask vs mid — PRD §13 "avoid wide spreads"
MIN_OI = 500
HIGH_IV_RANK = 0.55      # above this, prefer debit spreads


def gex_profile(chain: dict) -> dict:
    spot = chain["spot"]
    per_strike_gex: dict[float, float] = defaultdict(float)
    per_strike_vanna: dict[float, float] = defaultdict(float)
    for c in chain["contracts"]:
        t = c["dte"] / 365.0
        g = gamma(spot, c["strike"], c["iv"], t)
        v = vanna(spot, c["strike"], c["iv"], t)
        sign = 1.0 if c["type"] == "call" else -1.0
        per_strike_gex[c["strike"]] += sign * g * c["oi"] * 100 * spot * spot * 0.01
        per_strike_vanna[c["strike"]] += sign * v * c["oi"] * 100 * spot * 0.01

    strikes = sorted(per_strike_gex)
    profile = [{"strike": k,
                "gex_$m": round(per_strike_gex[k] / 1e6, 2),
                "vanna_$m": round(per_strike_vanna[k] / 1e6, 2)}
               for k in strikes]

    # Zero-gamma flip: where the cumulative net-GEX curve crosses zero
    # (low-strike puts dominate below, calls above) — linear interpolation.
    # Live chains carry strikes 50%+ away from spot whose near-zero gamma
    # makes the cumulative curve cross on noise far from the money, so the
    # flip is computed within a ±20% band around spot.
    band = [k for k in strikes if abs(k - spot) / spot <= 0.20] or strikes
    flip = None
    cum = 0.0
    prev_k, prev_cum = None, None
    for k in band:
        cum += per_strike_gex[k]
        if prev_cum is not None and prev_cum < 0 <= cum:
            frac = -prev_cum / (cum - prev_cum) if cum != prev_cum else 0.5
            flip = round(prev_k + frac * (k - prev_k), 2)
            break
        prev_k, prev_cum = k, cum

    call_wall = max(strikes, key=lambda k: per_strike_gex[k]) if strikes else None
    put_wall = min(strikes, key=lambda k: per_strike_gex[k]) if strikes else None
    total = sum(per_strike_gex.values())

    return {
        "symbol": chain["symbol"], "spot": spot,
        "zero_gamma_flip": flip,
        "call_wall": call_wall, "put_wall": put_wall,
        "net_gex_$m": round(total / 1e6, 1),
        "gamma_regime": ("positive" if flip is not None and spot > flip
                         else "negative" if flip is not None else "unknown"),
        "profile": profile,
        "convention": "dealers long calls / short puts (approximation)",
    }


def dealer_zones(profile: dict) -> dict:
    spot, flip = profile["spot"], profile["zero_gamma_flip"]
    regime = profile["gamma_regime"]
    return {
        "symbol": profile["symbol"], "spot": spot,
        "gamma_regime": regime,
        "zero_gamma_flip": flip,
        "call_wall": profile["call_wall"],
        "put_wall": profile["put_wall"],
        "reading": (
            "positive gamma: dealers dampen moves; call/put walls act as "
            "magnets and pin candidates" if regime == "positive" else
            "negative gamma: dealers amplify moves; breaks of big-OI strikes "
            "can accelerate" if regime == "negative" else
            "flip not resolvable from this chain"),
    }


def contract_quality(chain: dict, strike: float, expiry: str,
                     opt_type: str) -> dict:
    c = next((x for x in chain["contracts"]
              if x["strike"] == strike and x["expiry"] == expiry
              and x["type"] == opt_type), None)
    if c is None:
        return {"found": False, "strike": strike, "expiry": expiry, "type": opt_type}
    spread_pct = round((c["ask"] - c["bid"]) / c["mid"], 4) if c["mid"] > 0 else 1.0
    return {
        "found": True, "strike": strike, "expiry": expiry, "type": opt_type,
        "dte": c["dte"], "iv": c["iv"], "oi": c["oi"], "volume": c["volume"],
        "bid": c["bid"], "mid": c["mid"], "ask": c["ask"],
        "spread_pct": spread_pct,
        "liquid": c["oi"] >= MIN_OI and spread_pct <= MAX_SPREAD_PCT,
    }


def decide_structure(iv_rank: float | None, vrp: dict | None = None,
                     high_iv_rank: float = HIGH_IV_RANK) -> dict:
    """Single leg or debit spread? Combines the two vol signals.

    `iv_rank` asks: is IV high *for this name, against its own history*?
    `vrp` asks:     is IV high *against the volatility likely to be realized*?

    The second is the sharper question — it is the one that determines whether
    you are overpaying — so when the two disagree decisively, VRP wins. When VRP
    is equivocal (slightly rich / fair / slightly cheap) it defers to iv_rank
    rather than manufacturing a view from a number close to 1.0.

    vrp=None reproduces the pre-Phase-19 behaviour exactly.

    Returns {use_spread, reason, inputs} — `inputs` records both signals and
    which one decided, so the choice is auditable rather than asserted.
    """
    rank_says_spread = iv_rank is not None and iv_rank >= high_iv_rank
    inputs = {"iv_rank": iv_rank, "iv_rank_threshold": high_iv_rank,
              "iv_rank_says": "spread" if rank_says_spread else "single_leg"}

    verdict = (vrp or {}).get("verdict") if (vrp or {}).get("available") else None
    if verdict is None:
        inputs["vrp"] = None
        inputs["decided_by"] = "iv_rank"
        if rank_says_spread:
            reason = (f"IV rank {iv_rank:.0%} ≥ {high_iv_rank:.0%} — define risk "
                      "with a debit spread")
        else:
            reason = "IV not elevated — single leg acceptable"
        return {"use_spread": rank_says_spread, "reason": reason, "inputs": inputs}

    inputs["vrp"] = {"verdict": verdict, "ratio": vrp.get("ratio"),
                     "implied_vol": vrp.get("implied_vol"),
                     "forecast_vol": vrp.get("forecast_vol")}
    ratio = vrp.get("ratio")

    if verdict == "rich":
        vrp_says_spread = True
    elif verdict == "cheap":
        vrp_says_spread = False
    else:
        inputs["vrp_says"] = "not decisive"
        inputs["decided_by"] = "iv_rank"
        base = ("IV rank elevated" if rank_says_spread else "IV not elevated")
        reason = (f"{base}; variance risk premium {verdict.replace('_', ' ')} "
                  f"(IV/forecast {ratio}) is not decisive, deferring to IV rank")
        return {"use_spread": rank_says_spread, "reason": reason, "inputs": inputs}

    inputs["vrp_says"] = "spread" if vrp_says_spread else "single_leg"

    if vrp_says_spread == rank_says_spread:
        inputs["decided_by"] = "both agree"
        if vrp_says_spread:
            reason = (f"IV rank {iv_rank:.0%} and variance risk premium agree "
                      f"options are rich (IV {vrp['implied_vol']:.0%} vs forecast "
                      f"{vrp['forecast_vol']:.0%}) — debit spread")
        else:
            reason = (f"IV rank and variance risk premium agree options are not "
                      f"rich (IV {vrp['implied_vol']:.0%} vs forecast "
                      f"{vrp['forecast_vol']:.0%}) — single leg")
        return {"use_spread": vrp_says_spread, "reason": reason, "inputs": inputs}

    # Disagreement: the sharper signal wins, and says so out loud.
    inputs["decided_by"] = "variance_risk_premium (overrode iv_rank)"
    if vrp_says_spread:
        reason = (f"IV rank {iv_rank:.0%} is below the {high_iv_rank:.0%} "
                  f"threshold, but IV {vrp['implied_vol']:.0%} is well above the "
                  f"{vrp['forecast_vol']:.0%} forecast (ratio {ratio}) — options "
                  "are rich despite an unremarkable rank; debit spread")
    else:
        reason = (f"IV rank {iv_rank:.0%} looks elevated, but IV "
                  f"{vrp['implied_vol']:.0%} is below the "
                  f"{vrp['forecast_vol']:.0%} forecast (ratio {ratio}) — options "
                  "are cheap versus what should be realized; keep the convexity "
                  "of a single long leg")
    return {"use_spread": vrp_says_spread, "reason": reason, "inputs": inputs}


def select_contract(chain: dict, direction: str, entry: float, target_1: float,
                    target_2: float, horizon: str = "swing",
                    vrp: dict | None = None) -> dict:
    """PRD §13: call/put, strike, expiry, single-leg vs debit spread, with
    liquidity and expected-move checks. Falls back to stock with the reason."""
    opt_type = "call" if direction == "long" else "put"
    dte_lo, dte_hi = (21, 50) if horizon == "swing" else (0, 7)
    expiries = [e for e in chain["expiries"] if dte_lo <= e["dte"] <= dte_hi] \
        or sorted(chain["expiries"], key=lambda e: abs(e["dte"] - dte_lo))[:1]
    if not expiries:
        return {"instrument": "stock", "reason": "no usable expiry on the chain"}
    expiry = expiries[0]

    same = [c for c in chain["contracts"]
            if c["expiry"] == expiry["date"] and c["type"] == opt_type]
    if not same:
        return {"instrument": "stock", "reason": "empty chain for expiry"}

    # Strike: at/just inside the entry trigger (≈0.55–0.65 delta zone).
    side = (lambda c: c["strike"] <= entry) if direction == "long" \
        else (lambda c: c["strike"] >= entry)
    candidates = sorted((c for c in same if side(c)),
                        key=lambda c: abs(c["strike"] - entry)) \
        or sorted(same, key=lambda c: abs(c["strike"] - entry))

    notes, chosen = [], None
    for c in candidates[:4]:
        q = contract_quality(chain, c["strike"], expiry["date"], opt_type)
        if q["liquid"]:
            chosen = q
            break
        notes.append(f"{c['strike']} skipped (OI {q['oi']}, spread "
                     f"{q['spread_pct']:.1%})")
    if chosen is None:
        return {"instrument": "stock",
                "reason": "no liquid strike near entry "
                          f"(OI < {MIN_OI} or spread > {MAX_SPREAD_PCT:.0%})",
                "notes": notes}

    atm = min(same, key=lambda c: abs(c["strike"] - chain["spot"]))
    em = round(expected_move(chain["spot"], atm["iv"], expiry["dte"]), 2)
    t1_within_em = abs(target_1 - chain["spot"]) <= em
    if not t1_within_em:
        notes.append(f"target 1 sits outside the {em} expected move for this expiry")

    iv_rank = chain.get("iv_rank")
    decision = decide_structure(iv_rank, vrp)
    use_spread = decision["use_spread"]
    result = {
        "expiry": expiry["date"], "dte": expiry["dte"],
        "iv": chosen["iv"], "iv_rank": iv_rank,
        "oi": chosen["oi"], "spread_pct": chosen["spread_pct"],
        "expected_move": em, "t1_within_expected_move": t1_within_em,
        "structure_decision": decision["inputs"],
        "notes": notes,
    }
    if use_spread:
        short_side = [c for c in same if (c["strike"] >= target_2)] if direction == "long" \
            else [c for c in same if c["strike"] <= target_2]
        short_leg = (min(short_side, key=lambda c: abs(c["strike"] - target_2))
                     if short_side else None)
        result |= {
            "instrument": f"{opt_type}_debit_spread",
            "long_strike": chosen["strike"],
            "short_strike": short_leg["strike"] if short_leg else None,
            "reason": decision["reason"],
        }
    else:
        result |= {"instrument": opt_type, "strike": chosen["strike"],
                   "reason": decision["reason"]}
    return result


def options_alignment(profile: dict, direction: str, entry: float,
                      target_1: float) -> dict:
    """Score 0..1 for the confidence engine: where do entry/targets sit
    relative to the flip and walls?"""
    flip, cw, pw = (profile["zero_gamma_flip"], profile["call_wall"],
                    profile["put_wall"])
    value, reasons = 0.5, []
    if direction == "long":
        if flip is not None and entry > flip:
            value += 0.15; reasons.append("entry above zero-gamma flip")
        if cw is not None and entry < cw < target_1:
            value -= 0.3; reasons.append(f"call wall {cw} sits between entry and T1")
        elif cw is None or cw >= target_1:
            value += 0.2; reasons.append("no call-wall resistance before T1")
        if pw is not None and pw < entry:
            value += 0.1; reasons.append(f"put wall {pw} supports below entry")
    else:
        if flip is not None and entry < flip:
            value += 0.15; reasons.append("entry below zero-gamma flip")
        if pw is not None and target_1 < pw < entry:
            value -= 0.3; reasons.append(f"put wall {pw} sits between entry and T1")
        elif pw is None or pw <= target_1:
            value += 0.2; reasons.append("no put-wall support before T1")
        if cw is not None and cw > entry:
            value += 0.1; reasons.append(f"call wall {cw} caps above entry")
    return {"value": max(0.0, min(1.0, round(value, 2))), "reasons": reasons,
            "flip": flip, "call_wall": cw, "put_wall": pw}


class OptionsEngine:
    def __init__(self, price_provider: DataProvider,
                 options_provider: OptionsProvider,
                 volatility_engine=None):
        """volatility_engine (Phase 18) is optional. When attached, contract
        selection consults the variance risk premium instead of relying on
        iv_rank alone; when absent, behaviour is unchanged."""
        self.prices = price_provider
        self.options = options_provider
        self.volatility = volatility_engine
        self._chains: dict[str, dict] = {}

    def _spot(self, symbol: str) -> float:
        bars = self.prices.get_bars(BarRequest(symbol, "1d", 30))
        return float(bars["close"].iloc[-1])

    def chain(self, symbol: str) -> dict:
        if symbol not in self._chains:
            self._chains[symbol] = self.options.get_chain(symbol, self._spot(symbol))
        return self._chains[symbol]

    def get_gex_profile(self, symbol: str) -> dict:
        return gex_profile(self.chain(symbol))

    def get_dealer_zones(self, symbol: str) -> dict:
        return dealer_zones(self.get_gex_profile(symbol))

    def get_contract_quality(self, symbol: str, strike: float, expiry: str,
                             opt_type: str) -> dict:
        return contract_quality(self.chain(symbol), strike, expiry, opt_type)

    def _vrp_for(self, symbol: str, chain: dict) -> dict | None:
        """Variance risk premium for this chain's ATM IV, horizon-matched to the
        nearest swing expiry. Returns None (silently) if no volatility engine is
        attached or the fit is unavailable — the caller then falls back to
        iv_rank alone rather than failing."""
        if self.volatility is None:
            return None
        try:
            expiries = chain.get("expiries") or []
            swing = [e for e in expiries if 21 <= e["dte"] <= 50] or expiries
            if not swing:
                return None
            dte = swing[0]["dte"]
            spot = chain["spot"]
            atm = min(chain["contracts"],
                      key=lambda c: abs(c["strike"] - spot))
            return self.volatility.get_iv_comparison(
                symbol, atm["iv"], dte).get("variance_risk_premium")
        except Exception:
            return None

    def select_contract(self, symbol: str, direction: str, entry: float,
                        target_1: float, target_2: float,
                        horizon: str = "swing") -> dict:
        chain = self.chain(symbol)
        return select_contract(chain, direction, entry, target_1, target_2,
                               horizon, vrp=self._vrp_for(symbol, chain))

    def get_alignment(self, symbol: str, direction: str, entry: float,
                      target_1: float) -> dict:
        return options_alignment(self.get_gex_profile(symbol), direction,
                                 entry, target_1)
