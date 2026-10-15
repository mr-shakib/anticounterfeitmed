"use client";

import { useEffect, useState } from "react";
import { ApiError, Organization, StaffRow, api } from "@/lib/api";
import { ActionDialog, Dialog } from "@/components/Dialog";
import { Feedback, useAction } from "@/components/Feedback";
import { useSession } from "@/components/Session";

const ROLES: Record<string, { value: StaffRow["role"]; label: string; note: string }[]> = {
  MANUFACTURER: [
    {
      value: "MANUFACTURER_STAFF",
      label: "Manufacturer staff",
      note: "Prepares batches: labels, printing, QC and coating. Cannot activate.",
    },
    {
      value: "RELEASE_MANAGER",
      label: "Release manager",
      note: "Everything staff can do, plus activating units and recalling batches.",
    },
  ],
  PLATFORM: [
    {
      value: "PLATFORM_ADMIN",
      label: "Platform admin",
      note: "Approves manufacturers, manages staff access, investigates reports.",
    },
  ],
};

type Created = StaffRow & { temporary_password: string };

export default function StaffAccessPage() {
  const { membership } = useSession();
  const [rows, setRows] = useState<StaffRow[]>([]);
  const [organizations, setOrganizations] = useState<Organization[]>([]);
  const [loadError, setLoadError] = useState("");
  const [adding, setAdding] = useState(false);
  const [form, setForm] = useState({ organization: "", username: "", role: "" });
  const [created, setCreated] = useState<Created | null>(null);
  const [copied, setCopied] = useState(false);
  const [target, setTarget] = useState<{ row: StaffRow; kind: "revoke" | "restore" | "reset" } | null>(null);
  const [reason, setReason] = useState("");
  const [notice, setNotice] = useState("");
  const create = useAction();
  const dialog = useAction();

  async function load() {
    try {
      const [staff, orgs] = await Promise.all([
        api.get<StaffRow[]>("/v1/admin/memberships"),
        api.get<Organization[]>("/v1/admin/organizations"),
      ]);
      setRows(staff);
      setOrganizations(orgs);
    } catch (e) {
      setLoadError(e instanceof ApiError ? e.message : "Could not load staff.");
    }
  }

  useEffect(() => { void load(); }, []);

  const organization = organizations.find((o) => o.id === form.organization);
  const roles = organization ? ROLES[organization.type] ?? [] : [];

  const add = (event: React.FormEvent) => {
    event.preventDefault();
    setNotice("");
    void create.run(async () => {
      const result = await api.post<Created>("/v1/admin/memberships", form);
      setForm({ organization: "", username: "", role: "" });
      setAdding(false);
      setCopied(false);
      setCreated(result);
      await load();
    });
  };

  const act = () =>
    dialog.run(async () => {
      if (!target) return;
      const { row, kind } = target;
      if (kind === "revoke") {
        await api.post(`/v1/admin/memberships/${row.membership_id}/disable`, { reason });
        setNotice(`Access revoked for ${row.username}. It takes effect on their next request.`);
      } else if (kind === "restore") {
        await api.post(`/v1/admin/memberships/${row.membership_id}/enable`);
        setNotice(`Access restored for ${row.username}.`);
      } else {
        await api.post(`/v1/admin/memberships/${row.membership_id}/reset-mfa`);
        setNotice(
          `Second factor cleared for ${row.username}. The reset is recorded in the audit trail.`,
        );
      }
      setTarget(null);
      await load();
    });

  const open = (row: StaffRow, kind: "revoke" | "restore" | "reset") => {
    dialog.clear();
    setNotice("");
    setReason("");
    setTarget({ row, kind });
  };

  return (
    <>
      <div className="title-row">
        <h1>Staff access</h1>
        {!adding && (
          <button onClick={() => { create.clear(); setAdding(true); }}>Add staff member</button>
        )}
      </div>
      <p className="muted">
        Privileged roles require a second factor. Revoke access when someone
        leaves rather than relying on their password expiring.
      </p>
      {loadError && <div className="alert error">{loadError}</div>}

      {adding && (
        <div className="card">
          <h2>Add a staff member</h2>
          <form onSubmit={add}>
            <div className="row">
              <label>
                <span>Organization</span>
                <select
                  value={form.organization}
                  onChange={(e) => setForm({ ...form, organization: e.target.value, role: "" })}
                  required
                >
                  <option value="">Choose…</option>
                  {organizations.map((o) => (
                    <option key={o.id} value={o.id}>
                      {o.name}
                      {o.approval_status !== "APPROVED" ? " (pending approval)" : ""}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                <span>Username</span>
                <input
                  value={form.username}
                  onChange={(e) => setForm({ ...form, username: e.target.value })}
                  autoComplete="off"
                  pattern="[\w.@+\-]+"
                  title="Letters, digits and @ . + - _ only"
                  required
                />
              </label>
              <label>
                <span>Role</span>
                <select
                  value={form.role}
                  onChange={(e) => setForm({ ...form, role: e.target.value })}
                  disabled={!organization}
                  required
                >
                  <option value="">{organization ? "Choose…" : "Choose an organization first"}</option>
                  {roles.map((r) => (
                    <option key={r.value} value={r.value}>{r.label}</option>
                  ))}
                </select>
              </label>
            </div>
            {roles.find((r) => r.value === form.role) && (
              <p className="muted">{roles.find((r) => r.value === form.role)?.note}</p>
            )}
            <p className="muted">
              A temporary password is generated and shown to you once. They must
              replace it at their first sign-in.
            </p>
            <div className="form-actions">
              <button type="submit" disabled={create.busy}>
                {create.busy ? "Adding…" : "Add staff member"}
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
          <tr>
            <th>User</th><th>Organization</th><th>Role</th>
            <th>Access</th><th>Second factor</th><th></th>
          </tr>
        </thead>
        <tbody>
          {rows.map((m) => (
            <tr key={m.membership_id}>
              <td>
                {m.username}
                {m.password_change_required && (
                  <div className="muted">has not signed in yet</div>
                )}
              </td>
              <td className="muted">{m.organization}</td>
              <td>{m.role.replace(/_/g, " ").toLowerCase()}</td>
              <td>
                {m.is_enabled
                  ? <span className="badge ok">enabled</span>
                  : <span className="badge danger">revoked</span>}
              </td>
              <td>
                {!m.mfa_required
                  ? <span className="muted">not required</span>
                  : m.mfa_enrolled
                    ? <span className="badge ok">enrolled</span>
                    : <span className="badge warn">not enrolled</span>}
              </td>
              <td className="nowrap">
                {m.mfa_required && m.mfa_enrolled && (
                  <button className="secondary" onClick={() => open(m, "reset")}>
                    Reset second factor…
                  </button>
                )}{" "}
                {m.membership_id !== membership?.membership_id &&
                  (m.is_enabled ? (
                    <button className="danger" onClick={() => open(m, "revoke")}>
                      Revoke…
                    </button>
                  ) : (
                    <button onClick={() => open(m, "restore")}>Restore…</button>
                  ))}
              </td>
            </tr>
          ))}
          {rows.length === 0 && (
            <tr><td colSpan={6} className="muted">No staff.</td></tr>
          )}
        </tbody>
      </table>

      <Dialog
        open={created !== null}
        title={`${created?.username ?? ""} added`}
        onClose={() => setCreated(null)}
      >
        {created && (
          <>
            <p>
              Give them this temporary password through a channel only they can
              read. <strong>It is shown once</strong> and cannot be retrieved again.
            </p>
            <div className="secret-box">
              <code>{created.temporary_password}</code>
              <button
                type="button"
                className="secondary"
                onClick={() => {
                  void navigator.clipboard?.writeText(created.temporary_password);
                  setCopied(true);
                }}
              >
                {copied ? "Copied" : "Copy"}
              </button>
            </div>
            <p className="muted">
              Username <strong>{created.username}</strong> ·{" "}
              {created.role.replace(/_/g, " ").toLowerCase()} at {created.organization}.
              At first sign-in they choose their own password; this one stops
              working then.
            </p>
            <div className="dialog-actions">
              <button type="button" onClick={() => setCreated(null)}>Done</button>
            </div>
          </>
        )}
      </Dialog>

      <ActionDialog
        open={target !== null}
        title={
          target?.kind === "revoke"
            ? `Revoke access for ${target.row.username}?`
            : target?.kind === "restore"
              ? `Restore access for ${target.row.username}?`
              : `Reset the second factor for ${target?.row.username ?? ""}?`
        }
        confirmLabel={
          target?.kind === "revoke" ? "Revoke access" : target?.kind === "restore" ? "Restore access" : "Reset"
        }
        danger={target?.kind === "revoke"}
        busy={dialog.busy}
        error={dialog.error}
        onConfirm={() => void act()}
        onClose={() => setTarget(null)}
      >
        {target?.kind === "revoke" && (
          <>
            <p>
              They are signed out of everything on their next request and cannot
              sign in again until access is restored.
            </p>
            <label>
              <span>Reason</span>
              <input
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="Left the company"
                required
                autoFocus
              />
            </label>
          </>
        )}
        {target?.kind === "restore" && (
          <p>They can sign in again with their existing password and second factor.</p>
        )}
        {target?.kind === "reset" && (
          <p>
            They will be asked to set up a new authenticator at their next sign-in.
            This does not grant access on its own.
          </p>
        )}
      </ActionDialog>
    </>
  );
}
