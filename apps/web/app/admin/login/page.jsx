"use client";

// Phase 9 — API key entry. The key is verified against a real resource call,
// then kept in localStorage and sent as X-API-Key. If the gateway reports
// auth disabled, the auth provider skips this page entirely.

import { useLogin } from "@refinedev/core";
import { useState } from "react";

export default function LoginPage() {
  const { mutate: login, mutation } = useLogin();
  const [apiKey, setApiKey] = useState("");

  return (
    <div style={{ maxWidth: 380, marginTop: 40 }}>
      <div className="eyebrow">Admin access</div>
      <p style={{ color: "var(--muted)", fontSize: 13, margin: "10px 0 14px" }}>
        Enter the value of <code>CONFLUENCE_API_KEY</code> from the gateway.
      </p>
      <input
        style={input}
        type="password"
        placeholder="API key"
        value={apiKey}
        onChange={(e) => setApiKey(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && login({ apiKey })}
      />
      <button
        style={{ ...btn, marginTop: 12 }}
        disabled={!apiKey || mutation?.isPending}
        onClick={() => login({ apiKey })}
      >
        {mutation?.isPending ? "checking…" : "sign in"}
      </button>
      {mutation?.data?.success === false && (
        <p style={{ color: "var(--bear)", fontSize: 12.5, marginTop: 10 }}>
          {mutation.data.error?.message}
        </p>
      )}
    </div>
  );
}

const input = {
  background: "var(--panel2)", border: "1px solid var(--line)", borderRadius: 6,
  color: "var(--text)", padding: "9px 11px", fontSize: 13, width: "100%",
};
const btn = {
  background: "var(--gold)", color: "#1a1508", border: "none", borderRadius: 6,
  padding: "8px 18px", fontWeight: 600, cursor: "pointer",
};
