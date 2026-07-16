"use client";
/**
 * /admin/login — enter the gateway API key once.
 * The key is verified against a real resource call before being kept.
 * If the gateway runs with auth disabled (dev), check() waves you through
 * and you'll never see this page.
 */

import { useState } from "react";
import { useLogin } from "@refinedev/core";

export default function LoginPage() {
  const { mutate: login, mutation } = useLogin();
  const [apiKey, setApiKey] = useState("");
  const [error, setError] = useState("");

  const submit = () =>
    login({ apiKey }, {
      onSuccess: (data) => {
        if (data?.success === false)
          setError(data?.error?.message || "The gateway rejected this key.");
      },
    });

  return (
    <div className="card" style={{ maxWidth: 420, margin: "60px auto" }}>
      <h2>Operator access</h2>
      <div className="sub" style={{ marginTop: 6 }}>
        Enter the gateway API key (the CONFLUENCE_API_KEY value the server
        was started with).
      </div>
      <input
        type="password"
        placeholder="API key"
        value={apiKey}
        autoFocus
        onChange={(e) => { setApiKey(e.target.value); setError(""); }}
        onKeyDown={(e) => e.key === "Enter" && apiKey && submit()}
        style={{
          width: "100%", marginTop: 14, background: "var(--panel2)",
          border: "1px solid var(--line)", borderRadius: 8,
          color: "var(--text)", padding: "8px 10px",
          fontFamily: "var(--mono)", fontSize: 13,
        }}
      />
      {error && (
        <div className="state bad" style={{ marginTop: 10 }}>{error}</div>
      )}
      <button
        className="chip"
        onClick={submit}
        disabled={!apiKey || mutation.isPending}
        style={{ marginTop: 14, padding: "6px 16px", cursor: "pointer" }}
      >
        {mutation.isPending ? "checking…" : "Unlock"}
      </button>
    </div>
  );
}
