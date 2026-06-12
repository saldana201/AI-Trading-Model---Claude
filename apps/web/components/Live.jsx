"use client";

// Live components (Phase 7): an EventSource on /api/stream drives the ticker
// and the live alert feed; polling /api/quotes is the fallback when SSE is
// unavailable. SnapshotRefresher re-renders the server page on an interval.

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/* ---------------- shared SSE hook ---------------- */

function useStream(onQuote, onAlert) {
  const [status, setStatus] = useState("connecting");
  useEffect(() => {
    let es, pollTimer, dead = false;

    const startPolling = () => {
      setStatus("polling");
      const poll = async () => {
        try {
          const r = await fetch(`${API}/api/quotes`);
          onQuote?.(await r.json());
          setStatus("polling");
        } catch {
          setStatus("offline");
        }
      };
      poll();
      pollTimer = setInterval(poll, 20000);
    };

    try {
      es = new EventSource(`${API}/api/stream`);
      es.addEventListener("hello", () => setStatus("live"));
      es.addEventListener("quote", (e) => onQuote?.(JSON.parse(e.data)));
      es.addEventListener("alert", (e) => onAlert?.(JSON.parse(e.data)));
      es.onerror = () => {
        if (dead) return;
        setStatus("reconnecting");
        // EventSource retries on its own; fall back to polling if it never lands
        setTimeout(() => {
          if (!dead && es.readyState === EventSource.CLOSED) {
            es.close();
            startPolling();
          }
        }, 8000);
      };
    } catch {
      startPolling();
    }
    return () => { dead = true; es?.close(); clearInterval(pollTimer); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return status;
}

/* ---------------- ticker strip ---------------- */

export function LiveTicker() {
  const [quotes, setQuotes] = useState({});
  const status = useStream((payload) => {
    setQuotes((q) => ({ ...q, ...payload.quotes }));
  });
  const syms = Object.keys(quotes);
  return (
    <div className="ticker" aria-label="Live quotes">
      <span className={`livedot ${status}`} title={status} />
      <span className="eyebrow">{status}</span>
      {syms.length === 0 && <span className="empty">waiting for quotes…</span>}
      {syms.map((s) => {
        const q = quotes[s];
        const up = q.change_pct >= 0;
        return (
          <span className="tick num" key={s}>
            <b>{s}</b> {q.spot.toFixed(2)}
            <i style={{ color: up ? "var(--bull)" : "var(--bear)" }}>
              {up ? "+" : ""}{q.change_pct.toFixed(2)}%
            </i>
          </span>
        );
      })}
    </div>
  );
}

/* ---------------- live alert feed ---------------- */

export function LiveFeed({ initial }) {
  const [events, setEvents] = useState(initial?.events || []);
  const [liveCount, setLiveCount] = useState(0);
  useStream(null, (ev) => {
    setEvents((prev) => [...prev, { ...ev, live: true }]);
    setLiveCount((n) => n + 1);
  });
  return (
    <section className="card" style={{ marginTop: 18 }} aria-label="Alert feed">
      <h2>
        Alert feed{" "}
        <span className="num">
          {liveCount > 0 ? `${liveCount} live · ` : ""}{initial?.label || ""}
        </span>
      </h2>
      <div className="feed">
        {events.map((e, i) => (
          <div className={`fevent${e.live ? " liverow" : ""}`} key={i}>
            <span className="t num">{(e.bar_time || "").slice(0, 10)}</span>
            <span className="num">{e.symbol}</span>
            <span><span className={`badge ${e.to_state}`}>{(e.to_state || "").replaceAll("_", " ")}</span></span>
            <span className="why">{e.reason}</span>
            <span className="px num">{e.price == null ? "—" : Number(e.price).toFixed(2)}</span>
          </div>
        ))}
      </div>
    </section>
  );
}

/* ---------------- arm button ---------------- */

export function ArmButton() {
  const [state, setState] = useState({ phase: "idle" });
  async function arm() {
    setState({ phase: "arming" });
    try {
      const r = await fetch(`${API}/api/alerts/arm`, { method: "POST" });
      const data = await r.json();
      setState({ phase: "armed", n: data.armed });
    } catch {
      setState({ phase: "error" });
    }
  }
  return (
    <div className="armrow">
      <button className="armbtn" onClick={arm} disabled={state.phase === "arming"}>
        {state.phase === "arming" ? "Arming…" : "Arm game plan"}
      </button>
      {state.phase === "armed" && (
        <span className="state good">{state.n} setup{state.n === 1 ? "" : "s"} armed — alerts will stream here</span>
      )}
      {state.phase === "error" && <span className="state bad">API unreachable</span>}
    </div>
  );
}

/* ---------------- snapshot auto-refresh ---------------- */

export function SnapshotRefresher({ intervalMs = 120000 }) {
  const router = useRouter();
  const [last, setLast] = useState(null);
  const busy = useRef(false);
  async function refresh(force) {
    if (busy.current) return;
    busy.current = true;
    try {
      if (force) await fetch(`${API}/api/snapshot?refresh=1`);
      router.refresh();
      setLast(new Date());
    } finally {
      busy.current = false;
    }
  }
  useEffect(() => {
    const t = setInterval(() => refresh(false), intervalMs);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [intervalMs]);
  return (
    <span className="refresher">
      <button className="chip" type="button" onClick={() => refresh(true)}>↻ refresh</button>
      {last && <span className="num" style={{ fontSize: 11, color: "var(--faint)" }}>
        {last.toLocaleTimeString()}
      </span>}
    </span>
  );
}
