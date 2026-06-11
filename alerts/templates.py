"""Alert message rendering (PRD §12): the alert explains the trigger,
never just says buy/sell. The optional LLM rewrite happens AFTER detection."""
from __future__ import annotations

HEADLINES = {
    "TRIGGERED": "trigger fired",
    "ACTIVE": "entry confirmed",
    "TRIMMED_T1": "target 1 — trim",
    "TRAILING": "trailing engaged",
    "CLOSED": "trade closed",
    "STOPPED": "stopped out",
    "DETERIORATED": "setup deteriorated — exit recommended",
    "INVALIDATED": "setup invalidated",
    "WATCHING": "re-armed",
}


def render_event(event: dict, trade: dict | None = None) -> str:
    head = HEADLINES.get(event["to_state"], event["to_state"])
    lines = [
        f"[{event['symbol']} {event['direction'].upper()}] {head} @ {event['price']}",
        f"  {event['reason']} ({event['bar_time']})",
    ]
    if trade and event["to_state"] in ("TRIGGERED", "ACTIVE"):
        lines.append(
            f"  plan: entry {trade['entry_trigger']} · stop {trade['stop']} · "
            f"T1 {trade['target_1']} · T2 {trade['target_2']}")
    if event.get("details"):
        kv = " · ".join(f"{k}={v}" for k, v in event["details"].items()
                        if not isinstance(v, (dict, list)))
        if kv:
            lines.append(f"  {kv}")
    meta = (trade or {}).get("setup_meta") or {}
    if meta.get("thesis") and event["to_state"] == "TRIGGERED":
        lines.append(f"  why: {meta['thesis']}")
    return "\n".join(lines)
