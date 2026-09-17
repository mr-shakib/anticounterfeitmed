"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { ApiError, Membership, api, primeCsrf } from "@/lib/api";

type Stage = "credentials" | "verify" | "enroll";

export default function LoginPage() {
  const router = useRouter();
  const [stage, setStage] = useState<Stage>("credentials");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [enrolment, setEnrolment] = useState<{ secret: string; uri: string } | null>(null);
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
        <h1>MedSecure PQC</h1>
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
                  Add this key to an authenticator app, then enter the code it
                  shows. The key is displayed once.
                </p>
                <p className="mono" style={{ wordBreak: "break-all" }}>
                  {enrolment.secret}
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
