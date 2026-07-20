"""Confluence API gateway (design doc §8).

The HTTP surface the Next.js app consumes:

  GET  /api/health           liveness + data source + chat mode
  GET  /api/snapshot         full dashboard payload (TTL-cached; ?refresh=1)
  POST /api/chat             {"message": str, "history": [...]} -> {"reply", "mode", "tool_calls"}

Run:  uvicorn apps.api.main:app --port 8000
      CONFLUENCE_DATA=synthetic uvicorn apps.api.main:app --port 8000
"""

from __future__ import annotations

import asyncio
import os
import time
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from engines.vix_mcp.logic import VixEngine
from engines.levels_mcp.logic import LevelsEngine
from engines.volume_mcp.logic import VolumeEngine
from engines.momentum_mcp.logic import MomentumEngine
from engines.regime_mcp.logic import RegimeEngine
from engines.rotation_mcp.logic import RotationEngine
from engines.screener_mcp.logic import ScreenerEngine
from engines.fundamentals_mcp.logic import (
    FundamentalsEngine, SyntheticFundamentals, YFinanceFundamentals)
from engines.options_mcp.logic import OptionsEngine
from engines.options_mcp.providers import SyntheticOptions, YFinanceOptions
from orchestrator.composer import SetupComposer, load_pinned, load_watchlist
from orchestrator.chat import ChatService, EngineToolbox
from orchestrator.llm import make_thesis_writer
from engines.shared.providers import CachedProvider
from scripts.snapshot import build_provider, build_snapshot
from apps.api.live import Broadcaster, LiveAlerts, build_quotes, pump, DEFAULT_TICKER_SYMBOLS
from apps.api.auth import require_api_key

SNAPSHOT_TTL_S = int(os.environ.get("CONFLUENCE_SNAPSHOT_TTL", "300"))
BARS_TTL_S = float(os.environ.get("CONFLUENCE_BARS_TTL", "300"))
QUOTE_TTL_S = float(os.environ.get("CONFLUENCE_QUOTE_TTL", "15"))
QUOTE_INTERVAL_S = float(os.environ.get("CONFLUENCE_QUOTE_INTERVAL", "15"))
ALERT_INTERVAL_S = float(os.environ.get("CONFLUENCE_ALERT_INTERVAL", "60"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    import logging
    logging.getLogger("confluence.watchlist").setLevel(logging.INFO)
    s = get_state()
    _pins = load_pinned()
    print(f"[confluence] data={s['source']} · pinned={_pins or 'none'} · "
          f"autoarm={os.environ.get('CONFLUENCE_AUTOARM_ET') or 'off'}")
    stop = asyncio.Event()
    task = asyncio.create_task(
        pump(s, QUOTE_INTERVAL_S, ALERT_INTERVAL_S, stop))
    yield
    stop.set()
    task.cancel()


app = FastAPI(title="Confluence API", version="0.8.0", lifespan=lifespan)
# Phase 9: CORS origins are config, not hardcoded; X-Total-Count must be
# exposed or admin frameworks can't paginate.
from apps.api.resources import cors_origins as _cors_origins  # noqa: E402
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
    expose_headers=["X-Total-Count"],
)

_state: dict = {}


def _build_state() -> dict:
    raw_provider, source = build_provider()
    provider = CachedProvider(raw_provider, ttl_s=BARS_TTL_S)
    # shorter-lived cache for the ticker path so quotes stay fresher
    quote_provider = CachedProvider(raw_provider, ttl_s=QUOTE_TTL_S)
    levels = LevelsEngine(provider)
    options = OptionsEngine(
        provider,
        SyntheticOptions(iv_rank=0.62) if source == "synthetic" else YFinanceOptions())
    rotation = RotationEngine(provider)
    toolbox = EngineToolbox(
        regime=RegimeEngine(provider, rotation_engine=rotation),
        vix=VixEngine(provider),
        levels=levels,
        volume=VolumeEngine(provider),
        momentum=MomentumEngine(provider),
        rotation=rotation,
        screener=ScreenerEngine(provider),
        options=options,
        composer=SetupComposer(
            provider=provider,
            regime_engine=RegimeEngine(provider, rotation_engine=rotation),
            rotation_engine=rotation,
            levels_engine=levels,
            volume_engine=VolumeEngine(provider),
            momentum_engine=MomentumEngine(provider),
            fundamentals_engine=FundamentalsEngine(
                SyntheticFundamentals() if source == "synthetic"
                else YFinanceFundamentals()),
            screener_engine=ScreenerEngine(provider),
            thesis_writer=make_thesis_writer(),
            options_engine=options),
    )
    broadcaster = Broadcaster()
    vix = VixEngine(provider)
    return {"source": source, "toolbox": toolbox,
            "chat": ChatService(toolbox),
            "provider": provider, "quote_provider": quote_provider,
            "broadcaster": broadcaster,
            "live_alerts": LiveAlerts(quote_provider, levels, vix, broadcaster,
                                      db_path=os.environ.get(
                                          "CONFLUENCE_ALERT_DB", "alerts.db"),
                                      data_source=source),
            "ticker_symbols": DEFAULT_TICKER_SYMBOLS,
            "snapshot": None, "snapshot_at": 0.0}


def get_state() -> dict:
    if not _state:
        _state.update(_build_state())
    return _state


class ChatRequest(BaseModel):
    message: str
    history: list[dict] = []


@app.get("/api/health")
def health():
    s = get_state()
    wl = load_watchlist()
    from apps.api.auth import auth_mode
    return {"ok": True, "data_source": s["source"], "chat_mode": s["chat"].mode,
            "auth": auth_mode(),
            "pinned": load_pinned(),
            "watchlist_sectors": sorted(wl.keys()),
            "autoarm_et": os.environ.get("CONFLUENCE_AUTOARM_ET"),
            "snapshot_age_s": (round(time.time() - s["snapshot_at"])
                               if s["snapshot"] else None)}


@app.get("/api/snapshot")
def snapshot(refresh: int = 0):
    s = get_state()
    stale = time.time() - s["snapshot_at"] > SNAPSHOT_TTL_S
    if s["snapshot"] is None or stale or refresh:
        s["snapshot"] = build_snapshot()
        s["snapshot_at"] = time.time()
    return s["snapshot"]


@app.post("/api/chat", dependencies=[Depends(require_api_key)])
def chat(req: ChatRequest):
    svc = get_state()["chat"]
    try:
        return svc.ask(req.message, req.history)
    except Exception as exc:
        return {"reply": f"I hit an error answering that ({type(exc).__name__}: "
                         f"{exc}). If you named a ticker, double-check the "
                         "symbol and try again.",
                "mode": svc.mode, "tool_calls": [], "error": True}


# ---------- live feed (Phase 7) ----------

def _ensure_snapshot(s: dict) -> dict:
    if s["snapshot"] is None:
        s["snapshot"] = build_snapshot()
        s["snapshot_at"] = time.time()
    return s["snapshot"]


@app.get("/api/quotes")
def quotes(symbols: str = ""):
    s = get_state()
    syms = ([x.strip().upper() for x in symbols.split(",") if x.strip()]
            or s["ticker_symbols"])
    return build_quotes(s["quote_provider"], syms)


@app.post("/api/alerts/arm", dependencies=[Depends(require_api_key)])
def arm_alerts():
    s = get_state()
    snap = _ensure_snapshot(s)
    result = s["live_alerts"].arm(snap["setups"])
    # ticker follows the armed names too
    armed_syms = [t["symbol"] for t in s["live_alerts"].state()["trades"]]
    s["ticker_symbols"] = list(dict.fromkeys(
        DEFAULT_TICKER_SYMBOLS + armed_syms))
    return result


@app.post("/api/alerts/tick", dependencies=[Depends(require_api_key)])
def tick_alerts():
    return {"events": get_state()["live_alerts"].tick()}


@app.get("/api/alerts/state")
def alerts_state():
    return get_state()["live_alerts"].state()


@app.get("/api/journal")
def journal():
    from alerts.journal import build_journal
    s = get_state()
    qp = s["quote_provider"]

    def mark(symbol: str):
        from engines.shared.providers import BarRequest
        bars = qp.get_bars(BarRequest(symbol, "1d", 10))
        return float(bars["close"].iloc[-1])

    return build_journal(s["live_alerts"].engine.store, mark_fn=mark)


@app.get("/api/stream")
async def stream():
    s = get_state()
    q = s["broadcaster"].subscribe()

    async def gen():
        yield 'event: hello' + chr(10) + 'data: {"source": "' + s['source'] + '"}' + chr(10)*2
        try:
            while True:
                try:
                    yield await asyncio.wait_for(q.get(), timeout=float(os.environ.get('CONFLUENCE_SSE_KEEPALIVE', '30')))
                except asyncio.TimeoutError:
                    yield ': keepalive' + chr(10)*2
        finally:
            s["broadcaster"].unsubscribe(q)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


# ---------- Phase 12: config + trade assistant ----------

from apps.api.phase12 import install as install_phase12  # noqa: E402
install_phase12(app, get_state, _ensure_snapshot)


# ---------- Phase 9: headless resource REST (Refine-compatible) ----------

from apps.api.resources import install as install_resources  # noqa: E402
install_resources(app, get_state)
