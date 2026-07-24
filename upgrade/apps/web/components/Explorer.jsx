"use client";

// Phase 14 — Universe Explorer.
//
// Every sector expandable, every ticker viewable with the full card
// (entry/stop/targets/R:R, instrument line, thesis, risks) — the same
// treatment composed setups get. The difference is honesty about gating:
// each card carries a per-gate PASS/FAIL report, so you see the full
// picture while still relying on the triggers to arm setups. Cards here
// are view-only; arming stays with the composed list.

import { useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function Explorer() {
  const [universe, setUniverse] = useState(null);
  const [open, setOpen] = useState({});        // etf -> bool
  const [cards, setCards] = useState({});      // symbol -> card result
  const [loading, setLoading] = useState({});  // symbol -> bool
  const [active, setActive] = useState({});    // etf -> symbol shown
  const [err, setErr] = useState(null);

  useEffect(() => {
    fetch(`${API}/api/explore`)
      .then((r) => r.json())
      .then(setUniverse)
      .catch(() => setErr("Could not load the universe."));
  }, []);

  async function loadCard(etf, symbol) {
    setActive((a) => ({ ...a, [etf]: symbol }));
    if (cards[symbol]) return;
    setLoading((l) => ({ ...l, [symbol]: true }));
    try {
      const r = await fetch(`${API}/api/explore/${symbol}`);
      const body = await r.json();
      setCards((c) => ({ ...c, [symbol]: r.ok ? body : { error: body.detail } }));
    } catch {
      setCards((c) => ({ ...c, [symbol]: { error: "request failed" } }));
    } finally {
      setLoading((l) => ({ ...l, [symbol]: false }));
    }
  }

  if (err) return <div style={{ color: "var(--bear)", padding: "16px 0" }}>{err}</div>;
  if (!universe) return <div style={{ padding: "16px 0", color: "var(--muted)" }}>Loading universe…</div>;

  const sectors = [...universe.sectors].sort(
    (a, b) => (a.rank_4w ?? 99) - (b.rank_4w ?? 99)
  );

  return (
    <article className="card" aria-label="Universe explorer">
      <h2>
        Universe{" "}
        <span className="num">
          {sectors.length} sectors · {universe.direction} bias ·{" "}
          {universe.regime.regime} ({universe.regime.risk_score >= 0 ? "+" : ""}
          {universe.regime.risk_score})
        </span>
      </h2>
      <p style={{ color: "var(--faint)", fontSize: 11.5, margin: "6px 0 10px" }}>
        Full picture, view-only. Cards show every gate honestly — only the
        composed setups above can be armed.
      </p>

      {sectors.map((sec) => (
        <div key={sec.etf} style={S.sector}>
          <button
            style={S.sectorHead}
            onClick={() => setOpen((o) => ({ ...o, [sec.etf]: !o[sec.etf] }))}
          >
            <span style={{ width: 14, color: "var(--faint)" }}>
              {open[sec.etf] ? "▾" : "▸"}
            </span>
            <b className="num">{sec.etf}</b>
            <span className={`rotchip ${sec.status}`}>{sec.status}</span>
            {sec.rank_4w != null && (
              <span style={{ color: "var(--faint)", fontSize: 11 }}>
                #{sec.rank_4w} 4w
              </span>
            )}
            <span style={{ marginLeft: "auto", color: "var(--muted)", fontSize: 11.5 }}>
              {sec.tickers.length
                ? `${sec.tickers.length} ticker${sec.tickers.length === 1 ? "" : "s"}`
                : "no watchlist entries"}
            </span>
          </button>

          {open[sec.etf] && (
            <div style={S.body}>
              {sec.tickers.length === 0 && (
                <div style={{ color: "var(--faint)", fontSize: 12 }}>
                  Rotation tracks this sector but watchlist.json has no names
                  for it — add some to make it explorable.
                </div>
              )}
              <div style={S.chips}>
                {sec.tickers.map((t) => (
                  <button
                    key={t.symbol}
                    style={{
                      ...S.chip,
                      ...(active[sec.etf] === t.symbol ? S.chipActive : {}),
                    }}
                    onClick={() => loadCard(sec.etf, t.symbol)}
                  >
                    {t.pinned && <span style={{ marginRight: 4 }}>📌</span>}
                    <span className="num">{t.symbol}</span>
                  </button>
                ))}
              </div>

              {active[sec.etf] && (
                <TickerCard
                  symbol={active[sec.etf]}
                  data={cards[active[sec.etf]]}
                  busy={loading[active[sec.etf]]}
                />
              )}
            </div>
          )}
        </div>
      ))}
    </article>
  );
}

function TickerCard({ symbol, data, busy }) {
  if (busy || !data)
    return <div style={{ color: "var(--muted)", fontSize: 12.5, padding: "10px 0" }}>
      Building {symbol} card from engine evidence…
    </div>;

  if (data.error && !data.card)
    return (
      <div className="notrade" style={{ marginTop: 10 }}>
        <b>{symbol}:</b> {data.error}
      </div>
    );

  const x = data.card;
  const failed = data.gates.filter((g) => !g.passed);

  return (
    <div className="setup" style={{ marginTop: 10 }}>
      <div className="head">
        <span className="sym num">{x.symbol}</span>
        <span className={`state ${x.direction === "long" ? "good" : "bad"}`}>
          {x.direction}
        </span>
        {x.pinned && <span className="state warn">PINNED</span>}
        <span className={`rotchip ${x.sector_status}`}>
          {x.sector_etf} {x.sector_status}
        </span>
        {x.earnings_flag && <span className="state warn">earnings window</span>}
        <span
          className="conf num"
          style={{
            color:
              x.confidence >= 7.5
                ? "var(--bull)"
                : x.confidence >= 6.5
                ? "var(--gold)"
                : "var(--muted)",
          }}
        >
          {x.confidence.toFixed(1)}
          <span style={{ color: "var(--faint)", fontSize: 11 }}>/10</span>
        </span>
      </div>

      <div className="lvls">
        {[
          ["Entry", x.entry_trigger, "var(--gold)"],
          ["Stop", x.stop, "var(--bear)"],
          ["Target 1", x.target_1, "var(--bull)"],
          ["Target 2", x.target_2, "var(--bull)"],
        ].map(([label, v, color]) => (
          <div className="lvl" key={label}>
            <div className="eyebrow">{label}</div>
            <div className="v num" style={{ color }}>{v}</div>
          </div>
        ))}
        <div className="lvl">
          <div className="eyebrow">R:R T1/T2</div>
          <div className="v num">
            {x.risk_reward_t1} / {x.risk_reward_t2}
          </div>
        </div>
      </div>

      <div className="thesis">{x.thesis}</div>
      {(x.risks || []).length > 0 && (
        <div className="riskline">⚠ {x.risks.join(" · ")}</div>
      )}

      {/* the honesty section: why this is or isn't in today's setups */}
      <div style={S.gates}>
        <div className="eyebrow" style={{ marginBottom: 5 }}>
          {data.in_composed
            ? "Passes every gate — this appears in today's composed setups"
            : "View-only — not in today's composed setups"}
        </div>
        {data.gates.map((g) => (
          <div key={g.name} style={S.gateRow}>
            <span style={{ color: g.passed ? "var(--bull)" : "var(--bear)", width: 38, fontSize: 10.5, fontWeight: 700 }}>
              {g.passed ? "PASS" : "FAIL"}
            </span>
            <span style={{ color: "var(--muted)", width: 130, fontSize: 11.5 }}>
              {g.name.replaceAll("_", " ")}
            </span>
            <span style={{ color: g.passed ? "var(--faint)" : "var(--text)", fontSize: 11.5 }}>
              {g.detail}
            </span>
          </div>
        ))}
        {!data.in_composed && failed.length > 0 && (
          <div style={{ color: "var(--faint)", fontSize: 11, marginTop: 6 }}>
            Arming stays trigger-driven: this card becomes actionable only if{" "}
            {failed.map((g) => g.name.replaceAll("_", " ")).join(" and ")}{" "}
            resolve.
          </div>
        )}
      </div>
    </div>
  );
}

const S = {
  sector: { borderTop: "1px solid var(--line)" },
  sectorHead: {
    display: "flex", alignItems: "center", gap: 10, width: "100%",
    background: "transparent", border: "none", color: "var(--text)",
    padding: "9px 2px", cursor: "pointer", fontFamily: "var(--sans)",
    fontSize: 13, textAlign: "left",
  },
  body: { padding: "2px 0 12px 24px" },
  chips: { display: "flex", flexWrap: "wrap", gap: 6 },
  chip: {
    background: "var(--panel2)", border: "1px solid var(--line)",
    borderRadius: 6, color: "var(--text)", padding: "4px 10px",
    fontSize: 12, cursor: "pointer",
  },
  chipActive: { borderColor: "var(--gold)", color: "var(--gold)" },
  gates: {
    marginTop: 10, paddingTop: 8, borderTop: "1px dashed var(--line)",
  },
  gateRow: { display: "flex", gap: 8, alignItems: "baseline", padding: "2px 0" },
};
