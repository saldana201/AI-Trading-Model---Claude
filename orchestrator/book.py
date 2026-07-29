"""Phase 16 — the Book: setups grouped by direction and instrument.

The mental model this module enforces
-------------------------------------
"Long / Short / Options" is not three parallel buckets — it is *two orthogonal
axes*, and conflating them double-counts every trade:

    direction   long | short                    <- chosen by the regime gate
    instrument  stock | call | put              <- chosen by the options engine
                | call_debit_spread             (IV rank + liquidity)
                | put_debit_spread

A call spread on AVGO is a LONG setup *and* an OPTIONS setup. It is one trade,
not two. So this module partitions by **direction** (mutually exclusive, every
setup lands in exactly one side) and exposes **options as a cross-cutting lens**
over that same partition — explicitly labeled as a view, not a third bucket.

Why the empty sides need explaining
-----------------------------------
`SetupComposer.compose()` resolves a single direction per run: risk_on hunts
longs, risk_off hunts shorts. So on any given day one side of the book is empty
*by design*, not by failure. Same lesson as the chop gate: if the UI shows a
blank "Short setups" panel with no reason, the system looks broken when it is
working correctly. Every empty group here carries a `reason` string.

Likewise, when the options engine falls back to shares it already returns *why*
("no liquid strike near entry (OI < 200 or spread > 8%)"). That reason is
genuinely useful and currently buried in the payload — the book surfaces it.
"""

from __future__ import annotations

OPTION_INSTRUMENTS = {"call", "put", "call_debit_spread", "put_debit_spread"}

_LABELS = {
    "stock": "STOCK",
    "call": "CALL",
    "put": "PUT",
    "call_debit_spread": "CALL SPREAD",
    "put_debit_spread": "PUT SPREAD",
}


def instrument_label(instrument: str | None) -> str:
    """Human badge for a setup card. Unknown values degrade to upper-case."""
    if not instrument:
        return "STOCK"
    return _LABELS.get(instrument, str(instrument).replace("_", " ").upper())


def is_options(setup: dict) -> bool:
    return (setup.get("instrument") or "stock") in OPTION_INSTRUMENTS


def contract_summary(setup: dict) -> dict | None:
    """Flatten the options engine's contract choice into the few fields a card
    actually renders. Returns None for share trades.

    Every value is copied straight from `instrument_suggestion` (the engine's
    own output) — nothing is derived or invented here, so the anti-hallucination
    invariant holds: the book is a *view*, never a source of new numbers.
    """
    if not is_options(setup):
        return None
    c = setup.get("instrument_suggestion") or {}
    out = {
        "instrument": setup.get("instrument"),
        "label": instrument_label(setup.get("instrument")),
        "expiry": c.get("expiry"),
        "dte": c.get("dte"),
        "iv": c.get("iv"),
        "iv_rank": c.get("iv_rank"),
        "open_interest": c.get("oi"),
        "spread_pct": c.get("spread_pct"),
        "expected_move": c.get("expected_move"),
        "t1_within_expected_move": c.get("t1_within_expected_move"),
        "reason": c.get("reason"),
        "notes": c.get("notes") or [],
    }
    # single leg vs vertical: carry whichever strike fields the engine set
    if c.get("strike") is not None:
        out["strike"] = c.get("strike")
    if c.get("long_strike") is not None:
        out["long_strike"] = c.get("long_strike")
        out["short_strike"] = c.get("short_strike")
    return out


def stock_only_reason(setup: dict) -> str | None:
    """Why this setup is shares rather than contracts, when the engine said so."""
    if is_options(setup):
        return None
    c = setup.get("instrument_suggestion")
    if isinstance(c, dict) and c.get("reason"):
        return c["reason"]
    if c is None:
        return "options engine not attached to this run"
    return None


def _card(setup: dict) -> dict:
    """A setup reduced to what the book renders, plus the instrument view."""
    return {
        "symbol": setup.get("symbol"),
        "direction": setup.get("direction"),
        "instrument": setup.get("instrument") or "stock",
        "instrument_label": instrument_label(setup.get("instrument")),
        "is_options": is_options(setup),
        "confidence": setup.get("confidence"),
        "entry_trigger": setup.get("entry_trigger"),
        "stop": setup.get("stop"),
        "target_1": setup.get("target_1"),
        "target_2": setup.get("target_2"),
        "risk_reward_t1": setup.get("risk_reward_t1"),
        "sector_etf": setup.get("sector_etf"),
        "classification": setup.get("classification"),
        "pinned": bool(setup.get("pinned")),
        "earnings_flag": setup.get("earnings_flag"),
        "thesis": setup.get("thesis"),
        "risks": setup.get("risks"),
        "contract": contract_summary(setup),
        "stock_only_reason": stock_only_reason(setup),
    }


def _empty_reason(side: str, plan: dict) -> str:
    """Explain an empty direction group in the plan's own terms.

    The distinction that matters: a side can be empty because it was never
    scanned (regime picked the other direction) or because it *was* scanned and
    nothing cleared the gates. Reporting the first when the second happened is
    the kind of quiet inaccuracy that makes a glass-box system untrustworthy.
    """
    if plan.get("no_trade"):
        return ("regime gate returned no-trade conditions — nothing was "
                "composed on either side today")

    if plan.get("both_directions"):
        n = len(plan.get("suppressed") or [])
        tail = f" ({n} candidate{'s' if n != 1 else ''} suppressed)" if n else ""
        return (f"{side}s were scanned, but none cleared the confluence "
                f"gates{tail}")

    active = plan.get("direction")
    regime = (plan.get("regime") or {}).get("regime")
    if active and active != side:
        forced = plan.get("forced")
        how = ("direction is forced by config" if forced
               else f"regime is {regime or 'unresolved'}")
        return (f"{how}, so the composer hunted {active}s this run — "
                f"{side}s were not scanned")
    return f"no {side} setup cleared the confluence gates"


def build_book(plan: dict) -> dict:
    """Group a compose() plan into the Book.

    Returns:
      long / short  — the direction partition (a setup appears in exactly one)
      options       — cross-cutting lens: every setup traded as contracts
      shares        — cross-cutting lens: every setup traded as stock,
                      each carrying the engine's reason for the fallback
      counts        — quick tallies, incl. the overlap that makes the point
    """
    setups = list(plan.get("setups") or [])
    cards = [_card(s) for s in setups]

    longs = [c for c in cards if c["direction"] == "long"]
    shorts = [c for c in cards if c["direction"] == "short"]
    options = [c for c in cards if c["is_options"]]
    shares = [c for c in cards if not c["is_options"]]

    def group(side, rows):
        g = {"side": side, "count": len(rows), "setups": rows}
        if not rows:
            g["reason"] = _empty_reason(side, plan)
        return g

    book = {
        "generated_from": {
            "direction": plan.get("direction"),
            "regime": (plan.get("regime") or {}).get("regime"),
            "no_trade": bool(plan.get("no_trade")),
            "forced": plan.get("forced"),
        },
        "long": group("long", longs),
        "short": group("short", shorts),
        "options": {
            "view": "cross-cutting",
            "count": len(options),
            "setups": options,
            "note": ("these are the same trades as above, shown by instrument: "
                     "a call spread is a long setup, a put is a short setup"),
        },
        "shares": {
            "view": "cross-cutting",
            "count": len(shares),
            "setups": shares,
            "note": "setups the options engine routed to stock, with its reason",
        },
        "counts": {
            "total": len(cards),
            "long": len(longs),
            "short": len(shorts),
            "options": len(options),
            "shares": len(shares),
            "by_instrument": _by_instrument(cards),
        },
    }
    if not options and cards:
        book["options"]["reason"] = _options_empty_reason(cards)
    return book


def _by_instrument(cards: list[dict]) -> dict:
    out: dict[str, int] = {}
    for c in cards:
        out[c["instrument"]] = out.get(c["instrument"], 0) + 1
    return out


def _options_empty_reason(cards: list[dict]) -> str:
    reasons = [c["stock_only_reason"] for c in cards if c["stock_only_reason"]]
    if reasons:
        # the engine's most common stated reason reads better than a generic line
        top = max(set(reasons), key=reasons.count)
        return f"every setup routed to shares — {top}"
    return "every setup routed to shares"


def render_book(book: dict) -> str:
    """Plain-text Book for the morning brief and CLI."""
    lines = []
    for side in ("long", "short"):
        g = book[side]
        lines.append(f"{side.upper()} ({g['count']})")
        if not g["setups"]:
            lines.append(f"  — {g['reason']}")
        for c in g["setups"]:
            pin = " *" if c["pinned"] else ""
            lines.append(
                f"  {c['symbol']:<6}{pin} {c['instrument_label']:<12} "
                f"conf {c['confidence']}  entry {c['entry_trigger']} "
                f"stop {c['stop']} T1 {c['target_1']}")
    o = book["options"]
    lines.append(f"OPTIONS VIEW ({o['count']}) — {o['note']}")
    for c in o["setups"]:
        k = c["contract"] or {}
        legs = (f"{k.get('long_strike')}/{k.get('short_strike')}"
                if k.get("long_strike") is not None else k.get("strike"))
        lines.append(f"  {c['symbol']:<6} {c['instrument_label']:<12} "
                     f"{legs} exp {k.get('expiry')} ({k.get('dte')}d) "
                     f"IVR {k.get('iv_rank')}")
    if book["shares"]["count"]:
        lines.append(f"SHARES VIEW ({book['shares']['count']})")
        for c in book["shares"]["setups"]:
            why = c["stock_only_reason"] or "—"
            lines.append(f"  {c['symbol']:<6} {why}")
    return "\n".join(lines)
