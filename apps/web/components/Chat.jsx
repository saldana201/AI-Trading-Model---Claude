"use client";

import { useRef, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function Chat() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const boxRef = useRef(null);

  async function send(e) {
    e?.preventDefault();
    const text = input.trim();
    if (!text || busy) return;
    setInput("");
    const next = [...messages, { role: "user", text }];
    setMessages(next);
    setBusy(true);
    try {
      const r = await fetch(`${API}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text }),
      });
      const data = await r.json();
      setMessages([...next, { role: "assistant", text: data.reply, mode: data.mode }]);
    } catch {
      setMessages([...next, {
        role: "assistant",
        text: "API unreachable — start it with: uvicorn apps.api.main:app --port 8000",
      }]);
    } finally {
      setBusy(false);
      queueMicrotask(() => boxRef.current?.scrollTo(0, 1e9));
    }
  }

  const suggestions = [
    "What is the market regime today?",
    "Key QQQ and SPY levels",
    "Calls, puts, or no trade?",
    "Which sectors are leading?",
  ];

  return (
    <section className="card" style={{ marginTop: 18 }} aria-label="Chat">
      <h2>Ask Confluence</h2>
      <div ref={boxRef} className="chatbox">
        {messages.length === 0 && (
          <div className="empty">
            Ask about the regime, levels, sectors, setups, extension, gamma…
            <div className="sugg">
              {suggestions.map((s) => (
                <button key={s} className="chip" type="button"
                  onClick={() => { setInput(s); }}>{s}</button>
              ))}
            </div>
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`msg ${m.role}`}>
            <span className="who">{m.role === "user" ? "you" : `confluence${m.mode === "deterministic" ? " · deterministic" : ""}`}</span>
            <p>{m.text}</p>
          </div>
        ))}
        {busy && <div className="msg assistant"><span className="who">confluence</span><p>…</p></div>}
      </div>
      <form className="chatrow" onSubmit={send}>
        <input value={input} onChange={(e) => setInput(e.target.value)}
          placeholder="What level invalidates the NVDA trade?" aria-label="Message" />
        <button type="submit" disabled={busy}>Send</button>
      </form>
    </section>
  );
}
