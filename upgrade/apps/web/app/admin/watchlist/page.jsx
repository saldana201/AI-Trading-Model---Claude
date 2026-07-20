"use client";

// Phase 9 — watchlist CRUD. Edits apply on the next snapshot rebuild;
// the API says so and so does the UI.

import { useList, useCreate, useUpdate, useDelete } from "@refinedev/core";
import { useState } from "react";

export default function WatchlistPage() {
  const { result, query } = useList({
    resource: "watchlist",
    pagination: { mode: "off" },
  });
  const { mutate: create } = useCreate();
  const { mutate: update } = useUpdate();
  const { mutate: remove } = useDelete();

  const [draft, setDraft] = useState({});
  const [newRow, setNewRow] = useState({ id: "", symbols: "" });

  const rows = result?.data ?? [];
  if (query?.isLoading) return <p>Loading watchlist…</p>;
  if (query?.isError)
    return <p style={{ color: "var(--bear)" }}>{String(query.error?.message)}</p>;

  const parse = (s) => s.split(/[,\s]+/).filter(Boolean);

  return (
    <div>
      <div className="eyebrow">Watchlist · applies on next snapshot rebuild</div>

      <table style={{ width: "100%", borderCollapse: "collapse", marginTop: 12 }}>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id} style={{ borderTop: "1px solid var(--line)" }}>
              <td style={{ ...td, width: 120 }}>
                <b className="num">{r.id}</b>
                {r.pinned && (
                  <span style={{ color: "var(--gold)", fontSize: 10, marginLeft: 6 }}>
                    pinned
                  </span>
                )}
              </td>
              <td style={td}>
                <input
                  style={{ ...input, width: "100%" }}
                  value={draft[r.id] ?? r.symbols.join(", ")}
                  onChange={(e) =>
                    setDraft((d) => ({ ...d, [r.id]: e.target.value }))
                  }
                />
              </td>
              <td style={{ ...td, width: 150 }}>
                <button
                  style={btn}
                  onClick={() =>
                    update({
                      resource: "watchlist",
                      id: r.id,
                      values: { symbols: parse(draft[r.id] ?? r.symbols.join(",")) },
                    })
                  }
                >
                  save
                </button>{" "}
                {!r.pinned && (
                  <button
                    style={btn}
                    onClick={() => remove({ resource: "watchlist", id: r.id })}
                  >
                    delete
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <div style={{ display: "flex", gap: 8, marginTop: 16 }}>
        <input
          style={{ ...input, width: 110 }}
          placeholder="sector ETF"
          value={newRow.id}
          onChange={(e) => setNewRow({ ...newRow, id: e.target.value })}
        />
        <input
          style={{ ...input, flex: 1 }}
          placeholder="NVDA, AVGO, AMD"
          value={newRow.symbols}
          onChange={(e) => setNewRow({ ...newRow, symbols: e.target.value })}
        />
        <button
          style={btn}
          onClick={() => {
            create({
              resource: "watchlist",
              values: { id: newRow.id, symbols: parse(newRow.symbols) },
            });
            setNewRow({ id: "", symbols: "" });
          }}
        >
          add sector
        </button>
      </div>
    </div>
  );
}

const td = { padding: "7px 8px", fontSize: 13 };
const input = {
  background: "var(--panel2)", border: "1px solid var(--line)", borderRadius: 6,
  color: "var(--text)", padding: "5px 9px", fontSize: 12.5,
};
const btn = {
  background: "transparent", border: "1px solid var(--line)", borderRadius: 6,
  color: "var(--text)", padding: "5px 11px", fontSize: 12, cursor: "pointer",
};
