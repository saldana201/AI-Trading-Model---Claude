"use client";

// Phase 9 — trades table. Uses Refine v5 hook shapes (`result`, `tableQuery`,
// `currentPage`, `mutation.isPending`); don't mix in v4-era snippets.

import { useTable, useUpdate } from "@refinedev/core";
import { useState } from "react";

const TERMINAL = ["CLOSED", "STOPPED", "INVALIDATED", "DETERIORATED"];

export default function TradesPage() {
  const { result, tableQuery, currentPage, setCurrentPage, pageSize } =
    useTable({ resource: "trades", pagination: { pageSize: 25 } });
  const { mutate, mutation } = useUpdate();
  const [note, setNote] = useState({});

  const rows = result?.data ?? [];
  const total = result?.total ?? 0;

  if (tableQuery?.isLoading) return <p>Loading trades…</p>;
  if (tableQuery?.isError)
    return <p style={{ color: "var(--bear)" }}>{String(tableQuery.error?.message)}</p>;

  const close = (row, state) =>
    mutate({
      resource: "trades",
      id: row.id,
      values: { state, note: note[row.id] || "closed from admin" },
    });

  return (
    <div>
      <div className="eyebrow">Trades · {total} total</div>
      <table style={{ width: "100%", borderCollapse: "collapse", marginTop: 12 }}>
        <thead>
          <tr style={{ textAlign: "left", color: "var(--muted)", fontSize: 12 }}>
            <th style={th}>Symbol</th><th style={th}>Dir</th><th style={th}>State</th>
            <th style={th}>Entry</th><th style={th}>Stop</th><th style={th}>T1</th>
            <th style={th}>Manual close</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => {
            const done = TERMINAL.includes(r.state);
            return (
              <tr key={r.id} style={{ borderTop: "1px solid var(--line)" }}>
                <td style={td}><b className="num">{r.symbol}</b></td>
                <td style={td}>{r.direction}</td>
                <td style={td}>{r.state}</td>
                <td style={{ ...td }} className="num">{r.entry_trigger}</td>
                <td style={{ ...td }} className="num">{r.stop}</td>
                <td style={{ ...td }} className="num">{r.target_1}</td>
                <td style={td}>
                  {done ? (
                    <span style={{ color: "var(--faint)" }}>—</span>
                  ) : (
                    <span style={{ display: "flex", gap: 6 }}>
                      <input
                        style={input}
                        placeholder="note"
                        value={note[r.id] || ""}
                        onChange={(e) =>
                          setNote((n) => ({ ...n, [r.id]: e.target.value }))
                        }
                      />
                      <button
                        style={btn}
                        disabled={mutation?.isPending}
                        onClick={() => close(r, "CLOSED")}
                      >
                        close
                      </button>
                    </span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      <div style={{ display: "flex", gap: 10, marginTop: 14, alignItems: "center" }}>
        <button style={btn} disabled={currentPage <= 1}
                onClick={() => setCurrentPage(currentPage - 1)}>prev</button>
        <span style={{ color: "var(--muted)", fontSize: 12 }}>
          page {currentPage} of {Math.max(1, Math.ceil(total / pageSize))}
        </span>
        <button style={btn} disabled={currentPage * pageSize >= total}
                onClick={() => setCurrentPage(currentPage + 1)}>next</button>
      </div>

      <p style={{ color: "var(--faint)", fontSize: 11.5, marginTop: 14 }}>
        Only terminal states can be set here — lifecycle transitions stay
        engine-owned, and every manual change writes a <code>manual_update</code>
        audit event.
      </p>
    </div>
  );
}

const th = { padding: "6px 8px", fontWeight: 600 };
const td = { padding: "7px 8px", fontSize: 13 };
const input = {
  background: "var(--panel2)", border: "1px solid var(--line)", borderRadius: 6,
  color: "var(--text)", padding: "4px 8px", fontSize: 12, width: 130,
};
const btn = {
  background: "transparent", border: "1px solid var(--line)", borderRadius: 6,
  color: "var(--text)", padding: "4px 10px", fontSize: 12, cursor: "pointer",
};
