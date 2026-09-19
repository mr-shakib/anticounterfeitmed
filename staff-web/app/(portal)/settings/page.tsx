"use client";

import { useState } from "react";
import QRCode from "qrcode";
import { ApiError, Membership, api } from "@/lib/api";
import { useSession } from "@/components/Session";

export default function SettingsPage() {
  const { membership, refresh } = useSession();
  const [enrolment, setEnrolment] = useState<{ secret: string; qr: string } | null>(null);
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);

  if (!membership) return null;

  async function begin() {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const data = await api.post<{ secret: string; provisioning_uri: string }>(
        "/v1/staff/mfa/enroll",
      );
      // Rendered here: the provisioning URI carries the shared secret and must
      // not be sent to an image service.
      setEnrolment({
        secret: data.secret,
        qr: await QRCode.toDataURL(data.provisioning_uri, { margin: 2, width: 200 }),
      });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not start enrolment.");
    } finally {
      setBusy(false);
    }
  }

  async function confirm(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api.post<Membership>("/v1/staff/mfa/confirm", { code });
      setEnrolment(null);
      setCode("");
      setNotice("Second factor enabled. You will be asked for a code at each sign-in.");
      await refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "That code did not match.");
    } finally {
      setBusy(false);
    }
  }

  async function disable(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api.post<Membership>("/v1/staff/mfa/disable", { code });
      setCode("");
      setNotice("Second factor removed.");
      await refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not remove it.");
    } finally {
      setBusy(false);
    }
  }

  const enrolled = membership.mfa_enrolled;
  const compulsory = membership.mfa_enrolment_required;

  return (
    <>
      <h1>Settings</h1>
      <p className="muted">
        Signed in as {membership.username} · {membership.role.replace(/_/g, " ").toLowerCase()}
      </p>

      {error && <div className="alert error">{error}</div>}
      {notice && <div className="alert success">{notice}</div>}

      <h2>Two-factor authentication</h2>
      <div className="card">
        <p style={{ marginTop: 0 }}>
          {enrolled ? (
            <>
              <span className="badge ok">enabled</span>{" "}
              You are asked for a code from your authenticator at each sign-in.
            </>
          ) : (
            <>
              <span className="badge">not set up</span>{" "}
              Your account is protected by a password only.
            </>
          )}
        </p>

        {!enrolled && (
          <p className="muted">
            {compulsory
              ? "This role requires a second factor before it can be used."
              : "Recommended. This role can act on medicine records, and a password on its own is thin protection if it is ever reused or leaked."}
          </p>
        )}

        {!enrolled && !enrolment && (
          <button onClick={begin} disabled={busy}>
            {busy ? "Preparing…" : "Set up two-factor authentication"}
          </button>
        )}

        {!enrolled && enrolment && (
          <>
            <p className="muted">
              Scan this with an authenticator app — Google Authenticator, Authy,
              1Password, or any other — then enter the six-digit code it shows.
            </p>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={enrolment.qr}
              alt="Authenticator setup code"
              width={200}
              height={200}
              style={{ display: "block", background: "#fff", padding: 8, borderRadius: 8 }}
            />
            <details style={{ margin: "0.75rem 0" }}>
              <summary className="muted" style={{ cursor: "pointer" }}>
                Can&rsquo;t scan? Enter the key by hand
              </summary>
              <p className="mono" style={{ wordBreak: "break-all" }}>{enrolment.secret}</p>
            </details>
            <form onSubmit={confirm}>
              <label style={{ maxWidth: 240 }}>
                <span>Code from your authenticator</span>
                <input
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  required
                />
              </label>
              <button type="submit" disabled={busy}>
                {busy ? "Confirming…" : "Confirm and enable"}
              </button>{" "}
              <button
                type="button"
                className="secondary"
                onClick={() => setEnrolment(null)}
                disabled={busy}
              >
                Cancel
              </button>
            </form>
          </>
        )}

        {enrolled && !compulsory && (
          <form onSubmit={disable} style={{ marginTop: "1rem" }}>
            <p className="muted">
              Removing it needs a current code, so an unattended screen cannot be
              used to strip the protection off your account.
            </p>
            <label style={{ maxWidth: 240 }}>
              <span>Code from your authenticator</span>
              <input
                value={code}
                onChange={(e) => setCode(e.target.value)}
                inputMode="numeric"
                autoComplete="one-time-code"
                required
              />
            </label>
            <button type="submit" className="danger" disabled={busy}>
              {busy ? "Removing…" : "Turn off two-factor authentication"}
            </button>
          </form>
        )}

        {enrolled && compulsory && (
          <p className="muted">
            This role requires a second factor, so it cannot be turned off here.
            An administrator can reset it if you lose the authenticator.
          </p>
        )}
      </div>
    </>
  );
}
