"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiError, AuditEntry, api } from "@/lib/api";

const ACTIONS = [
  "", "ORGANIZATION_APPROVED", "ORGANIZATION_SUSPENDED", "UNITS_GENERATED",
  "MANUFACTURING_RECORDED", "UNIT_ACTIVATED", "UNIT_BLOCKED", "UNIT_VOIDED",
  "BATCH_RECALLED", "VERIFICATION_COMMITTED", "KEY_REVOKED",
];

export default function AuditPage() {
  const [entries, setEntries] = useState<AuditEntry[]>([]);
  const [action, setAction] = useState("");
  const [requestId, setRequestId] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setError("");
    try {
      const query = new URLSearchParams();
      if (action) query.set("action", action);
      if (requestId) query.set("request_id", requestId);
      setEntries(await api.get<AuditEntry[]>(`/v1/admin/audit?${query}`));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not search the audit trail.");
    }
  }, [action, requestId]);

  useEffect(() => { void load(); }, [load]);

  return (
    <>
      <h1>Audit trail</h1>
      <p className="muted">
        Append-only. Investigations add a conclusion; nothing here is edited or
        removed. Records never contain a package token.
      </p>
      {error && <div className="alert error">{error}</div>}

      <div className="card">
        <div className="row">
          <label>
            <span>Action</span>
            <select value={action} onChange={(e) => setAction(e.target.value)}>
              {ACTIONS.map((a) => (
                <option key={a} value={a}>{a ? a.replace(/_/g, " ").toLowerCase() : "all actions"}</option>
              ))}
            </select>
          </label>
          <label>
            <span>Request ID</span>
            <input value={requestId} onChange={(e) => setRequestId(e.target.value)} />
          </label>
        </div>
      </div>

      <table>
        <thead>
          <tr><th>When</th><th>Action</th><th>Organization</th><th>Actor</th><th>Detail</th></tr>
        </thead>
        <tbody>
          {entries.map((e) => (
            <tr key={e.id}>
              <td className="muted">{new Date(e.created_at).toLocaleString()}</td>
              <td>{e.action.replace(/_/g, " ").toLowerCase()}</td>
              <td>{e.organization ?? "—"}</td>
              <td className="muted">{e.actor ?? "—"}</td>
              <td className="muted mono">
                {e.reason || Object.entries(e.detail ?? {}).map(([k, v]) => `${k}=${v}`).join(" ") || "—"}
              </td>
            </tr>
          ))}
          {entries.length === 0 && (
            <tr><td colSpan={5} className="muted">Nothing matches.</td></tr>
          )}
        </tbody>
      </table>
    </>
  );
}
