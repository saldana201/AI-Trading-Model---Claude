"use client";
/**
 * Watchlist resource — sector ETF -> pinned tickers, full CRUD.
 * Edits land in watchlist.json and take effect on the next snapshot rebuild;
 * the note from the API is surfaced verbatim so that's never a surprise.
 */

import { useState } from "react";
import { useList, useCreate, useUpdate, useDelete, Authenticated }
  from "@refinedev/core";

function EntryRow({ row }) {
  const { mutate: update, mutation: upd } = useUpdate();
  const { mutate: remove, mutation: del } = useDelete();
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(row.tickers.join(", "));

  const save = () =>
    update(
      { resource: "watchlist", id: row.id,
        values: { tickers: text.split(",").map((s) => s.trim()).filter(Boolean) } },
      { onSuccess: () => setEditing(false) },
    );

  return (
    <tr>
      <td className="num" style={{ color: "var(--gold)" }}>{row.sector_etf}</td>
      <td>
        {editing ? (
          <input value={text} onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && save()}
            style={{ width: "100%", background: "var(--panel2)",
                     border: "1px solid var(--line)", borderRadius: 6,
                     color: "var(--text)", padding: "3px 8px",
                     fontFamily: "var(--mono)", fontSize: 12 }} />
        ) : (
          <span className="num">{row.tickers.join(" · ")}</span>
        )}
      </td>
      <td className="num" style={{ textAlign: "right" }}>{row.ticker_count}</td>
      <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
        {editing ? (
          <>
            <button className="chip" onClick={save} disabled={upd.isPending}>
              {upd.isPending ? "saving…" : "save"}
            </button>{" "}
            <button className="chip" onClick={() => setEditing(false)}>cancel</button>
          </>
        ) : (
          <>
            <button className="chip" onClick={() => setEditing(true)}>edit</button>{" "}
            <button className="chip" disabled={del.isPending}
              onClick={() => remove({ resource: "watchlist", id: row.id })}>
              {del.isPending ? "…" : "remove"}
            </button>
          </>
        )}
      </td>
    </tr>
  );
}

function WatchlistPanel() {
  const { result, query } = useList({
    resource: "watchlist",
    pagination: { mode: "off" },
    sorters: [{ field: "sector_etf", order: "asc" }],
  });
  const { mutate: create, mutation: cr } = useCreate();
  const [etf, setEtf] = useState("");
  const [tickers, setTickers] = useState("");

  const add = () =>
    create(
      { resource: "watchlist",
        values: { sector_etf: etf,
                  tickers: tickers.split(",").map((s) => s.trim()).filter(Boolean) } },
      { onSuccess: () => { setEtf(""); setTickers(""); } },
    );

  const inputStyle = {
    background: "var(--panel2)", border: "1px solid var(--line)",
    borderRadius: 6, color: "var(--text)", padding: "4px 8px",
    fontFamily: "var(--mono)", fontSize: 12,
  };

  return (
    <div className="card" style={{ marginTop: 20 }}>
      <h2>Pinned watchlist <span className="num">{result?.total ?? 0} sectors</span></h2>
      <div className="sub" style={{ marginTop: 4 }}>
        Custom entries replace that sector&apos;s defaults. Changes apply on the
        next snapshot rebuild — pinned names still pass the quality gates.
      </div>

      {query.isLoading ? (
        <div className="empty">loading…</div>
      ) : (
        <table style={{ width: "100%", marginTop: 12, borderCollapse: "collapse", fontSize: 12.5 }}>
          <thead>
            <tr className="eyebrow" style={{ textAlign: "left" }}>
              <th>sector etf</th><th>tickers</th>
              <th style={{ textAlign: "right" }}>#</th><th></th>
            </tr>
          </thead>
          <tbody>
            {(result?.data ?? []).map((row) => <EntryRow key={row.id} row={row} />)}
          </tbody>
        </table>
      )}

      <div className="section-gap" style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <input placeholder="ETF (e.g. XBI)" value={etf} style={{ ...inputStyle, width: 110 }}
          onChange={(e) => setEtf(e.target.value)} />
        <input placeholder="tickers, comma-separated" value={tickers}
          style={{ ...inputStyle, flex: 1, minWidth: 200 }}
          onChange={(e) => setTickers(e.target.value)} />
        <button className="chip" onClick={add}
          disabled={cr.isPending || !etf || !tickers}>
          {cr.isPending ? "adding…" : "add sector"}
        </button>
      </div>
    </div>
  );
}

export default function WatchlistPage() {
  return (
    <Authenticated key="watchlist">
      <WatchlistPanel />
    </Authenticated>
  );
}
