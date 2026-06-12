"""Chat service (design doc §8, PRD §10).

Two modes, same engines:

- LLM mode (ANTHROPIC_API_KEY + CONFLUENCE_MODEL set): the Anthropic SDK
  tool-use loop over the engine tool mesh. Claude writes language; every
  number comes from a tool result.
- Deterministic mode (no key): a keyword intent router that answers the
  PRD §10 canonical questions straight from engine output, clearly labeled.
  The product degrades to "still correct, less fluent" — never to silence.

SDK docs: https://docs.claude.com/en/api/overview
"""

from __future__ import annotations

import json
import os
import re

CHAT_SYSTEM = (
    "You are the chat surface of Confluence, a trading decision-support "
    "system. Answer concisely and actionably using ONLY numbers returned by "
    "your tools — never invent a price level. Always state what confirms and "
    "what invalidates a view. This is decision support for a discretionary "
    "trader, not financial advice; do not tell the user to buy or sell."
)


class EngineToolbox:
    """The tool mesh both chat modes share."""

    def __init__(self, *, regime, vix, levels, volume, momentum, rotation,
                 screener, options, composer):
        self.regime, self.vix, self.levels = regime, vix, levels
        self.volume, self.momentum, self.rotation = volume, momentum, rotation
        self.screener, self.options, self.composer = screener, options, composer
        self._cache: dict = {}

    def call(self, name: str, args: dict) -> dict:
        key = (name, json.dumps(args, sort_keys=True))
        if key not in self._cache:
            self._cache[key] = getattr(self, f"tool_{name}")(**args)
        return self._cache[key]

    # ---- tools (names map 1:1 to the MCP mesh) ----
    def tool_get_regime(self):
        return self.regime.get_regime()

    def tool_get_vix_levels(self):
        return self.vix.get_levels()

    def tool_get_index_levels(self, symbol: str = "QQQ"):
        return self.levels.get_levels(symbol.upper())

    def tool_classify_phase(self, symbol: str = "QQQ"):
        return self.volume.get_phase(symbol.upper())

    def tool_get_rsi_stack(self, symbol: str = "QQQ"):
        return self.momentum.get_rsi_stack(symbol.upper())

    def tool_get_rotation(self):
        return self.rotation.get_rotation_candidates()

    def tool_screen(self, symbols: list[str]):
        return self.screener.screen([s.upper() for s in symbols])

    def tool_get_dealer_zones(self, symbol: str = "QQQ"):
        return self.options.get_dealer_zones(symbol.upper())

    def tool_get_setups(self):
        return self.composer.compose()

    SPECS = [
        {"name": "get_regime", "description": "Current market regime, risk score, component contributions.", "input_schema": {"type": "object", "properties": {}}},
        {"name": "get_vix_levels", "description": "VIX spot, pivot, upside/downside targets.", "input_schema": {"type": "object", "properties": {}}},
        {"name": "get_index_levels", "description": "Key levels for an index or stock: triggers, weekly pivot/ceiling/floor, session levels, MA status, RVOL.", "input_schema": {"type": "object", "properties": {"symbol": {"type": "string"}}}},
        {"name": "classify_phase", "description": "Price-volume phase: accumulation/mark_up/distribution/etc.", "input_schema": {"type": "object", "properties": {"symbol": {"type": "string"}}}},
        {"name": "get_rsi_stack", "description": "RSI across timeframes with zones.", "input_schema": {"type": "object", "properties": {"symbol": {"type": "string"}}}},
        {"name": "get_rotation", "description": "Leading sectors, improving laggards, deteriorating leaders.", "input_schema": {"type": "object", "properties": {}}},
        {"name": "screen", "description": "CANSLIM-style screen incl. extension vs 21d MA.", "input_schema": {"type": "object", "properties": {"symbols": {"type": "array", "items": {"type": "string"}}}, "required": ["symbols"]}},
        {"name": "get_dealer_zones", "description": "Gamma regime, zero-gamma flip, call/put walls.", "input_schema": {"type": "object", "properties": {"symbol": {"type": "string"}}}},
        {"name": "get_setups", "description": "Today's composed trade setups with entries, stops, targets, confidence.", "input_schema": {"type": "object", "properties": {}}},
    ]


KNOWN_NON_TICKERS = {"WHAT", "WHICH", "TODAY", "THE", "FOR", "AND", "ARE",
                     "IS", "VIX", "RSI", "GOOD", "BEST", "I", "A", "MY", "OR",
                     "QQQ", "SPY", "NO", "CALLS", "PUTS", "ETF", "MA"}


def extract_symbols(text: str) -> list[str]:
    dollar = re.findall(r"\$([A-Za-z]{1,5})\b", text)
    caps = re.findall(r"\b([A-Z]{2,5})\b", text)
    out = []
    for s in [x.upper() for x in dollar] + caps:
        if s not in KNOWN_NON_TICKERS and s not in out:
            out.append(s)
    return out


class ChatService:
    def __init__(self, toolbox: EngineToolbox):
        self.toolbox = toolbox
        self._client = None
        self.model = os.environ.get("CONFLUENCE_MODEL")
        if os.environ.get("ANTHROPIC_API_KEY") and self.model:
            import anthropic
            self._client = anthropic.Anthropic()

    @property
    def mode(self) -> str:
        return "llm" if self._client else "deterministic"

    def ask(self, message: str, history: list[dict] | None = None) -> dict:
        if self._client:
            return self._ask_llm(message, history or [])
        return self._ask_deterministic(message)

    # ---------- LLM mode ----------

    def _ask_llm(self, message: str, history: list[dict]) -> dict:
        messages = history + [{"role": "user", "content": message}]
        tool_calls = []
        for _ in range(8):  # tool-use loop budget
            resp = self._client.messages.create(
                model=self.model, max_tokens=1200, system=CHAT_SYSTEM,
                tools=EngineToolbox.SPECS, messages=messages)
            if resp.stop_reason != "tool_use":
                text = "".join(b.text for b in resp.content if b.type == "text")
                return {"reply": text.strip(), "mode": "llm",
                        "tool_calls": tool_calls}
            messages.append({"role": "assistant", "content": resp.content})
            results = []
            for block in resp.content:
                if block.type != "tool_use":
                    continue
                tool_calls.append({"name": block.name, "input": block.input})
                try:
                    out = self.toolbox.call(block.name, dict(block.input))
                    results.append({"type": "tool_result",
                                    "tool_use_id": block.id,
                                    "content": json.dumps(out, default=str)})
                except Exception as exc:
                    results.append({"type": "tool_result",
                                    "tool_use_id": block.id,
                                    "content": f"tool error: {exc}",
                                    "is_error": True})
            messages.append({"role": "user", "content": results})
        return {"reply": "Tool-use budget exhausted — try a narrower question.",
                "mode": "llm", "tool_calls": tool_calls}

    # ---------- deterministic mode ----------

    def _ask_deterministic(self, message: str) -> dict:
        q = message.lower()
        syms = extract_symbols(message)
        tb = self.toolbox

        def reply(text, tools):
            return {"reply": text, "mode": "deterministic", "tool_calls": tools}

        if "regime" in q or ("market" in q and ("tone" in q or "today" in q)):
            r = tb.call("get_regime", {})
            top = sorted(r["components"], key=lambda c: -abs(c["contribution"]))[:3]
            drivers = ", ".join(f"{c['name'].replace('_', ' ')} {c['contribution']:+.1f}"
                                for c in top)
            mods = f" Modifiers: {', '.join(r['modifiers'])}." if r["modifiers"] else ""
            return reply(
                f"Regime: {r['regime'].replace('_', '-')} (risk score "
                f"{r['risk_score']:+.1f} of ±10).{mods} Main drivers: {drivers}.",
                ["get_regime"])

        if "calls" in q and "puts" in q or "no trade" in q:
            r = tb.call("get_regime", {})
            v = tb.call("get_vix_levels", {})
            bias = {"risk_on": "the day favors call setups",
                    "risk_off": "the day favors put setups",
                    "chop": "no-trade conditions — standing aside is the setup"}[r["regime"]]
            confirm = ("VIX confirms (below pivot)" if v["spot_vs_pivot"] == "below"
                       else "VIX does NOT confirm (at/above pivot) — size down or wait")
            return reply(f"{bias} (risk score {r['risk_score']:+.1f}); {confirm}: "
                         f"VIX {v['spot']} vs pivot {v['pivot']}.",
                         ["get_regime", "get_vix_levels"])

        if "vix" in q:
            v = tb.call("get_vix_levels", {})
            return reply(
                f"VIX {v['spot']} ({v['spot_vs_pivot']} pivot {v['pivot']}). "
                f"Upside targets {v['upside_target_1']} / {v['upside_target_2']}; "
                f"downside {v['downside_target_1']} / {v['downside_target_2']}.",
                ["get_vix_levels"])

        if "invalidate" in q or "stop" in q:
            s = tb.call("get_setups", {})
            target = next((x for x in s.get("setups", [])
                           if x["symbol"] in syms), None) if syms else None
            if target:
                return reply(
                    f"{target['symbol']} {target['direction']}: stop "
                    f"{target['stop']}; invalidated by {target['invalidation']}.",
                    ["get_setups"])
            return reply("Setups are invalidated by their stop level plus the "
                         "regime guard: a long dies on a daily close below the "
                         "21d MA or VIX reclaiming its pivot. Name a ticker for "
                         "its exact levels.", ["get_setups"])

        if "level" in q:
            parts, tools = [], []
            for sym in (syms or ["QQQ", "SPY"]):
                L = tb.call("get_index_levels", {"symbol": sym})
                parts.append(
                    f"{sym} {L['spot']}: bull trigger {L['bullish_trigger']}, "
                    f"bear trigger {L['bearish_trigger']}, weekly pivot "
                    f"{L['weekly']['weekly_pivot']} (ceiling "
                    f"{L['weekly']['weekly_ceiling']} / floor "
                    f"{L['weekly']['weekly_floor']}), HOD/LOD "
                    f"{L['session']['high_of_day']}/{L['session']['low_of_day']}")
                tools.append("get_index_levels")
            return reply(" · ".join(parts), tools)

        if "sector" in q or "leading" in q or "laggard" in q or "rotat" in q:
            r = tb.call("get_rotation", {})
            lead = ", ".join(e["symbol"] for e in r["leading"][:6]) or "none"
            imp = ", ".join(e["symbol"] for e in r["improving"][:6]) or "none"
            det = ", ".join(e["symbol"] for e in r["deteriorating"][:4]) or "none"
            return reply(f"Leading: {lead}. Improving laggards: {imp}. "
                         f"Deteriorating: {det}.", ["get_rotation"])

        if "extended" in q and syms:
            res = tb.call("screen", {"symbols": syms[:3]})
            parts = []
            for r in res["results"]:
                ext = r["extension_vs_21d_pct"]
                verdict = ("extended — avoid chasing" if ext is not None and ext > 9
                           else "not overextended")
                parts.append(f"{r['symbol']}: {ext}% above the 21d MA, "
                             f"{r['pct_off_52w_high']}% off highs — {verdict} "
                             f"({r['classification'].replace('_', ' ')})")
            return reply(" · ".join(parts) or "No screen data for those symbols.",
                         ["screen"])

        if ("accumulation" in q or "distribution" in q or "phase" in q
                or "mark-up" in q or "mark up" in q):
            sym = syms[0] if syms else "QQQ"
            ph = tb.call("classify_phase", {"symbol": sym})
            ev = ph["evidence"]
            return reply(
                f"{sym} reads as {ph['phase'].replace('_', ' ')} — trend "
                f"{ev['trend_slope_pct_per_bar']}%/bar, up/down volume "
                f"{ev['updown_volume_ratio_20d']}, range position "
                f"{ev['range_position_60d']}.", ["classify_phase"])

        if "gamma" in q or "dealer" in q or "wall" in q or "options" in q:
            sym = syms[0] if syms else "QQQ"
            z = tb.call("get_dealer_zones", {"symbol": sym})
            return reply(
                f"{sym}: {z['gamma_regime']} gamma (flip {z['zero_gamma_flip']}, "
                f"call wall {z['call_wall']}, put wall {z['put_wall']}). "
                f"{z['reading']}.", ["get_dealer_zones"])

        if "setup" in q or "stocks" in q or "swing" in q or "watch" in q:
            s = tb.call("get_setups", {})
            if s.get("no_trade"):
                return reply(s["reason"], ["get_setups"])
            lines = [f"{x['symbol']} {x['direction']} {x['confidence']}/10: "
                     f"entry {x['entry_trigger']}, stop {x['stop']}, "
                     f"T1 {x['target_1']}, T2 {x['target_2']} "
                     f"({x['instrument'].replace('_', ' ')})"
                     for x in s["setups"][:5]]
            return reply(" · ".join(lines) or "No setups clear the gates today.",
                         ["get_setups"])

        if "rsi" in q or "momentum" in q:
            sym = syms[0] if syms else "QQQ"
            st = tb.call("get_rsi_stack", {"symbol": sym})["stack"]
            return reply(sym + " RSI: " + ", ".join(
                f"{s['timeframe']} {s['rsi']} ({s['zone']})" for s in st),
                ["get_rsi_stack"])

        return reply(
            "I can answer: market regime, key QQQ/SPY levels, calls vs puts vs "
            "no-trade, VIX framework, sector rotation, today's setups, whether "
            "a ticker is extended, what invalidates a trade, volume phase, RSI, "
            "and gamma/dealer positioning. (Deterministic mode — set "
            "ANTHROPIC_API_KEY and CONFLUENCE_MODEL for the full assistant.)",
            [])
