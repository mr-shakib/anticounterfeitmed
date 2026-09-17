"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiError, Report, api } from "@/lib/api";

export default function ReportsPage() {
  const [reports, setReports] = useState<Report[]>([]);
  const [status, setStatus] = useState("OPEN");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");

  const load = useCallback(async () => {
    setError("");
    try {
      setReports(await api.get<Report[]>(`/v1/admin/reports?status=${status}`));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not load the queue.");
    }
  }, [status]);

  useEffect(() => { void load(); }, [load]);

  async function conclude(report: Report) {
    const conclusion = window.prompt(
      `Record a finding for ${report.case_number}.\n\nThis adds to the case; it does not erase anything.`,
    );
    if (!conclusion) return;
    setBusy(report.case_number);
    try {
      await api.post(`/v1/admin/reports/${report.case_number}/conclude`, {
        status: "CLOSED",
        conclusion,
      });
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not record the finding.");
    } finally {
      setBusy("");
    }
  }

  return (
    <>
      <h1>Investigations</h1>
      <p className="muted">
        A repeat check or a failed scan is a signal for review, not evidence of
        counterfeiting.
      </p>
      {error && <div className="alert error">{error}</div>}

      <div className="card">
        <label style={{ maxWidth: 240 }}>
          <span>Status</span>
          <select value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="OPEN">Open</option>
            <option value="IN_REVIEW">In review</option>
            <option value="CLOSED">Closed</option>
            <option value="all">All</option>
          </select>
        </label>
      </div>

      <table>
        <thead>
          <tr><th>Case</th><th>Reason</th><th>Reference</th><th>Opened</th><th>Status</th><th></th></tr>
        </thead>
        <tbody>
          {reports.map((r) => (
            <tr key={r.case_number}>
              <td className="mono">{r.case_number}</td>
              <td>{r.reason.replace(/_/g, " ").toLowerCase()}</td>
              <td className="mono muted">{r.external_reference || r.unit_id?.slice(0, 8) || "—"}</td>
              <td className="muted">{new Date(r.created_at).toLocaleDateString()}</td>
              <td><span className="badge">{r.status.toLowerCase()}</span></td>
              <td>
                {r.status !== "CLOSED" && (
                  <button onClick={() => conclude(r)} disabled={busy === r.case_number}>
                    Record finding
                  </button>
                )}
              </td>
            </tr>
          ))}
          {reports.length === 0 && (
            <tr><td colSpan={6} className="muted">Nothing in this queue.</td></tr>
          )}
        </tbody>
      </table>
    </>
  );
}
