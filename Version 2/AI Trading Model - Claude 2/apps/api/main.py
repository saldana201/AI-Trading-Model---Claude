"""Confluence API gateway (design doc §8) — headless-CRUD revision.

The HTTP surface:

  GET  /api/health                    liveness + data source + chat/auth mode
  GET  /api/snapshot                  full dashboard payload (TTL; ?refresh=1)
  POST /api/chat                      {"message", "history"} -> {"reply", ...}   [auth]
  GET  /api/quotes                    ticker strip quotes
  POST /api/alerts/arm|tick           live alert control                          [auth]
  GET  /api/alerts/state              armed trades + recent events
  GET  /api/stream                    SSE feed
  *    /api/resources/{trades,events,watchlist}   resource-style CRUD            [auth]

Changes vs. 0.7.0:
- State lives on app.state.confluence, built in the lifespan handler —
  explicit per-process initialization instead of a lazily-mutated module
  global. (Caches/broadcaster are still in-process: with --workers N each
  worker has its own. Cross-worker sharing needs Redis; run one worker.)
- CORS origins come from CONFLUENCE_CORS_ORIGINS (comma-separated), and
  X-Total-Count is exposed so browser clients can paginate.
- API key auth (apps.api.auth) guards mutations and the resource routers.
  Unset CONFLUENCE_API_KEY -> auth disabled with a logged warning (dev mode).

Run:  uvicorn apps.api.main:app --port 8000
      CONFLUENCE_DATA=synthetic CONFLUENCE_API_KEY=dev-secret \
          uvicorn apps.api.main:app --port 8000
"""

from __future__ import annotations

import asyncio
import os
import time
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
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
from orchestrator.composer import SetupComposer
from orchestrator.chat import ChatService, EngineToolbox
from orchestrator.llm import make_thesis_writer
from engines.shared.providers import CachedProvider
from scripts.snapshot import build_provider, build_snapshot
from apps.api.auth import configured_key, require_api_key
from apps.api.live import (Broadcaster, LiveAlerts, build_quotes, pump,
                           DEFAULT_TICKER_SYMBOLS)
from apps.api.resources import ALL_ROUTERS

SNAPSHOT_TTL_S = int(os.environ.get("CONFLUENCE_SNAPSHOT_TTL", "300"))
BARS_TTL_S = float(os.environ.get("CONFLUENCE_BARS_TTL", "300"))
QUOTE_TTL_S = float(os.environ.get("CONFLUENCE_QUOTE_TTL", "15"))
QUOTE_INTERVAL_S = float(os.environ.get("CONFLUENCE_QUOTE_INTERVAL", "15"))
ALERT_INTERVAL_S = float(os.environ.get("CONFLUENCE_ALERT_INTERVAL", "60"))
CORS_ORIGINS = [o.strip() for o in os.environ.get(
    "CONFLUENCE_CORS_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000").split(",") if o.strip()]


def build_state() -> dict:
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
                                          "CONFLUENCE_ALERT_DB", ":memory:")),
            "ticker_symbols": DEFAULT_TICKER_SYMBOLS,
            "snapshot": None, "snapshot_at": 0.0}


def _ensure_state(app: FastAPI) -> dict:
    if not hasattr(app.state, "confluence"):
        app.state.confluence = build_state()
    return app.state.confluence


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = _ensure_state(app)
    stop = asyncio.Event()
    task = asyncio.create_task(
        pump(s, QUOTE_INTERVAL_S, ALERT_INTERVAL_S, stop))
    yield
    stop.set()
    task.cancel()


app = FastAPI(title="Confluence API", version="0.8.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["*"], allow_headers=["*"],
    expose_headers=["X-Total-Count"],
)
for r in ALL_ROUTERS:
    app.include_router(r)


def state(request: Request) -> dict:
    """Dependency: the per-process state (built at startup, or lazily when
    the lifespan didn't run, e.g. TestClient without a context manager)."""
    return _ensure_state(request.app)


def get_state() -> dict:
    """Back-compat accessor for tests and scripts that reach in directly."""
    return _ensure_state(app)


class ChatRequest(BaseModel):
    message: str
    history: list[dict] = []


@app.get("/api/health")
def health(s: dict = Depends(state)):
    return {"ok": True, "data_source": s["source"], "chat_mode": s["chat"].mode,
            "auth": "api_key" if configured_key() else "disabled",
            "snapshot_age_s": (round(time.time() - s["snapshot_at"])
                               if s["snapshot"] else None)}


@app.get("/api/snapshot")
def snapshot(refresh: int = 0, s: dict = Depends(state)):
    stale = time.time() - s["snapshot_at"] > SNAPSHOT_TTL_S
    if s["snapshot"] is None or stale or refresh:
        s["snapshot"] = build_snapshot()
        s["snapshot_at"] = time.time()
    return s["snapshot"]


@app.post("/api/chat", dependencies=[Depends(require_api_key)])
def chat(req: ChatRequest, s: dict = Depends(state)):
    return s["chat"].ask(req.message, req.history)


# ---------- live feed (Phase 7) ----------

def _ensure_snapshot(s: dict) -> dict:
    if s["snapshot"] is None:
        s["snapshot"] = build_snapshot()
        s["snapshot_at"] = time.time()
    return s["snapshot"]


@app.get("/api/quotes")
def quotes(symbols: str = "", s: dict = Depends(state)):
    syms = ([x.strip().upper() for x in symbols.split(",") if x.strip()]
            or s["ticker_symbols"])
    return build_quotes(s["quote_provider"], syms)


@app.post("/api/alerts/arm", dependencies=[Depends(require_api_key)])
def arm_alerts(s: dict = Depends(state)):
    snap = _ensure_snapshot(s)
    result = s["live_alerts"].arm(snap["setups"])
    # ticker follows the armed names too
    armed_syms = [t["symbol"] for t in s["live_alerts"].state()["trades"]]
    s["ticker_symbols"] = list(dict.fromkeys(
        DEFAULT_TICKER_SYMBOLS + armed_syms))
    return result


@app.post("/api/alerts/tick", dependencies=[Depends(require_api_key)])
def tick_alerts(s: dict = Depends(state)):
    return {"events": s["live_alerts"].tick()}


@app.get("/api/alerts/state")
def alerts_state(s: dict = Depends(state)):
    return s["live_alerts"].state()


@app.get("/api/stream")
async def stream():
    # resolves state internally (not via Depends): test_phase7 drives this
    # generator directly, outside FastAPI's dependency injection
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
