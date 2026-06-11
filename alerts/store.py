"""SQLite persistence for trades and alert events (design doc §3 notes:
TimescaleDB in production; SQLite is the honest prototype store)."""
from __future__ import annotations

import json
import sqlite3
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS trades (
  id TEXT PRIMARY KEY, symbol TEXT, state TEXT, payload TEXT, updated_at REAL);
CREATE TABLE IF NOT EXISTS events (
  seq INTEGER PRIMARY KEY AUTOINCREMENT, trade_id TEXT, payload TEXT, created_at REAL);
"""


class Store:
    def __init__(self, path: str = ":memory:"):
        self.conn = sqlite3.connect(path)
        self.conn.executescript(SCHEMA)

    def save_trade(self, trade_dict: dict) -> None:
        self.conn.execute(
            "INSERT INTO trades(id, symbol, state, payload, updated_at) VALUES(?,?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET state=excluded.state, "
            "payload=excluded.payload, updated_at=excluded.updated_at",
            (trade_dict["id"], trade_dict["symbol"], trade_dict["state"],
             json.dumps(trade_dict), time.time()))
        self.conn.commit()

    def load_trades(self, active_only: bool = True) -> list[dict]:
        terminal = ("CLOSED", "INVALIDATED", "STOPPED", "DETERIORATED")
        rows = self.conn.execute("SELECT payload, state FROM trades").fetchall()
        out = [json.loads(p) for p, s in rows if not active_only or s not in terminal]
        return out

    def save_event(self, event: dict) -> None:
        self.conn.execute("INSERT INTO events(trade_id, payload, created_at) VALUES(?,?,?)",
                          (event["trade_id"], json.dumps(event), time.time()))
        self.conn.commit()

    def events(self, trade_id: str | None = None) -> list[dict]:
        q, args = "SELECT payload FROM events", ()
        if trade_id:
            q, args = q + " WHERE trade_id=?", (trade_id,)
        return [json.loads(r[0]) for r in self.conn.execute(q + " ORDER BY seq", args)]
