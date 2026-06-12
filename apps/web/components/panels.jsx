// Confluence panels — each dashboard panel as a server component.
// Class names match app/globals.css (ported from the Phase 2–5 dashboard),
// so this is a 1:1 migration of the proven UI.

const fmt = (v, d = 2) => (v == null ? "—" : Number(v).toFixed(d));

/* ---------------- shared SVG: price ladder ---------------- */

export function Ladder({ spot, rungs, w, h }) {
  const prices = rungs.map((r) => r.price).concat([spot]);
  let lo = Math.min(...prices), hi = Math.max(...prices);
  const pad = (hi - lo) * 0.06 || 1; lo -= pad; hi += pad;
  const y = (p) => 14 + (1 - (p - lo) / (hi - lo)) * (h - 28);
  const X0 = 64, XMAX = w - 78;
  const sorted = [...rungs].sort((a, b) => b.price - a.price);
  let lastY = -99;
  const items = sorted.map((r, i) => {
    const yy = y(r.price);
    const len = 18 + (r.strength ?? 0.6) * (XMAX - X0 - 18);
    let ly = yy; if (ly - lastY < 13) ly = lastY + 13; lastY = ly;
    return (
      <g key={i}>
        <line x1={X0} x2={X0 + len} y1={yy} y2={yy} stroke={r.color}
          strokeWidth={r.major ? 3 : 1.6 + (r.strength ?? 0.5) * 1.6}
          strokeLinecap="round" strokeDasharray={r.dash ? "4 4" : "none"}
          opacity={r.major ? 1 : 0.5 + (r.strength ?? 0.5) * 0.5} />
        <text x={X0 - 8} y={ly + 3.5} textAnchor="end" fill="var(--muted)"
          fontSize="10.5" fontFamily="var(--mono)">{fmt(r.price)}</text>
        {r.label && (
          <text x={X0 + len + 8} y={yy + 3.5} fill={r.color} fontSize="10"
            letterSpacing=".06em">{r.label.toUpperCase()}</text>
        )}
      </g>
    );
  });
  const sy = y(spot);
  return (
    <svg className="ladder" viewBox={`0 0 ${w} ${h}`} role="img">
      {items}
      <line x1={10} x2={w - 10} y1={sy} y2={sy} stroke="var(--text)"
        strokeWidth={1} strokeDasharray="2 3" opacity={0.9} />
      <text x={w - 10} y={sy - 5} textAnchor="end" fill="var(--text)"
        fontSize="11" fontFamily="var(--mono)" fontWeight="500">
        spot {fmt(spot)}
      </text>
    </svg>
  );
}

/* ---------------- regime strip ---------------- */

export function RegimeStrip({ regime }) {
  const s = regime.risk_score;
  const pct = ((s + 10) / 20) * 100, mid = 50;
  return (
    <section className="regime" aria-label="Market regime">
      <div>
        <div className="eyebrow">Market regime</div>
        <div className={`verdict ${regime.regime}`}>{regime.regime.replace("_", "-")}</div>
        <div className="mods">
          {(regime.modifiers?.length ? regime.modifiers : ["no vol modifier"]).map((m) => (
            <span className="chip" key={m}>{m.replace("_", " ")}</span>
          ))}
        </div>
      </div>
      <div>
        <div className="eyebrow" style={{ marginBottom: 8 }}>Risk-on score</div>
        <div className="gaugerow">
          <div className="gauge" style={{ flex: 1 }}>
            <div className="zero" />
            <div className="fill" style={{
              left: `${Math.min(pct, mid)}%`, right: `${100 - Math.max(pct, mid)}%`,
              background: s >= 0 ? "var(--bull)" : "var(--bear)",
            }} />
            <div className="pin" style={{ left: `calc(${pct}% - 1px)` }} />
          </div>
          <div className="score num" style={{
            color: s >= 3 ? "var(--bull)" : s <= -3 ? "var(--bear)" : "var(--chop)",
          }}>{s > 0 ? "+" : ""}{fmt(s, 1)}</div>
        </div>
        <div className="scale"><span>−10 risk-off</span><span>0</span><span>+10 risk-on</span></div>
      </div>
      <div>
        <div className="eyebrow" style={{ marginBottom: 8 }}>Component contributions</div>
        <div className="comps">
          {regime.components.map((c) => {
            const w = Math.min((Math.abs(c.contribution) / 5) * 50, 50);
            const pos = c.contribution >= 0;
            return (
              <div className="comp" key={c.name}>
                <span>{c.name.replaceAll("_", " ")}</span>
                <span className="track">
                  <span className="mid" />
                  <i style={{
                    [pos ? "left" : "right"]: "50%", width: `${w}%`,
                    background: pos ? "var(--bull)" : "var(--bear)",
                  }} />
                </span>
                <span className="val num">{pos ? "+" : ""}{fmt(c.contribution, 1)}</span>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}

/* ---------------- VIX + index panels ---------------- */

const TONE = {
  confirming_bullish: "good", diverging_supportive: "good", neutral_chop: "flat",
  diverging_warning: "warn", confirming_bearish: "bad",
};

export function VixPanel({ vix }) {
  const L = vix.levels, A = vix.alignment;
  const rungs = [];
  const add = (p, label, color, major, dash) =>
    p != null && rungs.push({ price: p, label, color, strength: 0.95, major, dash });
  add(L.pivot, "pivot", "var(--gold)", true);
  add(L.upside_target_1, "upside t1", "var(--bear)", true, true);
  add(L.upside_target_2, "upside t2", "var(--bear)", true, true);
  add(L.downside_target_1, "downside t1", "var(--bull)", true, true);
  add(L.downside_target_2, "downside t2", "var(--bull)", true, true);
  for (const c of (L.clusters || []).slice(0, 8)) {
    if (rungs.some((r) => Math.abs(r.price - c.price) < 0.05)) continue;
    rungs.push({
      price: c.price, strength: c.strength,
      color: c.kind === "resistance" ? "var(--bear)" : c.kind === "support" ? "var(--bull)" : "var(--chop)",
    });
  }
  return (
    <article className="card" aria-label="VIX framework">
      <h2>VIX <span className="num">{fmt(L.spot)}</span></h2>
      <div>
        <span className={`state ${TONE[A.state] || "flat"}`}>{A.state.replaceAll("_", " ")}</span>
      </div>
      <Ladder spot={L.spot} rungs={rungs} w={360} h={330} />
      <dl className="kv">
        <dt>Spot vs pivot</dt><dd className="num">{L.spot_vs_pivot ?? "—"}</dd>
        <dt>Window</dt><dd className="num">{L.window_sessions} sessions</dd>
      </dl>
    </article>
  );
}

export function IndexPanel({ symbol, data }) {
  const L = data.levels;
  const aboveWp = L.spot > L.weekly.weekly_pivot;
  const rungs = [];
  const add = (p, label, color, major, dash) =>
    p != null && rungs.push({ price: p, label, color, strength: 0.95, major, dash });
  add(L.bullish_trigger, "bull trigger", "var(--gold)", true);
  add(L.bearish_trigger, "bear trigger", "var(--gold)", true);
  add(L.weekly.weekly_pivot, "wk pivot", "var(--chop)", true, true);
  add(L.weekly.weekly_ceiling, "wk ceiling", "var(--bear)", false, true);
  add(L.weekly.weekly_floor, "wk floor", "var(--bull)", false, true);
  for (const c of (L.fractal_clusters || []).filter((c) => c.strength > 0.25).slice(0, 10)) {
    if (rungs.some((r) => Math.abs(r.price - c.price) / c.price < 0.001)) continue;
    rungs.push({
      price: c.price, strength: c.strength,
      color: c.kind === "resistance" ? "var(--bear)" : c.kind === "support" ? "var(--bull)" : "var(--chop)",
    });
  }
  return (
    <article className="card" aria-label={`${symbol} levels`}>
      <h2>{symbol} <span className="num">{fmt(L.spot)}</span></h2>
      <div>
        <span className={`state ${aboveWp ? "good" : "bad"}`}>
          {aboveWp ? "above weekly pivot" : "below weekly pivot"}
        </span>{" "}
        <span className={`state ${L.rvol_20d >= 1.3 ? "warn" : "flat"}`}>
          RVOL {fmt(L.rvol_20d)}×
        </span>
      </div>
      <Ladder spot={L.spot} rungs={rungs} w={420} h={380} />
      <dl className="kv">
        <dt>High / low of day</dt>
        <dd className="num">{fmt(L.session.high_of_day)} / {fmt(L.session.low_of_day)}</dd>
        <dt>Outliers ▲ / ▼</dt>
        <dd className="num">{fmt(L.outliers.outlier_upside)} / {fmt(L.outliers.outlier_downside)}</dd>
      </dl>
    </article>
  );
}

/* ---------------- tape / options / rotation / setups / feed ---------------- */

const PHASE_TONE = {
  mark_up: "good", accumulation: "good", failed_breakdown: "good", consolidation: "flat",
  distribution: "bad", mark_down: "bad", exhaustion: "warn", failed_breakout: "warn",
};

export function TapePanel({ qqq, spy }) {
  const ph = qqq.phase, ev = ph.evidence;
  return (
    <article className="card" aria-label="Tape character">
      <h2>Tape character <span className="num">QQQ</span></h2>
      <span className={`state ${PHASE_TONE[ph.phase] || "flat"}`}>{ph.phase.replaceAll("_", " ")}</span>
      <dl className="kv">
        <dt>Trend slope</dt><dd className="num">{fmt(ev.trend_slope_pct_per_bar, 3)}%/bar</dd>
        <dt>Up/down volume (20d)</dt><dd className="num">{fmt(ev.updown_volume_ratio_20d)}</dd>
        <dt>Range position (60d)</dt><dd className="num">{fmt(ev.range_position_60d)}</dd>
      </dl>
      <div className="eyebrow section-gap">RSI stack</div>
      <div className="rsirow">
        {qqq.rsi.stack.map((s) => (
          <div className={`rsicell ${s.zone}`} key={s.timeframe}>
            <div className="tf">{s.timeframe}</div>
            <div className="v num">{fmt(s.rsi, 0)}</div>
            <div className="dir">{s.direction}</div>
          </div>
        ))}
      </div>
      <div className="eyebrow section-gap">SPY check</div>
      <dl className="kv">
        <dt>Spot</dt><dd className="num">{fmt(spy.levels.spot)}</dd>
        <dt>Phase</dt><dd className="num">{spy.phase.phase.replaceAll("_", " ")}</dd>
      </dl>
    </article>
  );
}

export function OptionsPanel({ gex }) {
  const rows = gex.profile.filter((r) => Math.abs(r.strike - gex.spot) / gex.spot <= 0.09);
  const W = 640, H = 300, L = 60, R = 20, T = 14, B = 18, cw = W - L - R, ch = H - T - B;
  const maxAbs = Math.max(...rows.map((r) => Math.abs(r["gex_$m"])), 1e-9);
  const bw = Math.max(Math.min(ch / rows.length - 3, 14), 4);
  const x0 = L + cw / 2;
  const y = (i) => T + (i + 0.5) * (ch / rows.length);
  const sx = (v) => x0 + (v / maxAbs) * (cw / 2 - 6);
  const yFor = (price) => {
    let best = 0, bd = 1e18;
    rows.forEach((r, i) => { const d = Math.abs(r.strike - price); if (d < bd) { bd = d; best = i; } });
    return y(best);
  };
  return (
    <article className="card" aria-label="Options positioning">
      <h2>Options positioning <span className="num">{gex.symbol} · net {gex["net_gex_$m"].toLocaleString()} $m / 1%</span></h2>
      <span className={`state ${gex.gamma_regime === "positive" ? "good" : "warn"}`}>
        {gex.gamma_regime} gamma — {gex.gamma_regime === "positive" ? "dealers dampen, walls pin" : "dealers amplify, breaks accelerate"}
      </span>
      <svg className="ladder" viewBox={`0 0 ${W} ${H}`} role="img">
        <line x1={x0} x2={x0} y1={T} y2={T + ch} stroke="var(--line)" strokeWidth={1} />
        {rows.map((r, i) => {
          const v = r["gex_$m"], xx = sx(v);
          return (
            <g key={r.strike}>
              <rect x={Math.min(x0, xx)} y={y(i) - bw / 2} rx={1.5}
                width={Math.max(Math.abs(xx - x0), 1)} height={bw}
                fill={v >= 0 ? "var(--bull)" : "var(--bear)"} opacity={0.8} />
              <text x={L - 8} y={y(i) + 3.5} textAnchor="end" fill="var(--muted)"
                fontSize="9.5" fontFamily="var(--mono)">{r.strike}</text>
            </g>
          );
        })}
        {gex.zero_gamma_flip != null && Math.abs(gex.zero_gamma_flip - gex.spot) / gex.spot <= 0.09 && (
          <line x1={L} x2={W - R} y1={yFor(gex.zero_gamma_flip)} y2={yFor(gex.zero_gamma_flip)}
            stroke="var(--gold)" strokeWidth={1} strokeDasharray="3 3" />
        )}
        <line x1={L} x2={W - R} y1={yFor(gex.spot)} y2={yFor(gex.spot)}
          stroke="var(--text)" strokeWidth={1} strokeDasharray="2 4" opacity={0.9} />
      </svg>
      <dl className="kv">
        <dt>Zero-gamma flip</dt><dd className="num">{fmt(gex.zero_gamma_flip)}</dd>
        <dt>Call wall</dt><dd className="num">{fmt(gex.call_wall)}</dd>
        <dt>Put wall</dt><dd className="num">{fmt(gex.put_wall)}</dd>
      </dl>
    </article>
  );
}

export function RotationTable({ rotation }) {
  const shown = rotation.etfs.filter((e) => e.status !== "neutral")
    .concat(rotation.etfs.filter((e) => e.status === "neutral")).slice(0, 14);
  const cell = (v) =>
    v == null ? <td>—</td> :
      <td className={v > 0 ? "pos" : v < 0 ? "neg" : ""}>{v > 0 ? "+" : ""}{v.toFixed(1)}</td>;
  return (
    <article className="card" aria-label="Sector rotation">
      <h2>Sector rotation</h2>
      <table className="rot">
        <thead><tr><th>ETF</th><th>Status</th><th>1w</th><th>4w</th><th>12w</th><th>RVOL</th></tr></thead>
        <tbody>
          {shown.map((e) => (
            <tr key={e.symbol}>
              <td className="num">{e.symbol}</td>
              <td><span className={`rotchip ${e.status}`}>{e.status}</span></td>
              {cell(e.relative_perf["1w"])}{cell(e.relative_perf["4w"])}{cell(e.relative_perf["12w"])}
              <td className="num">{e.rvol_20d == null ? "—" : `${e.rvol_20d.toFixed(2)}×`}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </article>
  );
}

function InstrumentLine({ setup }) {
  const s = setup.instrument_suggestion;
  if (!s) return null;
  if (s.instrument === "stock" || setup.instrument === "stock")
    return <div className="inst"><b>stock</b> — {s.reason || "options route unavailable"}</div>;
  const strikes = s.long_strike != null
    ? `${s.long_strike}${s.short_strike != null ? " / " + s.short_strike : ""}` : s.strike;
  return (
    <div className="inst">
      <b>{s.instrument.replaceAll("_", " ")}</b> · {strikes} · exp {s.expiry} ({s.dte}d)
      · OI {s.oi} · spread {(s.spread_pct * 100).toFixed(1)}%
    </div>
  );
}

export function SetupCards({ setups }) {
  if (setups.no_trade) {
    return (
      <article className="card" aria-label="Trade setups">
        <h2>Setups <span className="num">no-trade conditions</span></h2>
        <div className="notrade"><b>Standing aside.</b> {setups.reason}</div>
      </article>
    );
  }
  return (
    <article className="card" aria-label="Trade setups">
      <h2>Setups <span className="num">
        {setups.setups.length} active · {setups.direction} · {(setups.suppressed || []).length} suppressed
      </span>{setups.forced && <span className="state warn" style={{ marginLeft: 10 }}>FORCED — test mode, regime gate bypassed</span>}</h2>
      {setups.setups.map((x) => (
        <div className="setup" key={x.symbol}>
          <div className="head">
            <span className="sym num">{x.symbol}</span>
            <span className={`state ${x.direction === "long" ? "good" : "bad"}`}>{x.direction}</span>
            <span className={`rotchip ${x.sector_status}`}>{x.sector_etf} {x.sector_status}</span>
            {x.earnings_flag && <span className="state warn">earnings window</span>}
            <span className="conf num" style={{
              color: x.confidence >= 7.5 ? "var(--bull)" : x.confidence >= 6.5 ? "var(--gold)" : "var(--muted)",
            }}>{x.confidence.toFixed(1)}<span style={{ color: "var(--faint)", fontSize: 11 }}>/10</span></span>
          </div>
          <div className="lvls">
            {[["Entry", x.entry_trigger, "var(--gold)"], ["Stop", x.stop, "var(--bear)"],
              ["Target 1", x.target_1, "var(--bull)"], ["Target 2", x.target_2, "var(--bull)"]]
              .map(([label, v, color]) => (
                <div className="lvl" key={label}>
                  <div className="eyebrow">{label}</div>
                  <div className="v num" style={{ color }}>{fmt(v)}</div>
                </div>
              ))}
            <div className="lvl">
              <div className="eyebrow">R:R T1/T2</div>
              <div className="v num">{x.risk_reward_t1} / {x.risk_reward_t2}</div>
            </div>
          </div>
          <InstrumentLine setup={x} />
          <div className="thesis">{x.thesis}</div>
          {(x.risks || []).length > 0 && <div className="riskline">⚠ {x.risks.join(" · ")}</div>}
        </div>
      ))}
    </article>
  );
}

export function AlertFeed({ feed }) {
  return (
    <section className="card" style={{ marginTop: 18 }} aria-label="Alert feed">
      <h2>Alert feed <span className="num">{feed.label}</span></h2>
      <div className="feed">
        {feed.events.map((e, i) => (
          <div className="fevent" key={i}>
            <span className="t num">{(e.bar_time || "").slice(0, 10)}</span>
            <span className="num">{e.symbol}</span>
            <span><span className={`badge ${e.to_state}`}>{e.to_state.replaceAll("_", " ")}</span></span>
            <span className="why">{e.reason}</span>
            <span className="px num">{e.price == null ? "—" : Number(e.price).toFixed(2)}</span>
          </div>
        ))}
      </div>
    </section>
  );
}
