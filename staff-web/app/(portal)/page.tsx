"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ApiError, Batch, Dashboard, api } from "@/lib/api";
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
  const [batches, setBatches] = useState<Batch[]>([]);
  const [error, setError] = useState("");

  const isAdmin = membership?.role === "PLATFORM_ADMIN";

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

      {!isAdmin && (
        <>
          <h2>Recent batches</h2>
          {batches.length === 0 ? (
            <div className="card">
              <p className="muted" style={{ margin: 0 }}>
                No batches yet. Create a product, then a batch, to begin.
              </p>
            </div>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Batch</th><th>Product</th><th>Expires</th><th>Planned</th><th>Status</th>
                </tr>
              </thead>
              <tbody>
                {batches.slice(0, 10).map((b) => (
                  <tr key={b.id}>
                    <td><Link href={`/batches/${b.id}`}>{b.batch_number}</Link></td>
                    <td>{b.product_brand}</td>
                    <td>{b.expires_on}</td>
                    <td>{b.planned_unit_count}</td>
                    <td>
                      {b.is_recalled
                        ? <span className="badge danger">recalled</span>
                        : <span className="badge ok">active</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </>
  );
}
