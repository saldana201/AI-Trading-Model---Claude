"use client";
/**
 * /admin — the Refine-powered operations surface.
 *
 * Refine (refine.dev) is headless: it contributes data fetching, caching,
 * mutations, and auth flow via hooks; every pixel below stays on the
 * Confluence design system in globals.css. The main dashboard at / is
 * untouched — this mounts only under /admin.
 */

import Link from "next/link";
import { Refine } from "@refinedev/core";
import routerProvider from "@refinedev/nextjs-router";
import { dataProvider, authProvider } from "../../lib/confluence";

export default function RefineShell({ children }) {
  return (
    <Refine
      dataProvider={dataProvider}
      authProvider={authProvider}
      routerProvider={routerProvider}
      resources={[
        { name: "trades", list: "/admin", show: "/admin/trades/:id" },
        { name: "watchlist", list: "/admin/watchlist", meta: { label: "Watchlist" } },
        { name: "events", list: "/admin/events" },
      ]}
      options={{ syncWithLocation: true, disableTelemetry: true }}
    >
      <div className="wrap">
        <header>
          <div className="mark">CONFLUENCE<b>.</b></div>
          <div className="sub">operations · trades / watchlist / audit</div>
          <div className="meta">
            <Link className="chip" href="/">dashboard</Link>
            <Link className="chip" href="/admin">trades</Link>
            <Link className="chip" href="/admin/watchlist">watchlist</Link>
          </div>
        </header>
        {children}
      </div>
    </Refine>
  );
}
