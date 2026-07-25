"""Backtest harness (the build that decides whether the system is trusted).

Walks the engines through history with ReplayProvider: at each as-of point
the composer builds setups exactly as it would have that day, then the Phase 4
lifecycle state machine is stepped forward over the actual subsequent bars to
record what happened — filled or not, stopped, trimmed, trailed, deteriorated,
or still open at the horizon. Outcomes are expressed in R-multiples (P&L per
unit of initial risk), with the trade-management semantics the live engine
uses: half off at T1, stop to breakeven, trail the remainder.

The report buckets results by confidence so the question "does an 8.1 setup
actually beat a 6.4?" gets an empirical answer, and compares mean component
values in winners vs losers to show which score inputs carry signal. Every
threshold tuned from this output replaces a guess with evidence.

Approximations (documented, not hidden):
- Fills at the trigger bar's close (no slippage/commissions).
- The market guard freezes VIX pivot and the index weekly pivot as-of the
  compose date; forward bars test prices against those frozen levels.
- Daily bars: intraday sequencing within a bar is invisible; if a bar spans
  both stop and target, the close decides — same limitation as live daily
  cadence.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from backtest.statistics import rigor_block, render_rigor
from alerts.engine import arm_from_setup
from alerts.lifecycle import step, TERMINAL, TRIGGERED, TRIMMED_T1
from engines.shared.providers import BarRequest, ReplayProvider
from engines.shared.levels import weekly_pivot_levels, rvol
from engines.vix_mcp.logic import compute_vix_levels, VIX_SYMBOL


@dataclass
class Outcome:
    symbol: str
    as_of: str
    direction: str
    confidence: float
    entry_trigger: float
    stop: float
    target_1: float
    target_2: float
    sector_etf: str
    classification: str
    components: dict
    final_state: str          # NO_FILL / CLOSED / STOPPED / DETERIORATED /
                              # INVALIDATED / OPEN_AT_HORIZON
    realized_r: float | None  # None when never filled
    bars_held: int
    exit_reason: str

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def realized_r_from_events(trade, events: list[dict],
                           last_close: float) -> tuple[float | None, str, int]:
    """R-multiple under live trade-management semantics: 50% off at T1,
    remainder at the final exit (or marked at last_close if still open)."""
    entry = trade.entry_price
    if entry is None:
        return None, "NO_FILL", 0
    risk = abs(entry - trade.stop)
    sign = 1.0 if trade.direction == "long" else -1.0
    trimmed = any(e["to_state"] == TRIMMED_T1 for e in events)
    first = next(i for i, e in enumerate(events) if e["to_state"] == TRIGGERED)
    bars_held = len(events) - first  # event-count proxy; refined below by caller

    if trade.state in TERMINAL and trade.state != "INVALIDATED":
        exit_price = events[-1]["price"]
        state, reason = trade.state, events[-1]["reason"]
    elif trade.state == "INVALIDATED":
        return None, "NO_FILL", 0
    else:
        exit_price, state, reason = last_close, "OPEN_AT_HORIZON", "horizon reached"

    if trimmed:
        pnl = 0.5 * sign * (trade.target_1 - entry) + 0.5 * sign * (exit_price - entry)
    else:
        pnl = sign * (exit_price - entry)
    return round(pnl / risk, 3), state, bars_held


class Backtest:
    def __init__(self, base_provider, composer_factory, span_bars: int = 252,
                 step_bars: int = 5, horizon_bars: int = 15,
                 index_symbol: str = "QQQ", n_trials: int = 1,
                 trial_sharpe_variance: float | None = None):
        """composer_factory(provider) -> SetupComposer bound to that provider.
        span_bars of history are replayed; the composer runs every step_bars;
        each setup is simulated horizon_bars forward.

        n_trials / trial_sharpe_variance feed the Deflated Sharpe Ratio: set
        n_trials to the number of distinct weight/threshold configurations you
        have evaluated against this data, so the report deflates the result for
        selection bias instead of reporting a naively optimistic PSR."""
        self.base = base_provider
        self.factory = composer_factory
        self.span = span_bars
        self.step = step_bars
        self.horizon = horizon_bars
        self.index_symbol = index_symbol
        self.n_trials = n_trials
        self.trial_sharpe_variance = trial_sharpe_variance

    # ---------- forward simulation ----------

    def _frozen_guard(self, replay) -> dict:
        vix = replay.get_bars(BarRequest(VIX_SYMBOL, "1d", 180))
        idx = replay.get_bars(BarRequest(self.index_symbol, "1d", 200))
        return {
            "vix_pivot": compute_vix_levels(vix).get("pivot"),
            "index_weekly_pivot": weekly_pivot_levels(idx)["weekly_pivot"],
        }

    def _simulate(self, setup: dict, full_bars, asof_idx: int,
                  vix_full, idx_full, frozen: dict) -> tuple:
        atr_proxy = max(abs(setup["entry_trigger"] - setup["stop"]) * 0.8, 1e-6)
        trade = arm_from_setup(setup, atr14=atr_proxy)
        events: list[dict] = []
        end = min(asof_idx + self.horizon, len(full_bars) - 1)
        bars_held = 0
        for i in range(asof_idx + 1, end + 1):
            row = full_bars.iloc[i]
            vix_c = float(vix_full["close"].iloc[min(i, len(vix_full) - 1)])
            idx_c = float(idx_full["close"].iloc[min(i, len(idx_full) - 1)])

            def guard(direction, _v=vix_c, _i=idx_c):
                vp, wp = frozen["vix_pivot"], frozen["index_weekly_pivot"]
                if vp is None:
                    return False, {}
                bad = ((_v > vp and _i < wp) if direction == "long"
                       else (_v < vp and _i > wp))
                return bad, {"vix": _v, "vix_pivot": vp,
                             "index": _i, "index_weekly_pivot": wp}

            evs = step(trade, {"close": float(row["close"]),
                               "high": float(row["high"]),
                               "low": float(row["low"]),
                               "time": str(full_bars.index[i]),
                               "rvol": 99.0},  # RVOL gate evaluated at compose time
                       market_guard=guard)
            events.extend(evs)
            if trade.entry_price is not None:
                bars_held += 1
            if trade.state in TERMINAL:
                break
        last_close = float(full_bars["close"].iloc[end])
        r, state, _ = realized_r_from_events(trade, events, last_close)
        return r, state, bars_held, (events[-1]["reason"] if events else "never triggered")

    # ---------- main loop ----------

    def run(self) -> dict:
        replay = ReplayProvider(self.base, start_offset=self.span)
        composer = self.factory(replay)
        outcomes: list[Outcome] = []
        no_trade_points = 0
        compose_points = 0

        full_cache: dict[str, object] = {}

        def full(symbol):
            if symbol not in full_cache:
                full_cache[symbol] = self.base.get_bars(
                    BarRequest(symbol, "1d", self.span + 460))
            return full_cache[symbol]

        offset = self.span
        while offset > self.horizon:
            compose_points += 1
            plan = composer.compose()
            as_of = None
            if plan.get("no_trade"):
                no_trade_points += 1
            else:
                frozen = self._frozen_guard(replay)
                vix_full, idx_full = full(VIX_SYMBOL), full(self.index_symbol)
                for s in plan["setups"]:
                    bars = full(s["symbol"])
                    asof_idx = len(bars) - 1 - offset
                    if asof_idx < 60:
                        continue
                    as_of = str(bars.index[asof_idx])
                    r, state, held, reason = self._simulate(
                        s, bars, asof_idx, vix_full, idx_full, frozen)
                    outcomes.append(Outcome(
                        symbol=s["symbol"], as_of=as_of,
                        direction=s["direction"], confidence=s["confidence"],
                        entry_trigger=s["entry_trigger"], stop=s["stop"],
                        target_1=s["target_1"], target_2=s["target_2"],
                        sector_etf=s["sector_etf"],
                        classification=s["classification"],
                        components={k: v["value"]
                                    for k, v in s["score_components"].items()},
                        final_state=state, realized_r=r,
                        bars_held=held, exit_reason=reason))
            replay.advance(self.step)
            offset -= self.step

        return report([o.to_dict() for o in outcomes],
                      compose_points=compose_points,
                      no_trade_points=no_trade_points,
                      n_trials=self.n_trials,
                      trial_sharpe_variance=self.trial_sharpe_variance)


# ---------- reporting ----------

CONF_BUCKETS = [(0.0, 6.5, "<6.5"), (6.5, 7.5, "6.5–7.5"), (7.5, 11.0, "≥7.5")]


def report(outcomes: list[dict], compose_points: int = 0,
           no_trade_points: int = 0, n_trials: int = 1,
           trial_sharpe_variance: float | None = None) -> dict:
    filled = [o for o in outcomes if o["realized_r"] is not None]
    wins = [o for o in filled if o["realized_r"] > 0]

    def stats(rows):
        if not rows:
            return {"n": 0}
        rs = [o["realized_r"] for o in rows]
        return {"n": len(rows),
                "win_rate": round(sum(r > 0 for r in rs) / len(rs), 3),
                "avg_r": round(sum(rs) / len(rs), 3),
                "best_r": round(max(rs), 2), "worst_r": round(min(rs), 2)}

    by_bucket = {}
    for lo, hi, label in CONF_BUCKETS:
        by_bucket[label] = stats([o for o in filled if lo <= o["confidence"] < hi])

    by_state: dict[str, int] = {}
    for o in outcomes:
        by_state[o["final_state"]] = by_state.get(o["final_state"], 0) + 1

    component_signal = {}
    losers = [o for o in filled if o["realized_r"] <= 0]
    if wins and losers:
        keys = wins[0]["components"].keys()
        for k in keys:
            w = sum(o["components"][k] for o in wins) / len(wins)
            l = sum(o["components"][k] for o in losers) / len(losers)
            component_signal[k] = {"winners_mean": round(w, 3),
                                   "losers_mean": round(l, 3),
                                   "edge": round(w - l, 3)}

    return {
        "compose_points": compose_points,
        "no_trade_points": no_trade_points,
        "setups": len(outcomes),
        "fill_rate": round(len(filled) / len(outcomes), 3) if outcomes else None,
        "overall": stats(filled),
        "by_confidence": by_bucket,
        "final_states": by_state,
        "component_signal": component_signal,
        "rigor": rigor_block([o["realized_r"] for o in filled],
                             n_trials=n_trials,
                             trial_sharpe_variance=trial_sharpe_variance),
        "outcomes": outcomes,
        "caveats": [
            "fills at trigger-bar close; no slippage or commissions",
            "market guard uses levels frozen at compose time",
            "daily bars: close decides when a bar spans stop and target",
        ],
    }


def render_text(rep: dict) -> str:
    lines = [
        f"compose points: {rep['compose_points']} "
        f"(no-trade on {rep['no_trade_points']})",
        f"setups: {rep['setups']} · fill rate: {rep['fill_rate']}",
        f"overall: {json.dumps(rep['overall'])}",
        "by confidence:",
    ]
    for label, s in rep["by_confidence"].items():
        lines.append(f"  {label:8} {json.dumps(s)}")
    lines.append(f"final states: {json.dumps(rep['final_states'])}")
    if rep["component_signal"]:
        lines.append("component edge (winners − losers):")
        for k, v in sorted(rep["component_signal"].items(),
                           key=lambda kv: -abs(kv[1]["edge"])):
            lines.append(f"  {k:24} {v['edge']:+.3f}")
    if rep.get("rigor"):
        lines.append(render_rigor(rep["rigor"]))
    lines.append("caveats: " + "; ".join(rep["caveats"]))
    return "\n".join(lines)
