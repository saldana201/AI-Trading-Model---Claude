"use client";

// Phase 16 — the Book.
//
// Direction (LONG / SHORT) is the real partition: every setup lands in exactly
// one. OPTIONS and SHARES are *lenses* over that same set, labeled as such, so
// nobody reads the tab strip as four separate trade pools. A call spread shows
// up under LONG and under OPTIONS because it is one trade seen two ways.
//
// Empty tabs always render the API's reason rather than a blank panel — the
// chop-gate lesson: a correct "nothing here today, and here's why" must never
// look like a broken fetch.

import { useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const TABS = [
  { key: "long", label: "Long", kind: "partition" },
  { key: "short", label: "Short", kind: "partition" },
  { key: "options", label: "Options", kind: "lens" },
  { key: "shares", label: "Shares", kind: "lens" },
];

function Badge({ children, tone = "neutral" }) {
  const tones = {
    long: { borderColor: "#1e7f4f", color: "#4ade80" },
    short: { borderColor: "#8a2f2f", color: "#f87171" },
    opt: { borderColor: "#2f5f8a", color: "#7dd3fc" },
    neutral: { borderColor: "var(--line, #333)", color: "var(--faint, #888)" },
  };
  return (
    <span
      style={{
        fontSize: 10,
        letterSpacing: 0.4,
        padding: "2px 6px",
        borderRadius: 4,
        borderWidth: 1,
        borderStyle: "solid",
        ...tones[tone],
      }}
    >
      {children}
    </span>
  );
}

function Contract({ c }) {
  if (!c) return null;
  const legs =
    c.long_strike != null ? `${c.long_strike} / ${c.short_strike ?? "—"}` : c.strike;
  return (
    <div style={{ fontSize: 12, color: "var(--faint,#888)", marginTop: 6 }}>
      <div>
        {legs} · exp {c.expiry} ({c.dte}d)
        {c.iv_rank != null && ` · IVR ${(c.iv_rank * 100).toFixed(0)}%`}
        {c.spread_pct != null && ` · spread ${(c.spread_pct * 100).toFixed(1)}%`}
        {c.open_interest != null && ` · OI ${c.open_interest}`}
      </div>
      {c.expected_move != null && (
        <div style={{ marginTop: 2 }}>
          expected move {c.expected_move}
          {c.t1_within_expected_move === false && (
            <span style={{ color: "#fbbf24" }}> — T1 sits outside it</span>
          )}
        </div>
      )}
      {c.reason && <div style={{ marginTop: 2, fontStyle: "italic" }}>{c.reason}</div>}
    </div>
  );
}

function Card({ s }) {
  return (
    <article
      className="card"
      style={{ padding: 12, marginBottom: 10 }}
      aria-label={`${s.symbol} ${s.direction} setup`}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        <strong style={{ fontSize: 15 }}>{s.symbol}</strong>
        <Badge tone={s.direction === "long" ? "long" : "short"}>
          {String(s.direction || "").toUpperCase()}
        </Badge>
        <Badge tone={s.is_options ? "opt" : "neutral"}>{s.instrument_label}</Badge>
        {s.pinned && <Badge>PINNED</Badge>}
        {s.earnings_flag && <Badge tone="neutral">EARNINGS</Badge>}
        <span style={{ marginLeft: "auto", fontSize: 12, color: "var(--faint,#888)" }}>
          conf {s.confidence} · {s.sector_etf}
        </span>
      </div>

      <div className="num" style={{ fontSize: 13, marginTop: 8 }}>
        entry {s.entry_trigger} · stop {s.stop} · T1 {s.target_1} · T2 {s.target_2}
        {s.risk_reward_t1 != null && ` · R:R ${s.risk_reward_t1}`}
      </div>

      <Contract c={s.contract} />

      {s.stock_only_reason && (
        <div style={{ fontSize: 12, color: "#fbbf24", marginTop: 6 }}>
          shares only — {s.stock_only_reason}
        </div>
      )}
      {s.thesis && (
        <p style={{ fontSize: 12, marginTop: 8, marginBottom: 0, lineHeight: 1.5 }}>
          {s.thesis}
        </p>
      )}
    </article>
  );
}

export default function Book() {
  const [book, setBook] = useState(null);
  const [tab, setTab] = useState("long");
  const [both, setBoth] = useState(false);
  const [err, setErr] = useState(null);
  const [loading, setLoading] = useState(false);

  async function load(useBoth) {
    setLoading(true);
    setErr(null);
    try {
      const res = await fetch(`${API}/api/book${useBoth ? "/both" : ""}`);
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
      setBook(await res.json());
    } catch (e) {
      setErr(String(e.message || e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load(both);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [both]);

  const group = book?.[tab];
  const counts = book?.counts;

  return (
    <section className="card" style={{ marginTop: 18 }} aria-label="Book">
      <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
        <h2 style={{ margin: 0 }}>Book</h2>
        {counts && (
          <span style={{ fontSize: 12, color: "var(--faint,#888)" }}>
            {counts.total} setup{counts.total === 1 ? "" : "s"} · {counts.long} long ·{" "}
            {counts.short} short · {counts.options} as options
          </span>
        )}
        <label style={{ marginLeft: "auto", fontSize: 12, display: "flex", gap: 6 }}>
          <input
            type="checkbox"
            checked={both}
            onChange={(e) => setBoth(e.target.checked)}
          />
          scan both directions
        </label>
      </div>

      <div className="sugg" style={{ marginTop: 10, display: "flex", gap: 6 }}>
        {TABS.map((t) => (
          <button
            key={t.key}
            className="chip"
            type="button"
            onClick={() => setTab(t.key)}
            style={{
              opacity: tab === t.key ? 1 : 0.55,
              fontWeight: tab === t.key ? 600 : 400,
            }}
          >
            {t.label} {counts ? `(${counts[t.key] ?? 0})` : ""}
          </button>
        ))}
      </div>

      {loading && (
        <p style={{ fontSize: 13, color: "var(--faint,#888)" }}>loading the book…</p>
      )}
      {err && <p style={{ fontSize: 13, color: "#f87171" }}>could not load: {err}</p>}

      {group && (
        <div style={{ marginTop: 12 }}>
          {group.view === "cross-cutting" && (
            <p
              style={{
                fontSize: 12,
                color: "var(--faint,#888)",
                fontStyle: "italic",
                marginTop: 0,
              }}
            >
              {group.note}
            </p>
          )}
          {group.setups?.length === 0 && (
            <p style={{ fontSize: 13, color: "var(--faint,#888)" }}>
              {group.reason || "nothing here."}
            </p>
          )}
          {group.setups?.map((s) => (
            <Card key={`${s.symbol}-${s.direction}-${s.instrument}`} s={s} />
          ))}
        </div>
      )}
    </section>
  );
}
