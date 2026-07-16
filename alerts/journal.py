"""Outcome journal (Phase 9): the live counterpart of the backtest report.

Every armed trade already persists its full lifecycle to the alert store; the
journal turns that history into R-multiple outcomes under the same semantics
as backtest/harness.py — half off at T1, remainder at the final exit, open
positions marked to the latest quote. The output feeds the identical
calibration report, so live results and backtest results are directly
comparable: same buckets, same math, one definition of "win".
"""

from __future__ import annotations

from backtest.harness import report

OPEN_STATES = {"TRIGGERED", "ACTIVE", "TRIMMED_T1", "TRAILING"}
CLOSED_STATES = {"CLOSED", "STOPPED", "DETERIORATED"}


def trade_outcome(trade: dict, events: list[dict],
                  mark_price: float | None = None) -> dict:
    """One stored trade + its event trail -> a journal row.

    status: pending (never triggered, still armed) / no_fill (invalidated
    pre-entry or failed trigger) / open (marked to mark_price or the trade's
    water mark) / closed.
    """
    state = trade["state"]
    entry = trade.get("entry_price")
    direction = trade["direction"]
    sign = 1.0 if direction == "long" else -1.0
    meta = trade.get("setup_meta") or {}

    row = {
        "trade_id": trade["id"], "symbol": trade["symbol"],
        "direction": direction,
        "confidence": meta.get("confidence"),
        "sector_etf": meta.get("sector_etf"),
        "entry_trigger": trade["entry_trigger"], "stop": trade["stop"],
        "target_1": trade["target_1"], "target_2": trade["target_2"],
        "state": state,
        "opened_at": next((e["bar_time"] for e in events
                           if e["to_state"] == "TRIGGERED"), None),
        "closed_at": (events[-1]["bar_time"]
                      if state in CLOSED_STATES and events else None),
        "exit_reason": (events[-1]["reason"]
                        if events else "armed — awaiting trigger"),
    }

    if state == "WATCHING":
        return row | {"status": "pending", "realized_r": None,
                      "final_state": "PENDING"}
    if entry is None or state == "INVALIDATED":
        return row | {"status": "no_fill", "realized_r": None,
                      "final_state": "NO_FILL"}

    risk = abs(entry - trade["stop"])
    trimmed = any(e["to_state"] == "TRIMMED_T1" for e in events)

    if state in CLOSED_STATES:
        exit_price = events[-1]["price"]
        status, final = "closed", state
    else:  # open: mark to quote, else high/low-water as a conservative proxy
        exit_price = mark_price if mark_price is not None else trade.get("water_mark")
        status, final = "open", "OPEN"
        if exit_price is None:
            exit_price = entry

    if trimmed:
        pnl = 0.5 * sign * (trade["target_1"] - entry) + 0.5 * sign * (exit_price - entry)
    else:
        pnl = sign * (exit_price - entry)

    return row | {"status": status, "final_state": final,
                  "entry_price": round(entry, 4),
                  "exit_or_mark": round(float(exit_price), 4),
                  "realized_r": round(pnl / risk, 3) if risk > 0 else None}


def build_journal(store, mark_fn=None) -> dict:
    """All stored trades -> rows + the shared calibration report.

    mark_fn(symbol) -> float | None supplies marks for open positions
    (the gateway passes the quote provider; absent that, water marks)."""
    rows = []
    for trade in store.load_trades(active_only=False):
        events = store.events(trade["id"])
        mark = None
        if mark_fn is not None and trade["state"] in OPEN_STATES:
            try:
                mark = mark_fn(trade["symbol"])
            except Exception:
                mark = None
        rows.append(trade_outcome(trade, events, mark_price=mark))

    reportable = [r | {"as_of": r.get("opened_at") or "",
                       "classification": "live",
                       "components": {},
                       "bars_held": 0,
                       "confidence": r.get("confidence") or 0.0}
                  for r in rows if r["status"] != "pending"]
    summary = report(reportable)
    summary.pop("outcomes", None)   # rows carry the detail for the UI
    counts = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    return {"rows": rows, "summary": summary, "counts": counts}
