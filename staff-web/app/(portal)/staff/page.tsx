"use client";

import { useEffect, useState } from "react";
import { ApiError, Membership2, api } from "@/lib/api";

export default function StaffAccessPage() {
  const [memberships, setMemberships] = useState<Membership2[]>([]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState("");

  async function load() {
    try {
      setMemberships(await api.get<Membership2[]>("/v1/admin/memberships"));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not load staff.");
    }
  }

  useEffect(() => { void load(); }, []);

  async function resetMfa(m: Membership2) {
    const confirmed = window.confirm(
      `Reset the second factor for ${m.username}?\n\n` +
        "They will be asked to enrol a new authenticator at their next sign-in. " +
        "This does not grant access on its own.",
    );
    if (!confirmed) return;
    setBusy(m.membership_id);
    setError("");
    try {
      await api.post(`/v1/admin/memberships/${m.membership_id}/reset-mfa`);
      setNotice(`Second factor cleared for ${m.username}. The reset is recorded in the audit trail.`);
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not reset.");
    } finally {
      setBusy("");
    }
  }

  return (
    <>
      <h1>Staff access</h1>
      <p className="muted">
        Privileged roles require a second factor. Revoke access when someone
        leaves rather than relying on their password expiring.
      </p>
      {error && <div className="alert error">{error}</div>}
      {notice && <div className="alert success">{notice}</div>}

      <table>
        <thead>
          <tr>
            <th>User</th><th>Organization</th><th>Role</th>
            <th>Enabled</th><th>Second factor</th><th></th>
          </tr>
        </thead>
        <tbody>
          {memberships.map((m) => (
            <tr key={m.membership_id}>
              <td>{m.username}</td>
              <td className="muted">{m.organization}</td>
              <td>{m.role.replace(/_/g, " ").toLowerCase()}</td>
              <td>
                {m.is_enabled
                  ? <span className="badge ok">enabled</span>
                  : <span className="badge danger">disabled</span>}
              </td>
              <td>
                {!m.mfa_required
                  ? <span className="muted">not required</span>
                  : m.mfa_enrolled
                    ? <span className="badge ok">enrolled</span>
                    : <span className="badge warn">not enrolled</span>}
              </td>
              <td>
                {m.mfa_required && m.mfa_enrolled && (
                  <button
                    className="secondary"
                    onClick={() => resetMfa(m)}
                    disabled={busy === m.membership_id}
                  >
                    Reset second factor
                  </button>
                )}
              </td>
            </tr>
          ))}
          {memberships.length === 0 && (
            <tr><td colSpan={6} className="muted">No staff.</td></tr>
          )}
        </tbody>
      </table>
    </>
  );
}
