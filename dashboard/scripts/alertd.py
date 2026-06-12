"""Polling alert daemon (prototype).

Arms the morning game plan, then ticks on an interval against live data.
Production swaps this loop for the streaming ingest path (design doc §6).

Usage:
    python -m scripts.snapshot                      # generate game plan first
    python -m scripts.alertd --interval 60          # poll every 60s
    DISCORD_WEBHOOK_URL=... python -m scripts.alertd
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import time

from alerts.engine import AlertEngine
from alerts.sinks import ConsoleSink, JsonlSink, WebhookSink
from alerts.store import Store
from engines.levels_mcp.logic import LevelsEngine
from engines.vix_mcp.logic import VixEngine
from scripts.snapshot import build_provider


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", type=int, default=60)
    ap.add_argument("--store", default="alerts.db")
    ap.add_argument("--ticks", type=int, default=0, help="0 = run forever")
    args = ap.parse_args()

    provider, source = build_provider()
    sinks = [ConsoleSink(), JsonlSink("alerts.jsonl")]
    hook = os.environ.get("DISCORD_WEBHOOK_URL")
    if hook:
        sinks.append(WebhookSink(hook))

    engine = AlertEngine(provider, LevelsEngine(provider), VixEngine(provider),
                         store=Store(args.store), sinks=sinks)

    plan_path = pathlib.Path(__file__).resolve().parent.parent / "dashboard" / "data.json"
    if plan_path.exists():
        plan = json.loads(plan_path.read_text()).get("setups", {})
        armed = engine.arm_setups(plan)
        print(f"[alertd] armed {len(armed)} setups from game plan ({source} data)")
    else:
        print("[alertd] no game plan found — run scripts.snapshot first")

    i = 0
    while True:
        events = engine.tick()
        if events:
            print(f"[alertd] {len(events)} event(s)")
        i += 1
        if args.ticks and i >= args.ticks:
            break
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
