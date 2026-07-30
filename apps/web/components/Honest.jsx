"use client";

// Phase 30 — honest-mode UI.
//
// Phases 15-28 measured this system on 506 real trades: +37.4% vs QQQ's +111.7%,
// with a deeper drawdown (-33.0% vs -22.8%) and worse Sharpe (0.55 vs 1.00).
// Component edges collapse to ~0 at adequate sample size, and the score has been
// anti-predictive in several runs.
//
// The engines still produce genuinely useful facts. What failed is the leap from
// facts to "take this trade, confidence 8.2". So the UI's job changes: it must
// present the score as a CONFLUENCE measure (how many engines agree) and never
// let a number stand alone as though it were a probability of profit.
//
// Note on naming: the wire format keeps `confidence` because that field is
// threaded through scoring, the composer, the SQLite journal, and the REST
// resources. Renaming it internally is a multi-file refactor with real drift
// risk, so the relabel lives here in the display layer only.

import { useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// ---------------------------------------------------------------------------
// BenchmarkStrip — always visible, so a trade idea is never seen in isolation.
// ---------------------------------------------------------------------------

export function BenchmarkStrip() {
  const [b, setB] = useState(null);
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    fetch(`${API}/api/benchmark-context`)
      .then((r) => (r.ok ? r.json() : null))
      .then(setB)
      .catch(() => {});
  }, []);

  if (!b || dismissed) return null;
  const worse = b.strategy_total_return_pct < b.total_return_pct;

  return (
    <section
      aria-label="Validation context"
      style={{
        borderWidth: 1,
        borderStyle: "solid",
        borderColor: worse ? "#8a6a2f" : "#2f5f8a",
        borderRadius: 8,
        padding: "10px 12px",
        marginTop: 14,
        background: "rgba(138,106,47,0.08)",
        fontSize: 13,
        lineHeight: 1.55,
      }}
    >
      <div style={{ display: "flex", gap: 8, alignItems: "baseline" }}>
        <strong style={{ color: "#fbbf24" }}>Validation context</strong>
        <button
          className="chip"
          type="button"
          onClick={() => setDismissed(true)}
          style={{ marginLeft: "auto", fontSize: 11 }}
        >
          hide
        </button>
      </div>
      <div style={{ marginTop: 6 }}>{b.headline}</div>
      <div style={{ marginTop: 4, color: "var(--faint,#999)" }}>{b.verdict}</div>
      <table style={{ marginTop: 8, fontSize: 12, borderCollapse: "collapse" }}>
        <tbody>
          <Row label="Total return" a={`${b.strategy_total_return_pct}%`} bb={`${b.total_return_pct}%`} />
          <Row label="Max drawdown" a={`${b.strategy_max_dd_pct}%`} bb={`${b.benchmark_max_dd_pct}%`} />
          <Row label="Sharpe" a={b.strategy_sharpe} bb={b.benchmark_sharpe} />
        </tbody>
      </table>
    </section>
  );
}

function Row({ label, a, bb }) {
  return (
    <tr>
      <td style={{ paddingRight: 14, color: "var(--faint,#999)" }}>{label}</td>
      <td style={{ paddingRight: 14 }}>system {a}</td>
      <td>QQQ {bb}</td>
    </tr>
  );
}

// ---------------------------------------------------------------------------
// ConfluenceScore — the replacement for a bare confidence number.
// ---------------------------------------------------------------------------

export function ConfluenceScore({ value, calibration, compact = false }) {
  const [cal, setCal] = useState(calibration || null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (calibration || value == null) return;
    fetch(`${API}/api/calibration`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (!d?.bands) return;
        const band = value < 6.5 ? "<6.5" : value < 7.5 ? "6.5-7.5" : ">=7.5";
        setCal(d.bands[band] || null);
      })
      .catch(() => {});
  }, [value, calibration]);

  if (value == null) return null;
  const h = cal?.historical;
  const negative = h?.avg_r != null && h.avg_r <= 0;
  const thin = h?.n != null && h.n < 30;

  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
      <span
        title="Confluence: how many engines agree. NOT a probability of profit."
        style={{
          fontSize: 12,
          padding: "2px 6px",
          borderRadius: 4,
          borderWidth: 1,
          borderStyle: "solid",
          borderColor: negative ? "#8a2f2f" : thin ? "#8a6a2f" : "var(--line,#333)",
          color: negative ? "#f87171" : thin ? "#fbbf24" : "var(--fg,#ddd)",
        }}
      >
        confluence {value}
      </span>
      {h && (
        <button
          className="chip"
          type="button"
          onClick={() => setOpen((v) => !v)}
          style={{ fontSize: 10 }}
        >
          {compact ? "?" : `hist ${h.avg_r >= 0 ? "+" : ""}${h.avg_r}R · n=${h.n}`}
        </button>
      )}
      {open && cal && (
        <span
          style={{
            fontSize: 11,
            color: "var(--faint,#999)",
            maxWidth: 420,
            lineHeight: 1.45,
          }}
        >
          {cal.reliability}. {cal.caveat}
        </span>
      )}
    </span>
  );
}

// ---------------------------------------------------------------------------
// CalibrationPanel — the full measured record, per band.
// ---------------------------------------------------------------------------

export function CalibrationPanel() {
  const [d, setD] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    fetch(`${API}/api/calibration`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(r.statusText))))
      .then(setD)
      .catch((e) => setErr(String(e.message || e)));
  }, []);

  return (
    <section className="card" style={{ marginTop: 18 }} aria-label="Calibration">
      <h2 style={{ margin: 0 }}>Calibration</h2>
      <p style={{ fontSize: 12, color: "var(--faint,#999)", marginTop: 6 }}>
        What actually happened to setups in each confluence band, measured on the
        validated backtest net of modelled costs. A band with few trades, or a
        negative average, is reported as such.
      </p>
      {err && <p style={{ fontSize: 13, color: "#f87171" }}>could not load: {err}</p>}
      {d?.bands && (
        <table style={{ fontSize: 13, borderCollapse: "collapse", marginTop: 8 }}>
          <thead>
            <tr style={{ color: "var(--faint,#999)", textAlign: "left" }}>
              <th style={{ paddingRight: 16 }}>band</th>
              <th style={{ paddingRight: 16 }}>n</th>
              <th style={{ paddingRight: 16 }}>avg R</th>
              <th style={{ paddingRight: 16 }}>win rate</th>
              <th>reading</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(d.bands).map(([band, info]) => {
              const h = info.historical || {};
              const neg = h.avg_r != null && h.avg_r <= 0;
              return (
                <tr key={band}>
                  <td style={{ paddingRight: 16 }}>{band}</td>
                  <td style={{ paddingRight: 16 }}>{h.n ?? "—"}</td>
                  <td
                    style={{
                      paddingRight: 16,
                      color: neg ? "#f87171" : "#4ade80",
                    }}
                  >
                    {h.avg_r != null ? `${h.avg_r >= 0 ? "+" : ""}${h.avg_r}` : "—"}
                  </td>
                  <td style={{ paddingRight: 16 }}>{h.win_rate ?? "—"}</td>
                  <td style={{ fontSize: 11, color: "var(--faint,#999)" }}>
                    {info.reliability}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
      {d && (
        <p style={{ fontSize: 11, color: "var(--faint,#999)", marginTop: 10 }}>
          source: {d.source}
        </p>
      )}
    </section>
  );
}

export default CalibrationPanel;
