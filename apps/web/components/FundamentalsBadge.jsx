"use client";

// Phase 34 — fundamentals badge.
//
// Modeled on the ConfluenceScore pattern in Honest.jsx: a compact chip that
// refuses to stand alone as a bare verdict. Clicking it opens the full
// per-component evidence — the actual input, the rule applied, and the score
// that came out — so the grade is auditable down to the pixel.
//
// Three display rules that carry real weight:
//   1. grade "unavailable" renders as a MUTED dash, never as an F. "Not
//      measured" and "measured and bad" are different claims, and the
//      all-None snapshot is a common live path (yfinance swallows errors).
//   2. the earnings chip outranks the grade. A B-grade name reporting in two
//      days is an earnings risk first and a quality read second.
//   3. colour is never the only signal — the grade letter is always present
//      as text, and every state has a word attached.

import { useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const PCT = (v) => `${(Number(v) * 100).toFixed(1)}%`;

const COMPONENT_LABEL = {
  growth: "Growth",
  profitability: "Profitability",
  valuation: "Valuation",
  sponsorship: "Sponsorship",
};

// How each component's raw inputs are worded in the drill-down. Keeping the
// formatting here (rather than in the API) means the wire format stays plain.
function describeInputs(name, inputs = {}) {
  const bits = [];
  if (name === "growth") {
    if (inputs.revenue_growth != null) bits.push(`revenue ${PCT(inputs.revenue_growth)}`);
    if (inputs.eps_growth != null) bits.push(`EPS ${PCT(inputs.eps_growth)}`);
    if (inputs.engine_growth_grade) bits.push(`engine grade "${inputs.engine_growth_grade}"`);
  } else if (name === "profitability") {
    if (inputs.profit_margin != null) bits.push(`net margin ${PCT(inputs.profit_margin)}`);
  } else if (name === "valuation") {
    if (inputs.forward_pe != null) bits.push(`forward P/E ${Number(inputs.forward_pe).toFixed(1)}`);
    if (inputs.sector) bits.push(inputs.sector);
  } else if (name === "sponsorship") {
    if (inputs.institutional_pct != null) bits.push(`institutional ${PCT(inputs.institutional_pct)}`);
  }
  return bits.join(" · ") || "—";
}

function gradeTone(grade) {
  if (grade === "A" || grade === "B") return "var(--bull)";
  if (grade === "C") return "var(--muted)";
  if (grade === "D" || grade === "F") return "var(--bear)";
  return "var(--faint)"; // unavailable
}

export function FundamentalsBadge({
  symbol,
  assessment: provided,
  direction = "long",
  compact = false,
}) {
  const [assessment, setAssessment] = useState(provided || null);
  const [open, setOpen] = useState(false);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (provided || !symbol) return;
    let cancelled = false;
    setLoading(true);
    fetch(`${API}/api/fundamentals/${symbol}?direction=${direction}`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((d) => { if (!cancelled) setAssessment(d.assessment || null); })
      .catch((e) => { if (!cancelled) setError(e.message || "unavailable"); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [symbol, direction, provided]);

  if (loading) {
    return <span className="fundbadge loading" aria-label="Loading fundamentals">fund …</span>;
  }
  if (error) {
    return (
      <span className="fundbadge err" aria-label={`Fundamentals unavailable: ${error}`}>
        fund n/a
      </span>
    );
  }
  if (!assessment) return null;

  const { grade, quality_score: quality, alignment_score: alignment } = assessment;
  const unknown = grade === "unavailable";
  const earnings = assessment.earnings || {};
  const evidence = assessment.evidence || {};
  const label = unknown ? "—" : grade;

  const ariaParts = [
    `Fundamentals grade ${unknown ? "unavailable" : grade}`,
    unknown ? "no components could be scored" : `quality ${quality}`,
    earnings.in_gate_window ? `earnings in ${earnings.days_until} days` : null,
  ].filter(Boolean);

  return (
    <span className="fundwrap">
      <button
        type="button"
        className="fundbadge"
        style={{ borderColor: gradeTone(grade), color: gradeTone(grade) }}
        aria-label={ariaParts.join(", ")}
        aria-expanded={open}
        title="Fundamental quality + direction alignment. NOT a price signal."
        onClick={() => setOpen((v) => !v)}
      >
        fund {label}
      </button>

      {earnings.in_gate_window && (
        <span
          className="fundearn"
          aria-label={`Earnings in ${earnings.days_until} days on ${earnings.date}`}
        >
          EARNINGS {earnings.days_until}d
        </span>
      )}

      {open && (
        <span className="fundpop" role="dialog" aria-label="Fundamentals evidence">
          <b>Fundamentals evidence</b>

          <span className="fundhead">
            {unknown ? (
              <span className="fundnote">
                No component could be scored — this is <em>not measured</em>,
                not <em>measured and bad</em>.
              </span>
            ) : (
              <span className="num">
                grade {grade} · quality {quality} · {direction} alignment {alignment}
              </span>
            )}
          </span>

          <table className="fundtable">
            <thead>
              <tr><th>Component</th><th>Input</th><th>Score</th></tr>
            </thead>
            <tbody>
              {Object.entries(assessment.components || {}).map(([name, c]) => (
                <tr key={name} className={c.score == null ? "na" : undefined}>
                  <td>
                    {COMPONENT_LABEL[name] || name}
                    {c.low_confidence && <span className="fundlow"> thin</span>}
                  </td>
                  <td className="num">{describeInputs(name, c.inputs)}</td>
                  <td className="num">{c.score == null ? "unavailable" : c.score}</td>
                </tr>
              ))}
            </tbody>
          </table>

          {(assessment.unavailable || []).length > 0 && (
            <span className="fundnote">
              Dropped: {assessment.unavailable.map((u) => `${u.component} (${u.reason})`).join("; ")}.
              {evidence.renormalized && " Remaining weights were renormalized to sum to 1."}
            </span>
          )}

          {!compact && evidence.formula && (
            <span className="fundnote">{evidence.formula}</span>
          )}

          <span className="fundcaveat">
            ⚠ business quality, not a price signal. Valuation is bare forward
            P/E with no peer set; sponsorship is an ownership level with no
            trend behind it.
          </span>
        </span>
      )}
    </span>
  );
}

export default FundamentalsBadge;
