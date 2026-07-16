"""Morning brief (Phase 10): the daily game plan as markdown.

Rendered from the same snapshot the dashboard consumes, so the brief and the
board can never disagree. Written to briefs/YYYY-MM-DD.md by the auto-arm
scheduler and optionally pushed to a Discord webhook. Defensive .get()
access throughout — a partial snapshot produces a partial brief, never a
crash at 8:30 ET.
"""

from __future__ import annotations


def _f(v, d=2):
    try:
        return f"{float(v):.{d}f}"
    except (TypeError, ValueError):
        return "—"


def render_brief(snapshot: dict) -> str:
    lines: list[str] = []
    date = (snapshot.get("generated_at") or "")[:10]
    source = snapshot.get("source", "?")
    lines.append(f"# Confluence morning brief — {date}")
    lines.append(f"_data source: {source}_\n")

    # regime
    regime = snapshot.get("regime") or {}
    if regime:
        mods = ", ".join(regime.get("modifiers") or []) or "none"
        lines.append(f"## Regime: {regime.get('regime', '?').replace('_', '-')} "
                     f"({regime.get('risk_score', 0):+.1f} of ±10)")
        lines.append(f"Vol modifiers: {mods}")
        comps = sorted(regime.get("components", []),
                       key=lambda c: -abs(c.get("contribution", 0)))[:3]
        if comps:
            lines.append("Top drivers: " + " · ".join(
                f"{c['name'].replace('_', ' ')} {c['contribution']:+.1f}"
                for c in comps))
        lines.append("")

    # vix
    vix = (snapshot.get("vix") or {})
    vl, va = vix.get("levels") or {}, vix.get("alignment") or {}
    if vl:
        lines.append(f"## VIX {_f(vl.get('spot'))} — "
                     f"{(va.get('state') or '?').replace('_', ' ')}")
        lines.append(f"Pivot {_f(vl.get('pivot'))} · upside targets "
                     f"{_f(vl.get('upside_target_1'))} / {_f(vl.get('upside_target_2'))} "
                     f"· downside {_f(vl.get('downside_target_1'))} / "
                     f"{_f(vl.get('downside_target_2'))}\n")

    # index levels
    indices = snapshot.get("indices") or {}
    for sym in ("QQQ", "SPY"):
        L = (indices.get(sym) or {}).get("levels") or {}
        if not L:
            continue
        wk = L.get("weekly") or {}
        lines.append(f"**{sym}** {_f(L.get('spot'))}: bull trigger "
                     f"{_f(L.get('bullish_trigger'))} · bear trigger "
                     f"{_f(L.get('bearish_trigger'))} · weekly pivot "
                     f"{_f(wk.get('weekly_pivot'))} "
                     f"(ceiling {_f(wk.get('weekly_ceiling'))} / floor "
                     f"{_f(wk.get('weekly_floor'))})")
    lines.append("")

    # rotation
    rotation = snapshot.get("rotation") or {}
    etfs = rotation.get("etfs") or []
    if etfs:
        lead = [e["symbol"] for e in etfs if e.get("status") == "leading"]
        imp = [e["symbol"] for e in etfs if e.get("status") == "improving"]
        det = [e["symbol"] for e in etfs if e.get("status") == "deteriorating"]
        lines.append(f"## Sectors — leading: {', '.join(lead) or 'none'} · "
                     f"improving: {', '.join(imp) or 'none'} · "
                     f"deteriorating: {', '.join(det) or 'none'}\n")

    # options positioning
    gex = (snapshot.get("options") or {}).get("QQQ") or {}
    if gex:
        lines.append(f"QQQ gamma: {gex.get('gamma_regime', '?')} · flip "
                     f"{_f(gex.get('zero_gamma_flip'))} · call wall "
                     f"{_f(gex.get('call_wall'))} · put wall "
                     f"{_f(gex.get('put_wall'))}\n")

    # setups
    setups = snapshot.get("setups") or {}
    lines.append("## Setups")
    if setups.get("no_trade"):
        lines.append(f"**Standing aside.** {setups.get('reason', '')}")
    else:
        rows = setups.get("setups") or []
        if setups.get("forced"):
            lines.append("_FORCED test mode — regime gate bypassed_")
        if not rows:
            f = setups.get("funnel") or {}
            lines.append(f"No setups cleared the gates "
                         f"({f.get('candidate_stocks', 0)} candidates, "
                         f"{f.get('passed_screen', 0)} passed the screen).")
        for s in rows:
            pin = " 📌" if s.get("pinned") else ""
            lines.append(
                f"- **{s['symbol']}** {s['direction']}{pin} "
                f"({s.get('confidence', '?')}/10, {s.get('sector_etf', '?')}): "
                f"entry {_f(s.get('entry_trigger'))} · stop {_f(s.get('stop'))} "
                f"· T1 {_f(s.get('target_1'))} · T2 {_f(s.get('target_2'))} "
                f"· {str(s.get('instrument', 'stock')).replace('_', ' ')}")
        sup = setups.get("suppressed") or []
        if sup:
            lines.append("\nSuppressed: " + "; ".join(
                f"{x['symbol']} ({x['reason']})" for x in sup))
    lines.append("")
    lines.append("---")
    lines.append("_Every level traces to engine evidence. Decision support, "
                 "not investment advice._")
    return "\n".join(lines)
