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


def select_contract(chain: dict, direction: str, entry: float, target_1: float,
                    target_2: float, horizon: str = "swing") -> dict:
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
    use_spread = iv_rank is not None and iv_rank >= HIGH_IV_RANK
    result = {
        "expiry": expiry["date"], "dte": expiry["dte"],
        "iv": chosen["iv"], "iv_rank": iv_rank,
        "oi": chosen["oi"], "spread_pct": chosen["spread_pct"],
        "expected_move": em, "t1_within_expected_move": t1_within_em,
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
            "reason": f"IV rank {iv_rank:.0%} ≥ {HIGH_IV_RANK:.0%} — define risk "
                      "with a debit spread",
        }
    else:
        result |= {"instrument": opt_type, "strike": chosen["strike"],
                   "reason": "IV not elevated — single leg acceptable"}
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
                 options_provider: OptionsProvider):
        self.prices = price_provider
        self.options = options_provider
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

    def select_contract(self, symbol: str, direction: str, entry: float,
                        target_1: float, target_2: float,
                        horizon: str = "swing") -> dict:
        return select_contract(self.chain(symbol), direction, entry,
                               target_1, target_2, horizon)

    def get_alignment(self, symbol: str, direction: str, entry: float,
                      target_1: float) -> dict:
        return options_alignment(self.get_gex_profile(symbol), direction,
                                 entry, target_1)
