"use client";
/**
 * Trades resource — Refine's headless useTable over the lifecycle store.
 * Pagination, sorting, filtering, and cache invalidation come from the
 * framework; the markup is plain Confluence design-system classes.
 */

import { useState } from "react";
import { useTable, useUpdate, Authenticated } from "@refinedev/core";

const STATE_CLASS = {
  WATCHING: "flat", TRIGGERED: "warn", ACTIVE: "good", TRAILING: "good",
  CLOSED: "flat", STOPPED: "bad", INVALIDATED: "bad", DETERIORATED: "bad",
};
const num = (v, d = 2) => (v == null ? "—" : Number(v).toFixed(d));

function Row({ t }) {
  const { mutate, mutation } = useUpdate();
  const close = () =>
    mutate({
      resource: "trades",
      id: t.id,
      values: { state: "CLOSED", note: "manual close from /admin" },
    });
  const terminal = ["CLOSED", "STOPPED", "INVALIDATED", "DETERIORATED"]
    .includes(t.state);
  return (
    <tr>
      <td className="num">{t.symbol}</td>
      <td>{t.direction}</td>
      <td><span className={`state ${STATE_CLASS[t.state] || "flat"}`}>{t.state}</span></td>
      <td className="num">{num(t.entry_trigger)}</td>
      <td className="num">{num(t.stop)}</td>
      <td className="num">{num(t.target_1)} / {num(t.target_2)}</td>
      <td className="num">{num(t.setup_meta?.confidence, 0)}</td>
      <td>
        {!terminal && (
          <button className="chip" onClick={close} disabled={mutation.isPending}>
            {mutation.isPending ? "closing…" : "close"}
          </button>
        )}
      </td>
    </tr>
  );
}

function TradesTable() {
  const [stateFilter, setStateFilter] = useState("");
  const { result, tableQuery, currentPage, setCurrentPage, pageCount, setFilters,
          setSorters } = useTable({
    resource: "trades",
    pagination: { pageSize: 15 },
    sorters: { initial: [{ field: "updated_at", order: "desc" }] },
  });

  const rows = result?.data ?? [];
  const total = result?.total ?? 0;

  const filterBy = (s) => {
    setStateFilter(s);
    setFilters(s ? [{ field: "state", operator: "eq", value: s }] : [], "replace");
  };

  return (
    <div className="card" style={{ marginTop: 20 }}>
      <h2>Trades <span className="num">{total}</span></h2>
      <div className="legend" style={{ marginTop: 8 }}>
        {["", "WATCHING", "TRIGGERED", "ACTIVE", "CLOSED", "STOPPED"].map((s) => (
          <button key={s || "all"} className="chip" onClick={() => filterBy(s)}
            style={s === stateFilter ? { color: "var(--gold)", borderColor: "#3a3424" } : {}}>
            {s || "all"}
          </button>
        ))}
        <button className="chip" onClick={() => setSorters([{ field: "symbol", order: "asc" }])}>
          sort: symbol
        </button>
      </div>

      {tableQuery.isLoading ? (
        <div className="empty">loading…</div>
      ) : rows.length === 0 ? (
        <div className="empty">
          No trades. Arm the game plan from the dashboard, then reload.
        </div>
      ) : (
        <table style={{ width: "100%", marginTop: 12, borderCollapse: "collapse", fontSize: 12.5 }}>
          <thead>
            <tr className="eyebrow" style={{ textAlign: "left" }}>
              <th>sym</th><th>dir</th><th>state</th><th>entry</th>
              <th>stop</th><th>targets</th><th>conf</th><th></th>
            </tr>
          </thead>
          <tbody>{rows.map((t) => <Row key={t.id} t={t} />)}</tbody>
        </table>
      )}

      {pageCount > 1 && (
        <div className="legend" style={{ marginTop: 12 }}>
          <button className="chip" disabled={currentPage <= 1}
            onClick={() => setCurrentPage(currentPage - 1)}>prev</button>
          <span className="num">{currentPage} / {pageCount}</span>
          <button className="chip" disabled={currentPage >= pageCount}
            onClick={() => setCurrentPage(currentPage + 1)}>next</button>
        </div>
      )}
    </div>
  );
}

export default function TradesPage() {
  return (
    <Authenticated key="trades">
      <TradesTable />
    </Authenticated>
  );
}
