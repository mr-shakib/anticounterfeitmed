"use client";

import { useEffect, useState } from "react";
import { ApiError, Organization, api } from "@/lib/api";

export default function OrganizationsPage() {
  const [organizations, setOrganizations] = useState<Organization[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");

  async function load() {
    try {
      setOrganizations(await api.get<Organization[]>("/v1/admin/organizations"));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not load organizations.");
    }
  }

  useEffect(() => { void load(); }, []);

  async function approve(org: Organization) {
    setBusy(org.id);
    setError("");
    try {
      await api.post(`/v1/admin/organizations/${org.id}/approve`);
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not approve.");
    } finally {
      setBusy("");
    }
  }

  async function suspend(org: Organization) {
    const reason = window.prompt(
      `Suspend ${org.name}? Suspension blocks issuance and overrides a positive verification result.\n\nReason:`,
    );
    if (!reason) return;
    setBusy(org.id);
    setError("");
    try {
      await api.post(`/v1/admin/organizations/${org.id}/suspend`, { reason });
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not suspend.");
    } finally {
      setBusy("");
    }
  }

  return (
    <>
      <h1>Organizations</h1>
      <p className="muted">
        A manufacturer must be approved before it can issue serials, and its
        issuer key association recorded.
      </p>
      {error && <div className="alert error">{error}</div>}

      <table>
        <thead>
          <tr><th>Name</th><th>Type</th><th>Approval</th><th>State</th><th></th></tr>
        </thead>
        <tbody>
          {organizations.map((o) => (
            <tr key={o.id}>
              <td>
                {o.name}
                {o.suspension_reason && (
                  <div className="muted">{o.suspension_reason}</div>
                )}
              </td>
              <td className="muted">{o.type.toLowerCase()}</td>
              <td>
                <span className={`badge ${o.approval_status === "APPROVED" ? "ok" : "warn"}`}>
                  {o.approval_status.toLowerCase()}
                </span>
              </td>
              <td>
                {o.is_suspended
                  ? <span className="badge danger">suspended</span>
                  : <span className="badge ok">active</span>}
              </td>
              <td>
                {o.approval_status !== "APPROVED" && (
                  <button onClick={() => approve(o)} disabled={busy === o.id}>
                    Approve
                  </button>
                )}{" "}
                {!o.is_suspended && o.type === "MANUFACTURER" && (
                  <button className="danger" onClick={() => suspend(o)} disabled={busy === o.id}>
                    Suspend
                  </button>
                )}
              </td>
            </tr>
          ))}
          {organizations.length === 0 && (
            <tr><td colSpan={5} className="muted">No organizations.</td></tr>
          )}
        </tbody>
      </table>
    </>
  );
}
