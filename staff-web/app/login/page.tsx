"use client";

import { useState } from "react";
import Image from "next/image";
import { useRouter } from "next/navigation";
import QRCode from "qrcode";
import { ApiError, Membership, api, primeCsrf } from "@/lib/api";

type Stage = "credentials" | "verify" | "enroll";

export default function LoginPage() {
  const router = useRouter();
  const [stage, setStage] = useState<Stage>("credentials");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [enrolment, setEnrolment] = useState<{ secret: string; uri: string } | null>(null);
  const [enrolmentQr, setEnrolmentQr] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  /** Decide where to send someone once a password has been accepted. */
  function routeAfterPassword(me: Membership) {
    if (!me.mfa_required) {
      router.push("/");
      return;
    }
    setStage(me.mfa_enrolled ? "verify" : "enroll");
  }

  async function submitCredentials(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await primeCsrf();
      const me = await api.post<Membership>("/v1/staff/login", { username, password });
      routeAfterPassword(me);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Login failed.");
    } finally {
      setBusy(false);
    }
  }

  async function beginEnrolment() {
    setBusy(true);
    setError("");
    try {
      const data = await api.post<{ secret: string; provisioning_uri: string }>(
        "/v1/staff/mfa/enroll",
      );
      setEnrolment({ secret: data.secret, uri: data.provisioning_uri });
      // Rendered here rather than fetched: the provisioning URI contains the
      // shared secret, so it must not travel to an image service.
      setEnrolmentQr(
        await QRCode.toDataURL(data.provisioning_uri, { margin: 2, width: 220 }),
      );
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not start enrolment.");
    } finally {
      setBusy(false);
    }
  }

  async function submitCode(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const path = stage === "enroll" ? "/v1/staff/mfa/confirm" : "/v1/staff/mfa/verify";
      await api.post<Membership>(path, { code });
      router.push("/");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "That code did not match.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="center">
      <div className="card auth-card">
        <div className="auth-brand">
          <Image src="/mark.png" alt="" width={64} height={64} priority />
          <h1>Anticounterfeit Med</h1>
        </div>
        <p className="muted">Manufacturer and platform administration.</p>

        {error && <div className="alert error">{error}</div>}

        {stage === "credentials" && (
          <form onSubmit={submitCredentials}>
            <label>
              <span>Username</span>
              <input
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="username"
                required
              />
            </label>
            <label>
              <span>Password</span>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                required
              />
            </label>
            <button type="submit" disabled={busy}>
              {busy ? "Signing in…" : "Sign in"}
            </button>
          </form>
        )}

        {stage === "enroll" && (
          <>
            <div className="alert info">
              This role can release medicine into circulation, so it requires a
              second factor before it can be used.
            </div>
            {!enrolment ? (
              <button onClick={beginEnrolment} disabled={busy}>
                {busy ? "Preparing…" : "Set up an authenticator"}
              </button>
            ) : (
              <>
                <p className="muted">
                  Scan this with an authenticator app — Google Authenticator,
                  Authy, 1Password, or any other — then enter the six-digit code
                  it shows.
                </p>
                {enrolmentQr && (
                  <img
                    src={enrolmentQr}
                    alt="Authenticator setup code"
                    width={220}
                    height={220}
                    style={{
                      display: "block",
                      margin: "0 auto 0.75rem",
                      background: "#fff",
                      padding: 8,
                      borderRadius: 8,
                    }}
                  />
                )}
                <details style={{ marginBottom: "0.75rem" }}>
                  <summary className="muted" style={{ cursor: "pointer" }}>
                    Can&rsquo;t scan? Enter the key by hand
                  </summary>
                  <p className="mono" style={{ wordBreak: "break-all", marginTop: "0.5rem" }}>
                    {enrolment.secret}
                  </p>
                </details>
                <p className="muted" style={{ fontSize: "0.85rem" }}>
                  This is shown once. If you lose the authenticator, an
                  administrator can reset it for you.
                </p>
                <form onSubmit={submitCode}>
                  <label>
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
                    {busy ? "Confirming…" : "Confirm"}
                  </button>
                </form>
              </>
            )}
          </>
        )}

        {stage === "verify" && (
          <form onSubmit={submitCode}>
            <p className="muted">Enter the code from your authenticator app.</p>
            <label>
              <span>Six-digit code</span>
              <input
                value={code}
                onChange={(e) => setCode(e.target.value)}
                inputMode="numeric"
                autoComplete="one-time-code"
                autoFocus
                required
              />
            </label>
            <button type="submit" disabled={busy}>
              {busy ? "Checking…" : "Continue"}
            </button>
          </form>
        )}
      </div>
    </main>
  );
}
