"""Run fingerprint — makes two runs provably comparable (or provably not).

Three scripts produced three different answers on "identical" settings:

    bias_check    490 trades  totalR +140.6  avg +0.287
    benchmark     486 trades  totalR +131.6  avg +0.271
    walk_forward  506 trades  totalR  +35.5  avg +0.070

A 4x spread in edge means at least one input differed. There are three
candidates, and this module pins all of them:

  1. CONFIG      — a persisted change (e.g. preentry_invalidation, min_rr_t2)
                   silently altering gates between runs. Note the walk_forward
                   run had MORE trades and FAR less edge, which is exactly what
                   a looser gate produces: marginal setups let in.
  2. WATCHLIST   — expanded/edited between runs.
  3. DATA WINDOW — yfinance returns the last N bars relative to NOW, so runs
                   hours apart cover different windows. This one is invisible
                   without recording the actual first/last bar dates.

Print this at the top of every diagnostic and any two runs can be compared with
confidence — or dismissed as non-comparable in one line.
"""

from __future__ import annotations

import hashlib
import json
import os


def _h(obj) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:10]


def _gates_summary() -> dict:
    """The specific knobs we have been changing, spelled out — a hash tells you
    THAT something differs; these tell you WHAT."""
    try:
        from config import get_config
        c = get_config()
        g, r, s = c.get("gates", {}), c.get("risk", {}), c.get("setup", {})
        return {
            "chop_mode": g.get("chop_mode"),
            "preentry": g.get("preentry_invalidation"),
            "force_direction": g.get("force_direction") or None,
            "min_score": r.get("min_score"),
            "min_rr_t1": r.get("min_rr_t1"),
            "min_rr_t2": r.get("min_rr_t2"),
            "max_stop_atr": s.get("max_stop_atr"),
            "t2_atr": s.get("t2_atr"),
        }
    except Exception as exc:
        return {"error": str(exc)}


def fingerprint(provider=None, symbol: str = "QQQ", span: int | None = None) -> dict:
    """Fingerprint the effective config, watchlist, and (if a provider is given)
    the actual data window in use."""
    fp: dict = {}

    try:
        from config import get_config
        cfg = get_config()
        fp["config_hash"] = _h(cfg)
    except Exception as exc:
        fp["config_hash"] = f"err:{exc}"
    fp["gates"] = _gates_summary()
    fp["config_file_present"] = os.path.exists("confluence.json")

    try:
        with open("watchlist.json") as fh:
            wl = json.load(fh)
        sectors = [k for k in wl if not k.startswith("_")]
        uniq = {t for k in sectors for t in wl[k]}
        fp["watchlist"] = {"hash": _h(wl), "sectors": len(sectors),
                           "unique_tickers": len(uniq)}
    except Exception as exc:
        fp["watchlist"] = {"error": str(exc)}

    fp["data_source"] = os.environ.get("CONFLUENCE_DATA", "yfinance")

    if provider is not None and span:
        try:
            from engines.shared.providers import BarRequest
            b = provider.get_bars(BarRequest(symbol, "1d", span + 5)).tail(span)
            fp["data_window"] = {"symbol": symbol, "bars": int(len(b)),
                                 "first": str(b.index[0])[:10],
                                 "last": str(b.index[-1])[:10]}
        except Exception as exc:
            fp["data_window"] = {"error": str(exc)}
    return fp


def render(fp: dict) -> str:
    g = fp.get("gates", {})
    knobs = "  ".join(f"{k}={v}" for k, v in g.items() if v is not None)
    lines = [
        f"[fp] config={fp.get('config_hash')} "
        f"file={'yes' if fp.get('config_file_present') else 'no (defaults)'} "
        f"source={fp.get('data_source')}",
        f"[fp] {knobs}",
    ]
    w = fp.get("watchlist", {})
    if "hash" in w:
        lines.append(f"[fp] watchlist={w['hash']} "
                     f"{w['unique_tickers']} tickers / {w['sectors']} sectors")
    d = fp.get("data_window")
    if d and "bars" in d:
        lines.append(f"[fp] window={d['first']}..{d['last']} ({d['bars']} bars "
                     f"of {d['symbol']})")
    return "\n".join(lines)


def emit(provider=None, symbol: str = "QQQ", span: int | None = None) -> dict:
    fp = fingerprint(provider, symbol, span)
    print(render(fp))
    return fp
