"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ApiError, Organization, api } from "@/lib/api";
import { ActionDialog } from "@/components/Dialog";
import { Feedback, useAction } from "@/components/Feedback";

const EMPTY = { name: "", contact_email: "", contact_phone: "" };

export default function OrganizationsPage() {
  const [organizations, setOrganizations] = useState<Organization[]>([]);
  const [loadError, setLoadError] = useState("");
  const [form, setForm] = useState({ ...EMPTY });
  const [adding, setAdding] = useState(false);
  const [approving, setApproving] = useState<Organization | null>(null);
  const [suspending, setSuspending] = useState<Organization | null>(null);
  const [reason, setReason] = useState("");
  const [notice, setNotice] = useState("");
  const create = useAction();
  const dialog = useAction();

  async function load() {
    try {
      setOrganizations(await api.get<Organization[]>("/v1/admin/organizations"));
    } catch (e) {
      setLoadError(e instanceof ApiError ? e.message : "Could not load organizations.");
    }
  }

  useEffect(() => { void load(); }, []);

  const add = (event: React.FormEvent) => {
    event.preventDefault();
    setNotice("");
    void create.run(async () => {
      const org = await api.post<Organization>("/v1/admin/organizations", form);
      setForm({ ...EMPTY });
      setAdding(false);
      setNotice(`${org.name} added. Approve it when its details are checked, then add its staff.`);
      await load();
    });
  };

  const approve = () =>
    dialog.run(async () => {
      if (!approving) return;
      const org = await api.post<Organization>(
        `/v1/admin/organizations/${approving.id}/approve`,
      );
      setApproving(null);
      setNotice(
        `${org.name} approved` +
          (org.type === "MANUFACTURER" ? " and given its signing key." : "."),
      );
      await load();
    });

  const suspend = () =>
    dialog.run(async () => {
      if (!suspending) return;
      await api.post(`/v1/admin/organizations/${suspending.id}/suspend`, { reason });
      setNotice(`${suspending.name} suspended.`);
      setSuspending(null);
      await load();
    });

  return (
    <>
      <div className="title-row">
        <h1>Organizations</h1>
        {!adding && (
          <button onClick={() => { create.clear(); setAdding(true); }}>Add manufacturer</button>
        )}
      </div>
      <p className="muted">
        A manufacturer can do nothing until it is approved. Approval gives it the
        key its units&rsquo; credentials are signed with; then add its staff on{" "}
        <Link href="/staff">Staff access</Link>.
      </p>
      {loadError && <div className="alert error">{loadError}</div>}

      {adding && (
        <div className="card">
          <h2>Add a manufacturer</h2>
          <form onSubmit={add}>
            <div className="row">
              <label>
                <span>Registered name</span>
                <input
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  required
                />
              </label>
              <label>
                <span>Contact email</span>
                <input
                  type="email"
                  value={form.contact_email}
                  onChange={(e) => setForm({ ...form, contact_email: e.target.value })}
                  required
                />
              </label>
              <label>
                <span>Contact phone (optional)</span>
                <input
                  type="tel"
                  value={form.contact_phone}
                  onChange={(e) => setForm({ ...form, contact_phone: e.target.value })}
                />
              </label>
            </div>
            <p className="muted">It starts pending. Nothing can be issued until you approve it.</p>
            <div className="form-actions">
              <button type="submit" disabled={create.busy}>
                {create.busy ? "Adding…" : "Add manufacturer"}
              </button>
              <button type="button" className="secondary" onClick={() => setAdding(false)}>
                Cancel
              </button>
            </div>
            <Feedback error={create.error} />
          </form>
        </div>
      )}
      <Feedback notice={notice} />

      <table>
        <thead>
          <tr><th>Name</th><th>Type</th><th>Approval</th><th>Signing key</th><th>State</th><th></th></tr>
        </thead>
        <tbody>
          {organizations.map((o) => (
            <tr key={o.id}>
              <td>
                {o.name}
                {o.contact_email && <div className="muted">{o.contact_email}</div>}
                {o.suspension_reason && (
                  <div className="muted">Suspended: {o.suspension_reason}</div>
                )}
              </td>
              <td className="muted">{o.type.toLowerCase()}</td>
              <td>
                <span className={`badge ${o.approval_status === "APPROVED" ? "ok" : "warn"}`}>
                  {o.approval_status.toLowerCase()}
                </span>
              </td>
              <td>
                {o.type !== "MANUFACTURER" ? (
                  <span className="muted">—</span>
                ) : o.has_signing_key ? (
                  <span className="badge ok">active</span>
                ) : (
                  <span className="badge warn">none</span>
                )}
              </td>
              <td>
                {o.is_suspended
                  ? <span className="badge danger">suspended</span>
                  : <span className="badge ok">active</span>}
              </td>
              <td className="nowrap">
                {o.approval_status !== "APPROVED" && (
                  <button onClick={() => { dialog.clear(); setNotice(""); setApproving(o); }}>
                    Approve…
                  </button>
                )}{" "}
                {!o.is_suspended && o.type === "MANUFACTURER" && (
                  <button
                    className="danger"
                    onClick={() => { dialog.clear(); setNotice(""); setReason(""); setSuspending(o); }}
                  >
                    Suspend…
                  </button>
                )}
              </td>
            </tr>
          ))}
          {organizations.length === 0 && (
            <tr><td colSpan={6} className="muted">No organizations.</td></tr>
          )}
        </tbody>
      </table>

      <ActionDialog
        open={approving !== null}
        title={`Approve ${approving?.name ?? ""}?`}
        confirmLabel="Approve"
        busy={dialog.busy}
        error={dialog.error}
        onConfirm={() => void approve()}
        onClose={() => setApproving(null)}
      >
        <p>Approving lets this manufacturer generate labels and activate units.</p>
        {approving?.type === "MANUFACTURER" && !approving.has_signing_key && (
          <p className="muted">
            It has no signing key yet, so one is created now and the trust list
            the app downloads is republished to include it. The key is held by
            the platform: its signatures are platform-managed, associated with
            this manufacturer.
          </p>
        )}
        {approving?.contact_email && (
          <p className="muted">Contact on record: {approving.contact_email}</p>
        )}
      </ActionDialog>

      <ActionDialog
        open={suspending !== null}
        title={`Suspend ${suspending?.name ?? ""}?`}
        confirmLabel="Suspend"
        danger
        busy={dialog.busy}
        error={dialog.error}
        onConfirm={() => void suspend()}
        onClose={() => setSuspending(null)}
      >
        <p>
          Suspension blocks issuance and activation immediately, and overrides an
          otherwise positive verification result for this manufacturer&rsquo;s units.
        </p>
        <label>
          <span>Reason</span>
          <textarea
            rows={2}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            required
            autoFocus
          />
        </label>
      </ActionDialog>
    </>
  );
}
