"use client";

// Phase 12 — Settings: presets + live config editing.
// Reads GET /api/config, applies presets via POST /api/config/presets/{name},
// and PUTs partial patches. Numbers are the same named parameters the
// composer, scorer, and lifecycle read — this is the glass-box tuning surface.

import { useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const FIELDS = [
  ["setup", "entry_buffer_atr", "Entry buffer (ATR)"],
  ["setup", "stop_atr", "Stop fallback (ATR)"],
  ["setup", "max_stop_atr", "Max stop risk (ATR)"],
  ["setup", "t1_atr", "Target 1 (ATR)"],
  ["setup", "t2_atr", "Target 2 (ATR)"],
  ["risk", "min_score", "Confidence floor (0–10)"],
  ["risk", "min_rr_t1", "Min R:R at T1"],
  ["risk", "min_rr_t2", "Min R:R at T2"],
  ["risk", "account_size", "Account size ($)"],
  ["risk", "risk_per_trade_pct", "Risk per trade (%)"],
  ["risk", "max_position_pct", "Max position (% of acct)"],
  ["lifecycle", "max_trigger_attempts", "Trigger attempts"],
  ["lifecycle", "trail_atr", "Trail distance (ATR)"],
  ["compose", "max_setups", "Max setups shown"],
];

export default function Settings() {
  const [cfg, setCfg] = useState(null);
  const [presets, setPresets] = useState({});
  const [draft, setDraft] = useState({});
  const [msg, setMsg] = useState(null);
  const [busy, setBusy] = useState(false);

  async function load() {
    const [c, p] = await Promise.all([
      fetch(`${API}/api/config`).then((r) => r.json()),
      fetch(`${API}/api/config/presets`).then((r) => r.json()),
    ]);
    setCfg(c.config);
    setPresets(p.presets || {});
    setDraft({});
  }
  useEffect(() => {
    load().catch(() => setMsg({ err: "Could not reach the API." }));
  }, []);

  function edit(section, key, raw) {
    setDraft((d) => ({ ...d, [`${section}.${key}`]: raw }));
  }

  function buildPatch() {
    const patch = {};
    for (const [path, raw] of Object.entries(draft)) {
      const [section, key] = path.split(".");
      const num = Number(raw);
      if (raw === "" || Number.isNaN(num)) continue;
      (patch[section] ||= {})[key] = num;
    }
    // chop mode + force direction are selects, tracked under gates.*
    if (draft["gates.chop_mode"] !== undefined)
      (patch.gates ||= {}).chop_mode = draft["gates.chop_mode"];
    if (draft["gates.force_direction"] !== undefined)
      (patch.gates ||= {}).force_direction = draft["gates.force_direction"];
    return patch;
  }

  async function save() {
    const patch = buildPatch();
    if (!Object.keys(patch).length) return;
    setBusy(true);
    setMsg(null);
    try {
      const r = await fetch(`${API}/api/config`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ patch }),
      });
      const body = await r.json();
      if (!r.ok) throw new Error(body.detail || "rejected");
      setCfg(body.config);
      setDraft({});
      setMsg({ ok: `Saved. ${Object.keys(body.event.changed).length} value(s) changed.` });
    } catch (e) {
      setMsg({ err: String(e.message || e) });
    } finally {
      setBusy(false);
    }
  }

  async function applyPreset(name) {
    setBusy(true);
    setMsg(null);
    try {
      const r = await fetch(`${API}/api/config/presets/${name}`, { method: "POST" });
      const body = await r.json();
      if (!r.ok) throw new Error(body.detail || "rejected");
      setCfg(body.config);
      setDraft({});
      setMsg({ ok: `Applied "${name}" preset.` });
    } catch (e) {
      setMsg({ err: String(e.message || e) });
    } finally {
      setBusy(false);
    }
  }

  if (!cfg) return <div style={S.wrap}>Loading settings…</div>;

  const gates = cfg.gates || {};
  const val = (section, key) => {
    const k = `${section}.${key}`;
    return draft[k] !== undefined ? draft[k] : cfg[section]?.[key];
  };
  const dirty = Object.keys(draft).length > 0;

  return (
    <div style={S.wrap}>
      <div style={S.eyebrow}>Settings · glass-box configuration</div>

      <div style={S.presets}>
        {Object.entries(presets).map(([name, p]) => (
          <button
            key={name}
            style={S.preset}
            disabled={busy}
            title={p.description}
            onClick={() => applyPreset(name)}
          >
            <div style={{ fontWeight: 600, textTransform: "capitalize" }}>{name}</div>
            <div style={S.presetDesc}>{p.description}</div>
          </button>
        ))}
      </div>

      <div style={S.grid}>
        {FIELDS.map(([section, key, label]) => (
          <label key={`${section}.${key}`} style={S.field}>
            <span style={S.label}>{label}</span>
            <input
              style={S.input}
              className="num"
              type="number"
              step="any"
              value={val(section, key) ?? ""}
              onChange={(e) => edit(section, key, e.target.value)}
            />
          </label>
        ))}

        <label style={S.field}>
          <span style={S.label}>Chop gate</span>
          <select
            style={S.input}
            value={draft["gates.chop_mode"] ?? gates.chop_mode}
            onChange={(e) => setDraft((d) => ({ ...d, "gates.chop_mode": e.target.value }))}
          >
            <option value="hard">hard — no-trade in chop</option>
            <option value="soft">soft — compose with a warning</option>
            <option value="off">off — trade regardless</option>
          </select>
        </label>

        <label style={S.field}>
          <span style={S.label}>Force direction</span>
          <select
            style={S.input}
            value={draft["gates.force_direction"] ?? gates.force_direction ?? ""}
            onChange={(e) =>
              setDraft((d) => ({ ...d, "gates.force_direction": e.target.value }))
            }
          >
            <option value="">auto (regime-driven)</option>
            <option value="long">long only</option>
            <option value="short">short only</option>
          </select>
        </label>
      </div>

      <div style={S.actions}>
        <button style={S.save} disabled={!dirty || busy} onClick={save}>
          {busy ? "Saving…" : dirty ? "Save changes" : "No changes"}
        </button>
        {dirty && (
          <button style={S.reset} disabled={busy} onClick={() => setDraft({})}>
            Discard
          </button>
        )}
        {msg?.ok && <span style={{ color: "var(--bull)" }}>{msg.ok}</span>}
        {msg?.err && <span style={{ color: "var(--bear)" }}>{msg.err}</span>}
      </div>
    </div>
  );
}

const S = {
  wrap: { padding: "18px 0", borderTop: "1px solid var(--line)" },
  eyebrow: {
    fontSize: 10.5, letterSpacing: ".14em", textTransform: "uppercase",
    color: "var(--faint)", fontWeight: 600, marginBottom: 14,
  },
  presets: { display: "flex", gap: 10, flexWrap: "wrap", marginBottom: 18 },
  preset: {
    flex: "1 1 220px", textAlign: "left", background: "var(--panel)",
    border: "1px solid var(--line)", borderRadius: 8, padding: "10px 12px",
    color: "var(--text)", cursor: "pointer", fontFamily: "var(--sans)",
  },
  presetDesc: { color: "var(--muted)", fontSize: 11.5, marginTop: 3 },
  grid: {
    display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))",
    gap: 12,
  },
  field: { display: "flex", flexDirection: "column", gap: 4 },
  label: { color: "var(--muted)", fontSize: 12 },
  input: {
    background: "var(--panel2)", border: "1px solid var(--line)", borderRadius: 6,
    color: "var(--text)", padding: "7px 9px", fontSize: 13, fontFamily: "var(--mono)",
  },
  actions: { display: "flex", gap: 12, alignItems: "center", marginTop: 18 },
  save: {
    background: "var(--gold)", color: "#1a1508", border: "none", borderRadius: 6,
    padding: "8px 16px", fontWeight: 600, cursor: "pointer",
  },
  reset: {
    background: "transparent", color: "var(--muted)", border: "1px solid var(--line)",
    borderRadius: 6, padding: "8px 14px", cursor: "pointer",
  },
};
