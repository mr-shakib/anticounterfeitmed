"use client";

import { useCallback, useEffect, useState } from "react";
import { ActionDialog } from "@/components/Dialog";
import { Feedback, useAction } from "@/components/Feedback";
import { ApiError, BatchUnits, Unit, api } from "@/lib/api";

const PAGE_SIZE = 50;

const LIFECYCLES = [
  ["", "All states"],
  ["CREATED", "Created"],
  ["PRINTED", "Printed"],
  ["QC_PASSED", "QC passed"],
  ["COVERED", "Coated"],
  ["ACTIVE", "Active"],
  ["REDEEMED", "Redeemed"],
  ["VOID", "Void"],
] as const;

function lifecycleTone(lifecycle: string) {
  if (lifecycle === "ACTIVE") return "ok";
  if (lifecycle === "REDEEMED") return "warn";
  if (lifecycle === "VOID") return "danger";
  return "";
}

/**
 * Every unit of the batch, searchable by the reference printed on the strip.
 *
 * The old list stopped at the first fifty, so a unit further down could not be
 * found to block it. Search and paging run on the server.
 */
export function UnitsPanel({
  batchId,
  onChanged,
}: {
  batchId: string;
  onChanged: () => Promise<void>;
}) {
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState("");
  const [lifecycle, setLifecycle] = useState("");
  const [blockedOnly, setBlockedOnly] = useState(false);
  const [offset, setOffset] = useState(0);
  const [units, setUnits] = useState<Unit[]>([]);
  const [matching, setMatching] = useState(0);
  const [loadError, setLoadError] = useState("");
  const [blocking, setBlocking] = useState<Unit | null>(null);
  const [reason, setReason] = useState("");
  const [notice, setNotice] = useState("");
  const dialog = useAction();

  const load = useCallback(async () => {
    const params = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(offset) });
    if (search) params.set("q", search);
    if (lifecycle) params.set("lifecycle", lifecycle);
    if (blockedOnly) params.set("blocked", "true");
    try {
      const data = await api.get<BatchUnits>(`/v1/staff/batches/${batchId}/units?${params}`);
      setUnits(data.units);
      setMatching(data.units_matching);
      setLoadError("");
    } catch (e) {
      setLoadError(e instanceof ApiError ? e.message : "Could not load the units.");
    }
  }, [batchId, search, lifecycle, blockedOnly, offset]);

  // Mounted only while its tab is open, so it loads fresh each time it is shown.
  useEffect(() => { void load(); }, [load]);

  const block = () =>
    dialog.run(async () => {
      if (!blocking) return;
      await api.post(`/v1/staff/units/${blocking.id}/block`, { reason });
      setBlocking(null);
      setReason("");
      await Promise.all([load(), onChanged()]);
      setNotice(`${blocking.external_reference} blocked.`);
    });

  const first = matching === 0 ? 0 : offset + 1;
  const last = Math.min(offset + PAGE_SIZE, matching);

  return (
    <div className="card">
      <h2>Units</h2>
      <form
        className="row"
        onSubmit={(event) => {
          event.preventDefault();
          setOffset(0);
          setSearch(query.trim());
        }}
      >
        <label>
          <span>Find by reference</span>
          <input
            type="search"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              if (!e.target.value) {
                setOffset(0);
                setSearch("");
              }
            }}
            placeholder="e.g. 000123"
            spellCheck={false}
          />
        </label>
        <label style={{ maxWidth: 200 }}>
          <span>State</span>
          <select
            value={lifecycle}
            onChange={(e) => {
              setOffset(0);
              setLifecycle(e.target.value);
            }}
          >
            {LIFECYCLES.map(([value, label]) => (
              <option key={value} value={value}>{label}</option>
            ))}
          </select>
        </label>
        <label className="shrink checkbox">
          <input
            type="checkbox"
            checked={blockedOnly}
            onChange={(e) => {
              setOffset(0);
              setBlockedOnly(e.target.checked);
            }}
          />
          Blocked only
        </label>
        <div className="shrink">
          <button type="submit" className="secondary">Search</button>
        </div>
      </form>

      <Feedback error={loadError} notice={notice} />

      <table style={{ marginTop: "1rem" }}>
        <thead>
          <tr><th>Reference</th><th>State</th><th>Activated</th><th>Verified</th><th></th></tr>
        </thead>
        <tbody>
          {units.map((u) => (
            <tr key={u.id}>
              <td className="mono">{u.external_reference}</td>
              <td>
                <span className={`badge ${lifecycleTone(u.lifecycle)}`}>
                  {u.lifecycle.replace(/_/g, " ").toLowerCase()}
                </span>{" "}
                {u.is_blocked && (
                  <span className="badge danger" title={u.blocked_reason}>blocked</span>
                )}
              </td>
              <td className="muted">{u.activated_at?.slice(0, 10) ?? "—"}</td>
              <td className="muted">{u.redeemed_at?.slice(0, 10) ?? "—"}</td>
              <td>
                {!u.is_blocked && u.lifecycle !== "VOID" && (
                  <button
                    className="danger"
                    onClick={() => {
                      dialog.clear();
                      setNotice("");
                      setReason("");
                      setBlocking(u);
                    }}
                  >
                    Block…
                  </button>
                )}
              </td>
            </tr>
          ))}
          {units.length === 0 && (
            <tr>
              <td colSpan={5} className="muted">
                {search || lifecycle || blockedOnly ? "No units match." : "No units yet."}
              </td>
            </tr>
          )}
        </tbody>
      </table>

      {matching > 0 && (
        <div className="pager">
          <span className="muted">
            {first}–{last} of {matching}
          </span>
          <button
            className="secondary"
            onClick={() => setOffset(Math.max(offset - PAGE_SIZE, 0))}
            disabled={offset === 0}
          >
            Previous
          </button>
          <button
            className="secondary"
            onClick={() => setOffset(offset + PAGE_SIZE)}
            disabled={last >= matching}
          >
            Next
          </button>
        </div>
      )}

      <ActionDialog
        open={blocking !== null}
        title={`Block ${blocking?.external_reference ?? ""}?`}
        confirmLabel="Block unit"
        danger
        busy={dialog.busy}
        error={dialog.error}
        onConfirm={() => void block()}
        onClose={() => setBlocking(null)}
      >
        <p>
          A blocked unit cannot record a first verification. Verifications
          already recorded remain in the record.
        </p>
        <label>
          <span>Reason</span>
          <textarea
            rows={2}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Reported stolen from warehouse 3"
            required
            autoFocus
          />
        </label>
      </ActionDialog>
    </div>
  );
}
