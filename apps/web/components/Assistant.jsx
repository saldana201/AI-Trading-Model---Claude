"use client";

// Phase 12 — Trade Assistant.
// Three roles, all backed by traceable engine evidence:
//   1. Plans   — GET /api/assistant/plans: sized bracket + copy-ready orders
//   2. Advice  — GET /api/assistant/advise: "what do I do right now" per trade
//   3. Fill    — POST /api/assistant/fill: log your actual entry so the
//                lifecycle manages YOUR trade, not the idealized one.

import { useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function Assistant() {
  const [plans, setPlans] = useState([]);
  const [chopWarn, setChopWarn] = useState(null);
  const [advice, setAdvice] = useState([]);
  const [copied, setCopied] = useState(null);
  const [err, setErr] = useState(null);

  async function loadPlans() {
    try {
      const r = await fetch(`${API}/api/assistant/plans`);
      const b = await r.json();
      setPlans(b.plans || []);
      setChopWarn(b.chop_warning || null);
    } catch {
      setErr("Could not load trade plans.");
    }
  }
  async function loadAdvice() {
    try {
      const r = await fetch(`${API}/api/assistant/advise`);
      const b = await r.json();
      setAdvice(b.advice || []);
    } catch {
      /* advice needs armed trades + live quotes; silent when unavailable */
    }
  }

  useEffect(() => {
    loadPlans();
    loadAdvice();
    const t = setInterval(loadAdvice, 30000);
    return () => clearInterval(t);
  }, []);

  function copyPlan(plan) {
    const text =
      `${plan.symbol} ${plan.direction.toUpperCase()} — ${plan.sizing.shares} sh\n` +
      plan.text;
    navigator.clipboard?.writeText(text);
    setCopied(plan.symbol);
    setTimeout(() => setCopied(null), 1500);
  }

  return (
    <div style={S.wrap}>
      <div style={S.eyebrow}>Trade Assistant · sizing · plans · live advice</div>

      {chopWarn && <div style={S.warn}>{chopWarn}</div>}
      {err && <div style={{ ...S.warn, color: "var(--bear)" }}>{err}</div>}

      {advice.length > 0 && (
        <div style={S.adviceBox}>
          <div style={S.subhead}>What to do right now</div>
          {advice.map((a) => (
            <div key={a.trade_id} style={S.adviceRow}>
              <span style={{ ...S.tag, ...tagColor(a.action) }}>{a.action}</span>
              <b className="num">{a.symbol}</b>
              <span style={{ color: "var(--muted)" }}>{a.instruction}</span>
            </div>
          ))}
        </div>
      )}

      {plans.length === 0 ? (
        <div style={{ color: "var(--muted)" }}>
          No setups to plan — the composer is in a no-trade regime or nothing
          cleared the confidence floor.
        </div>
      ) : (
        <div style={S.cards}>
          {plans.map((p) => (
            <PlanCard
              key={p.symbol + p.bracket.entry}
              plan={p}
              copied={copied === p.symbol}
              onCopy={() => copyPlan(p)}
              onFilled={loadAdvice}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function PlanCard({ plan, copied, onCopy, onFilled }) {
  const s = plan.sizing;
  const b = plan.bracket;
  const long = plan.direction === "long";
  return (
    <div style={S.card}>
      <div style={S.cardHead}>
        <b className="num" style={{ fontSize: 16 }}>{plan.symbol}</b>
        <span style={{ ...S.dir, color: long ? "var(--bull)" : "var(--bear)" }}>
          {plan.direction}
        </span>
        {plan.confidence != null && (
          <span style={S.conf}>conf {plan.confidence}</span>
        )}
        <button style={S.copy} onClick={onCopy}>
          {copied ? "copied" : "copy plan"}
        </button>
      </div>

      <div style={S.sizeRow}>
        <Stat label="Shares" value={s.shares} />
        <Stat label="Risk" value={`$${s.dollar_risk ?? "—"}`} />
        <Stat label="Position" value={`$${s.position_value ?? "—"}`} />
        {s.capped_by_position_limit && (
          <span style={S.capNote}>capped by position limit</span>
        )}
      </div>

      <div style={S.levels}>
        <Level label="Entry" v={b.entry} />
        <Level label="Stop" v={b.stop} tone="bear" />
        <Level label="T1" v={b.target_1} tone="bull" sub={`trim ${b.trim_quantity}`} />
        <Level label="T2" v={b.target_2} tone="bull" sub={`run ${b.runner_quantity}`} />
      </div>

      <ol style={S.steps}>
        {plan.steps.map((st) => (
          <li key={st.step} style={S.step}>
            <span style={S.stepAction}>{st.action}</span> {st.order}
          </li>
        ))}
      </ol>

      <FillForm plan={plan} onFilled={onFilled} />
    </div>
  );
}

function FillForm({ plan, onFilled }) {
  const [price, setPrice] = useState(plan.bracket.entry);
  const [shares, setShares] = useState(plan.sizing.shares);
  const [state, setState] = useState(null);

  // fill needs an armed trade_id; setups become trades on /api/alerts/arm.
  // We look one up by symbol from the live alert state.
  async function submit() {
    setState("working");
    try {
      const st = await fetch(`${API}/api/alerts/state`).then((r) => r.json());
      const match = (st.trades || []).find(
        (t) => t.symbol === plan.symbol && t.state === "WATCHING"
      );
      if (!match) {
        setState("arm-first");
        return;
      }
      const r = await fetch(`${API}/api/assistant/fill`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          trade_id: match.id,
          price: Number(price),
          shares: Number(shares),
        }),
      });
      setState(r.ok ? "logged" : "error");
      if (r.ok) onFilled?.();
    } catch {
      setState("error");
    }
  }

  return (
    <div style={S.fill}>
      <span style={S.fillLabel}>Log my fill</span>
      <input
        style={S.fillInput} className="num" type="number" step="any"
        value={price} onChange={(e) => setPrice(e.target.value)}
      />
      <input
        style={S.fillInput} className="num" type="number"
        value={shares} onChange={(e) => setShares(e.target.value)}
      />
      <button style={S.fillBtn} onClick={submit}>log</button>
      {state === "logged" && <span style={{ color: "var(--bull)" }}>tracking</span>}
      {state === "arm-first" && (
        <span style={{ color: "var(--gold)" }}>arm alerts first</span>
      )}
      {state === "error" && <span style={{ color: "var(--bear)" }}>failed</span>}
    </div>
  );
}

const Stat = ({ label, value }) => (
  <div style={S.stat}>
    <div style={S.statLabel}>{label}</div>
    <div className="num" style={S.statValue}>{value}</div>
  </div>
);

const Level = ({ label, v, tone, sub }) => (
  <div style={S.level}>
    <span style={S.levelLabel}>{label}</span>
    <span
      className="num"
      style={{ color: tone === "bear" ? "var(--bear)" : tone === "bull" ? "var(--bull)" : "var(--text)" }}
    >
      {v}
    </span>
    {sub && <span style={S.levelSub}>{sub}</span>}
  </div>
);

function tagColor(action) {
  const map = {
    exit: "var(--bear)", stand_down: "var(--bear)",
    trim: "var(--gold)", enter: "var(--bull)", hold: "var(--muted)",
    wait: "var(--muted)", done: "var(--faint)",
  };
  return { background: map[action] || "var(--muted)", color: "#0B1018" };
}

const S = {
  wrap: { padding: "18px 0", borderTop: "1px solid var(--line)" },
  eyebrow: {
    fontSize: 10.5, letterSpacing: ".14em", textTransform: "uppercase",
    color: "var(--faint)", fontWeight: 600, marginBottom: 14,
  },
  subhead: { color: "var(--muted)", fontSize: 12, marginBottom: 8 },
  warn: {
    background: "rgba(217,179,106,.08)", border: "1px solid #3a3424",
    color: "var(--gold)", borderRadius: 8, padding: "9px 12px",
    fontSize: 12.5, marginBottom: 14,
  },
  adviceBox: {
    background: "var(--panel)", border: "1px solid var(--line)", borderRadius: 10,
    padding: "12px 14px", marginBottom: 16,
  },
  adviceRow: {
    display: "flex", gap: 10, alignItems: "baseline", padding: "5px 0", fontSize: 13,
  },
  tag: {
    fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: ".06em",
    borderRadius: 4, padding: "2px 7px",
  },
  cards: {
    display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))",
    gap: 14,
  },
  card: {
    background: "var(--panel)", border: "1px solid var(--line)", borderRadius: 12,
    padding: 16,
  },
  cardHead: { display: "flex", alignItems: "center", gap: 10, marginBottom: 12 },
  dir: { fontSize: 11, textTransform: "uppercase", letterSpacing: ".08em", fontWeight: 600 },
  conf: { marginLeft: "auto", color: "var(--muted)", fontSize: 11.5 },
  copy: {
    background: "transparent", border: "1px solid var(--line)", color: "var(--muted)",
    borderRadius: 6, padding: "3px 9px", fontSize: 11, cursor: "pointer",
  },
  sizeRow: { display: "flex", gap: 18, alignItems: "flex-end", marginBottom: 12, flexWrap: "wrap" },
  stat: {},
  statLabel: { color: "var(--faint)", fontSize: 10.5, textTransform: "uppercase", letterSpacing: ".08em" },
  statValue: { fontSize: 18 },
  capNote: { color: "var(--gold)", fontSize: 11 },
  levels: {
    display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 8,
    padding: "10px 0", borderTop: "1px solid var(--line)", borderBottom: "1px solid var(--line)",
    marginBottom: 12,
  },
  level: { display: "flex", flexDirection: "column", gap: 2 },
  levelLabel: { color: "var(--faint)", fontSize: 10.5 },
  levelSub: { color: "var(--muted)", fontSize: 10 },
  steps: { margin: 0, paddingLeft: 18, display: "flex", flexDirection: "column", gap: 5 },
  step: { fontSize: 12, color: "var(--text)" },
  stepAction: {
    color: "var(--gold)", textTransform: "uppercase", fontSize: 10, letterSpacing: ".06em",
    marginRight: 4,
  },
  fill: {
    display: "flex", gap: 8, alignItems: "center", marginTop: 12, paddingTop: 12,
    borderTop: "1px solid var(--line)", flexWrap: "wrap",
  },
  fillLabel: { color: "var(--muted)", fontSize: 11.5 },
  fillInput: {
    width: 84, background: "var(--panel2)", border: "1px solid var(--line)",
    borderRadius: 6, color: "var(--text)", padding: "5px 8px", fontSize: 12,
  },
  fillBtn: {
    background: "var(--gold)", color: "#1a1508", border: "none", borderRadius: 6,
    padding: "5px 12px", fontWeight: 600, cursor: "pointer", fontSize: 12,
  },
};
