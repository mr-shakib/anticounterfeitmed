"use client";

import { useState } from "react";
import Image from "next/image";
import { useRouter } from "next/navigation";
import QRCode from "qrcode";
import { Footer } from "@/components/Footer";
import { ApiError, Membership, api, primeCsrf } from "@/lib/api";

type Stage = "credentials" | "verify" | "password" | "enroll";

export default function LoginPage() {
  const router = useRouter();
  const [stage, setStage] = useState<Stage>("credentials");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [repeatPassword, setRepeatPassword] = useState("");
  const [enrolment, setEnrolment] = useState<{ secret: string; uri: string } | null>(null);
  const [enrolmentQr, setEnrolmentQr] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  /** Decide where to send someone once a password has been accepted.
   *
   * Enrolment is not forced here. Someone with a second factor is asked for a
   * code; someone without one goes straight in and can enrol later from
   * Settings. The exception is a role whose policy makes enrolment compulsory,
   * where there is nothing useful to let them do until it is set up.
   *
   * Someone signing in with an administrator's temporary password chooses their
   * own before anything else -- after their code, if they have a factor.
   * Called again after each step, with the state that step returned.
   */
  function routeAfterPassword(me: Membership) {
    setCode("");
    if (me.mfa_enrolled && !me.mfa_verified) {
      setStage("verify");
      return;
    }
    if (me.password_change_required) {
      setStage("password");
      return;
    }
    if (me.mfa_enrolment_required && !me.mfa_enrolled) {
      setStage("enroll");
      return;
    }
    router.push("/");
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
      routeAfterPassword(await api.post<Membership>(path, { code }));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "That code did not match.");
    } finally {
      setBusy(false);
    }
  }

  async function submitNewPassword(event: React.FormEvent) {
    event.preventDefault();
    if (newPassword !== repeatPassword) {
      setError("The two passwords do not match.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const me = await api.post<Membership>("/v1/staff/password", {
        current_password: password,
        new_password: newPassword,
      });
      setPassword("");
      setNewPassword("");
      setRepeatPassword("");
      routeAfterPassword(me);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not change the password.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth">
      <main className="center">
        <div className="card auth-card">
          <div className="auth-brand">
            <Image src="/mark.png" alt="" width={60} height={60} priority />
            <h1>Anticounterfeit Med</h1>
          </div>
          <p className="muted">Staff sign-in · manufacturer and platform administration</p>

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

          {stage === "password" && (
            <form onSubmit={submitNewPassword}>
              <div className="alert info">
                You signed in with a temporary password. Choose your own to
                continue; the temporary one stops working.
              </div>
              <label>
                <span>New password</span>
                <input
                  type="password"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  autoComplete="new-password"
                  minLength={8}
                  autoFocus
                  required
                />
              </label>
              <label>
                <span>Repeat it</span>
                <input
                  type="password"
                  value={repeatPassword}
                  onChange={(e) => setRepeatPassword(e.target.value)}
                  autoComplete="new-password"
                  minLength={8}
                  required
                />
              </label>
              <p className="muted" style={{ fontSize: "0.85rem" }}>
                At least 8 characters, not entirely numbers, and not a common password.
              </p>
              <button type="submit" disabled={busy}>
                {busy ? "Saving…" : "Set password and continue"}
              </button>
            </form>
          )}

          {stage === "enroll" && (
            <>
              <div className="alert info">
                This role can release medicine into circulation, so a second factor
                is required before it can be used.
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
      <Footer />
    </div>
  );
}
