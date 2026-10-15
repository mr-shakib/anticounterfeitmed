"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ApiError, Batch, Dashboard, api } from "@/lib/api";
import { BatchTable, stageInput, waitingOnMe } from "@/components/BatchTable";
import { useSession } from "@/components/Session";

function Stat({ label, value, tone }: { label: string; value: number; tone?: string }) {
  return (
    <div className="stat">
      <div className="value" style={tone ? { color: `var(--${tone})` } : undefined}>
        {value}
      </div>
      <div className="label">{label}</div>
    </div>
  );
}

export default function OverviewPage() {
  const { membership } = useSession();
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [batches, setBatches] = useState<Batch[] | null>(null);
  const [error, setError] = useState("");

  const isAdmin = membership?.role === "PLATFORM_ADMIN";
  const canRelease = membership?.role === "RELEASE_MANAGER";

  useEffect(() => {
    (async () => {
      try {
        if (isAdmin) {
          setDashboard(await api.get<Dashboard>("/v1/admin/dashboard"));
        } else {
          setBatches(await api.get<Batch[]>("/v1/staff/batches"));
        }
      } catch (e) {
        setError(e instanceof ApiError ? e.message : "Could not load.");
      }
    })();
  }, [isAdmin]);

  const waiting = (batches ?? []).filter((b) => waitingOnMe(b, canRelease));
  const readyUnits = (batches ?? [])
    .filter((b) => !b.is_recalled)
    .reduce((sum, b) => sum + stageInput(b).ready, 0);

  return (
    <>
      <h1>Overview</h1>
      {error && <div className="alert error">{error}</div>}

      {isAdmin && dashboard && (
        <>
          <div className="grid">
            <Stat label="Organizations pending approval" value={dashboard.organizations_pending} />
            <Stat label="Organizations suspended" value={dashboard.organizations_suspended}
                  tone={dashboard.organizations_suspended ? "danger" : undefined} />
            <Stat label="Activation jobs with failures" value={dashboard.activation_jobs_with_failures}
                  tone={dashboard.activation_jobs_with_failures ? "warn" : undefined} />
            <Stat label="Open investigations" value={dashboard.reports_open} />
          </div>
          {dashboard.organizations_pending > 0 && (
            <div className="alert info">
              {dashboard.organizations_pending} manufacturer(s) are waiting for
              approval. <Link href="/organizations">Review them</Link>.
            </div>
          )}
          <h2>Verification</h2>
          <div className="grid">
            <Stat label="First verifications" value={dashboard.first_verifications} />
            <Stat label="Repeat checks" value={dashboard.repeat_checks} />
            <Stat label="Receipts awaiting signature" value={dashboard.receipts_pending} />
            <Stat label="Receipts failed" value={dashboard.receipts_failed}
                  tone={dashboard.receipts_failed ? "danger" : undefined} />
          </div>
          <p className="muted">
            A repeat check is not evidence of counterfeiting on its own. It is a
            signal for review.
          </p>
        </>
      )}

      {!isAdmin && batches !== null && (
        <>
          {batches.length === 0 ? (
            <div className="card">
              <p className="muted" style={{ margin: 0 }}>
                No batches yet. <Link href="/products">Add a product</Link>, then{" "}
                <Link href="/batches">create a batch</Link> to begin.
              </p>
            </div>
          ) : (
            <>
              {canRelease && readyUnits > 0 && (
                <div className="alert success">
                  <strong>{readyUnits} unit(s) are ready to activate.</strong> Open a
                  batch marked &ldquo;Ready to activate&rdquo; to release them.
                </div>
              )}
              <h2>Waiting on you</h2>
              {waiting.length === 0 ? (
                <div className="card">
                  <p className="muted" style={{ margin: 0 }}>
                    Nothing is waiting on you.{" "}
                    {!canRelease && "Batches ready to activate wait on a release manager."}
                  </p>
                </div>
              ) : (
                <BatchTable batches={waiting.slice(0, 10)} canRelease={canRelease} markMine={false} />
              )}
              <h2>Recent batches</h2>
              <BatchTable batches={batches.slice(0, 10)} canRelease={canRelease} showDates={false} />
              {batches.length > 10 && (
                <p><Link href="/batches">All {batches.length} batches</Link></p>
              )}
            </>
          )}
        </>
      )}
    </>
  );
}
