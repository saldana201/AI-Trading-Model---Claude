"""SQLite persistence for trades and alert events (design doc §3 notes:
TimescaleDB in production; SQLite is the honest prototype store)."""
from __future__ import annotations

import json
import sqlite3
import threading
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS trades (
  id TEXT PRIMARY KEY, symbol TEXT, state TEXT, payload TEXT, updated_at REAL);
CREATE TABLE IF NOT EXISTS events (
  seq INTEGER PRIMARY KEY AUTOINCREMENT, trade_id TEXT, payload TEXT, created_at REAL);
"""


class Store:
    def __init__(self, path: str = ":memory:"):
        # check_same_thread=False + a lock: the gateway serves sync routes on
        # a threadpool, so the connection is shared across threads by design.
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock:
            self.conn.executescript(SCHEMA)

    def save_trade(self, trade_dict: dict) -> None:
        with self._lock:
            self.conn.execute(
                "INSERT INTO trades(id, symbol, state, payload, updated_at) VALUES(?,?,?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET state=excluded.state, "
                "payload=excluded.payload, updated_at=excluded.updated_at",
                (trade_dict["id"], trade_dict["symbol"], trade_dict["state"],
                 json.dumps(trade_dict), time.time()))
            self.conn.commit()

    def load_trades(self, active_only: bool = True) -> list[dict]:
        terminal = ("CLOSED", "INVALIDATED", "STOPPED", "DETERIORATED")
        with self._lock:
            rows = self.conn.execute("SELECT payload, state FROM trades").fetchall()
        return [json.loads(p) for p, s in rows if not active_only or s not in terminal]

    def save_event(self, event: dict) -> None:
        with self._lock:
            self.conn.execute(
                "INSERT INTO events(trade_id, payload, created_at) VALUES(?,?,?)",
                (event["trade_id"], json.dumps(event), time.time()))
            self.conn.commit()

    def events(self, trade_id: str | None = None) -> list[dict]:
        q, args = "SELECT payload FROM events", ()
        if trade_id:
            q, args = q + " WHERE trade_id=?", (trade_id,)
        with self._lock:
            rows = self.conn.execute(q + " ORDER BY seq", args).fetchall()
        return [json.loads(r[0]) for r in rows]
