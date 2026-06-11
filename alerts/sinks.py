"""Alert delivery sinks: console, JSONL file, and a generic webhook POST
(Discord/Slack-compatible payload), stdlib-only."""
from __future__ import annotations

import json
import urllib.request

from .templates import render_event


class ConsoleSink:
    def emit(self, event: dict, trade: dict | None = None) -> None:
        print(render_event(event, trade))


class JsonlSink:
    def __init__(self, path: str):
        self.path = path

    def emit(self, event: dict, trade: dict | None = None) -> None:
        with open(self.path, "a") as f:
            f.write(json.dumps({"event": event,
                                "message": render_event(event, trade)}) + "\n")


class WebhookSink:
    """POSTs {'content': message, 'event': event} — Discord-compatible;
    adapt the body shape per service."""

    def __init__(self, url: str, timeout: float = 5.0):
        self.url = url
        self.timeout = timeout

    def emit(self, event: dict, trade: dict | None = None) -> None:
        body = json.dumps({"content": render_event(event, trade),
                           "event": event}).encode()
        req = urllib.request.Request(self.url, data=body,
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=self.timeout)  # caller handles errors
