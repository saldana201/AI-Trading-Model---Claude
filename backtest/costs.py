"""Phase 17 — transaction costs and slippage.

Every R-multiple the harness has reported so far is *gross*: fills at the
trigger bar's close, no commission, no slippage, no bid-ask. That is the single
most dangerous remaining approximation, because it is not a small uniform haircut
— it is a drag that scales inversely with how tight your stop is, and it lands
hardest on exactly the setups that look best (tight stop, high R:R). The
published cautionary case is FinMem: +23.26% cumulative became **-22.04%** once
a different window and transaction costs were applied. A sign reversal, from
costs.

Design rules, same as everywhere else in this system:

- **Glass box.** `cost_in_r()` returns not just a number but the itemized
  components and the assumptions used, so a cost drag can be audited the same
  way a price level can. Nothing is a magic constant hidden in a formula.
- **Engine evidence over guesses.** For options, the dominant cost is crossing
  the bid-ask. `options_mcp` already computes `spread_pct` per contract, so the
  model consumes that real number when it is present and only falls back to a
  configured default when it is not — and says which one it used.
- **Costs are expressed in R**, because R is the unit the whole system already
  speaks. A drag of 0.08R means every trade starts 8% of one risk unit in the
  hole, win or lose.

The options approximation, stated plainly
-----------------------------------------
For a debit spread the maximum loss is the net debit paid. A trader sizing so
that the position's worst case equals the trade's dollar risk therefore has
debit ≈ risk. Crossing the spread on the way in and again on the way out costs
approximately `spread_pct` of the debit, hence ≈ `spread_pct` expressed in R.
That is an approximation, not an identity — the harness prices stock geometry,
not option P&L — and `assumptions` says so on every result that relies on it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

OPTION_INSTRUMENTS = {"call", "put", "call_debit_spread", "put_debit_spread"}
SPREAD_INSTRUMENTS = {"call_debit_spread", "put_debit_spread"}


@dataclass(frozen=True)
class CostModel:
    """Per-trade friction. Defaults are deliberately mid-range retail, not
    optimistic: change them to match your broker rather than trusting these."""

    # --- stock ---
    slippage_bps: float = 5.0            # each side, in basis points of price
    commission_per_share: float = 0.005  # each side

    # --- options ---
    option_spread_pct: float | None = None      # hard override, else engine value
    default_option_spread_pct: float = 0.05     # used only when engine is silent
    commission_per_contract: float = 0.65       # each side, each leg
    contract_multiplier: int = 100

    # scale everything at once, for sensitivity curves
    multiplier: float = 1.0

    def scaled(self, k: float) -> "CostModel":
        return CostModel(**{**self.__dict__, "multiplier": self.multiplier * k})


def _is_option(instrument: str | None) -> bool:
    return (instrument or "stock") in OPTION_INSTRUMENTS


def cost_in_r(entry: float, stop: float, instrument: str | None = "stock",
              spread_pct: float | None = None,
              model: CostModel | None = None) -> dict:
    """Round-trip cost of one trade, expressed in R.

    Returns {"r_drag", "components", "assumptions", "instrument"} — the drag is
    what the harness subtracts from a gross R-multiple; the rest is the audit
    trail.
    """
    m = model or CostModel()
    risk = abs(float(entry) - float(stop))
    if risk <= 0:
        return {"r_drag": 0.0, "components": [],
                "assumptions": ["zero risk distance — cost not computable"],
                "instrument": instrument or "stock"}

    components: list[dict] = []
    assumptions: list[str] = []

    if _is_option(instrument):
        if m.option_spread_pct is not None:
            sp, src = m.option_spread_pct, "config override"
        elif spread_pct is not None:
            sp, src = float(spread_pct), "options engine (contract_quality)"
        else:
            sp, src = m.default_option_spread_pct, "default (engine value absent)"
            assumptions.append(
                "no per-contract spread available; used the configured default")
        drag = sp * m.multiplier
        components.append({"name": "bid_ask_round_trip", "r": round(drag, 5),
                           "detail": f"spread {sp:.2%} of debit", "source": src})
        assumptions.append(
            "debit ≈ dollar risk for a defined-risk spread, so spread cost in "
            "R ≈ spread as a fraction of debit")

        legs = 2 if (instrument in SPREAD_INSTRUMENTS) else 1
        # Commission needs the debit in dollars; approximate debit by the risk
        # per share times the multiplier (same debit≈risk assumption as above).
        debit_dollars = max(risk * m.contract_multiplier, 1e-9)
        comm = (2 * legs * m.commission_per_contract) / debit_dollars * m.multiplier
        components.append({"name": "commission", "r": round(comm, 5),
                           "detail": f"{legs} leg(s) × 2 sides × "
                                     f"${m.commission_per_contract}/contract",
                           "source": "config"})
        assumptions.append("commission expressed against an approximated debit")
        total = drag + comm
    else:
        slip_per_share = float(entry) * (m.slippage_bps / 10_000.0)
        slip_r = (2 * slip_per_share) / risk * m.multiplier
        components.append({"name": "slippage", "r": round(slip_r, 5),
                           "detail": f"{m.slippage_bps}bps × 2 sides on "
                                     f"{entry}", "source": "config"})
        comm_r = (2 * m.commission_per_share) / risk * m.multiplier
        components.append({"name": "commission", "r": round(comm_r, 5),
                           "detail": f"${m.commission_per_share}/share × 2 sides",
                           "source": "config"})
        assumptions.append("stock fills; slippage symmetric on entry and exit")
        total = slip_r + comm_r

    return {"r_drag": round(total, 5), "components": components,
            "assumptions": assumptions, "instrument": instrument or "stock"}


def apply_cost(gross_r: float | None, drag: float) -> float | None:
    """Net R after friction. Costs are paid win or lose, so the drag always
    subtracts — a +2.0R winner and a -1.0R loser both get worse."""
    if gross_r is None:
        return None
    return round(gross_r - drag, 4)


# ---------------------------------------------------------------------------
# Portfolio-level sensitivity — the FINSABER check
# ---------------------------------------------------------------------------

def cost_sensitivity(gross_rs: list, drags: list,
                     multipliers: tuple = (0.0, 0.5, 1.0, 2.0, 3.0)) -> dict:
    """How the edge decays as friction rises.

    `gross_rs` and `drags` are parallel per-trade lists. Reports average net R
    at each cost multiple, the breakeven drag that would zero the edge, and the
    headline boolean: does the sign flip once costs are real?
    """
    rows = [(g, d) for g, d in zip(gross_rs, drags) if g is not None]
    if not rows:
        return {"available": False, "reason": "no filled trades"}

    n = len(rows)
    gross_avg = sum(g for g, _ in rows) / n
    mean_drag = sum(d for _, d in rows) / n

    curve = []
    for k in multipliers:
        net = sum(g - d * k for g, d in rows) / n
        wins = sum(1 for g, d in rows if (g - d * k) > 0)
        curve.append({"cost_multiple": k, "avg_r": round(net, 4),
                      "win_rate": round(wins / n, 4)})

    net_at_1x = next(c["avg_r"] for c in curve if c["cost_multiple"] == 1.0)
    out = {
        "available": True,
        "n": n,
        "gross_avg_r": round(gross_avg, 4),
        "modeled_avg_drag_r": round(mean_drag, 5),
        "net_avg_r": net_at_1x,
        "curve": curve,
        "sign_flip_under_costs": bool(gross_avg > 0 >= net_at_1x),
    }
    # Breakeven: the uniform drag that would zero the gross edge.
    out["breakeven_drag_r"] = round(gross_avg, 5) if gross_avg > 0 else None
    if mean_drag > 0 and gross_avg > 0:
        out["cost_headroom_x"] = round(gross_avg / mean_drag, 2)
    out["verdict"] = _verdict(out)
    return out


def _verdict(s: dict) -> str:
    if s["sign_flip_under_costs"]:
        return ("EDGE DOES NOT SURVIVE COSTS — gross is positive but net is not. "
                "Do not promote this configuration.")
    if s["gross_avg_r"] <= 0:
        return "no gross edge to begin with; costs are not the binding problem"
    head = s.get("cost_headroom_x")
    if head is not None and head < 2:
        return (f"edge survives but with thin headroom ({head}× modeled cost) — "
                "fragile to worse fills or wider spreads")
    return f"edge survives modeled costs with {head}× headroom"


def render_costs(s: dict) -> str:
    if not s.get("available"):
        return f"costs: unavailable ({s.get('reason')})"
    lines = [
        f"costs: n={s['n']} gross avg R={s['gross_avg_r']} → "
        f"net avg R={s['net_avg_r']} (avg drag {s['modeled_avg_drag_r']}R)",
        "  cost curve: " + "  ".join(
            f"{c['cost_multiple']}x:{c['avg_r']}" for c in s["curve"]),
    ]
    if s.get("cost_headroom_x") is not None:
        lines.append(f"  breakeven drag={s['breakeven_drag_r']}R  "
                     f"headroom={s['cost_headroom_x']}×")
    lines.append(f"  -> {s['verdict']}")
    return "\n".join(lines)
