"use client";

// Phase 9 — the client-side <Refine> mount.
// Refine is headless: it contributes data fetching, caching, mutation
// invalidation, and the auth flow. Every pixel is the existing Confluence
// design system from globals.css.

import { Refine } from "@refinedev/core";
import routerProvider from "@refinedev/nextjs-router";
import Link from "next/link";

import { dataProvider, authProvider } from "../../lib/confluence";

export default function RefineShell({ children }) {
  return (
    <Refine
      dataProvider={dataProvider}
      authProvider={authProvider}
      routerProvider={routerProvider}
      resources={[
        { name: "trades", list: "/admin", meta: { label: "Trades" } },
        { name: "watchlist", list: "/admin/watchlist", meta: { label: "Watchlist" } },
        { name: "events", list: "/admin", meta: { label: "Events" } },
      ]}
      options={{ disableTelemetry: true, warnWhenUnsavedChanges: true }}
    >
      <div className="wrap" style={{ paddingTop: 20 }}>
        <header style={{ display: "flex", gap: 16, alignItems: "baseline" }}>
          <div className="mark">
            CONFLUENCE<b>.</b>
          </div>
          <nav style={{ display: "flex", gap: 14, marginLeft: 8 }}>
            <Link href="/admin">Trades</Link>
            <Link href="/admin/watchlist">Watchlist</Link>
            <Link href="/">← Dashboard</Link>
          </nav>
        </header>
        <div style={{ paddingTop: 18 }}>{children}</div>
      </div>
    </Refine>
  );
}
