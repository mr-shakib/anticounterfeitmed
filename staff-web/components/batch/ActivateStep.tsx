"use client";

import { useState } from "react";
import { ActionDialog } from "@/components/Dialog";
import { Feedback, useAction } from "@/components/Feedback";
import { ActivationJob, Batch, api } from "@/lib/api";

/**
 * Step 4: put the ready units into circulation.
 *
 * Everyone sees how many units are ready and why the rest are not; only a
 * release manager has the button. Runs are loaded from the server, so a run's
 * failures and the way to retry them survive a reload.
 */
export function ActivateStep({
  batch,
  counts,
  ready,
  canRelease,
  jobs,
  onChanged,
}: {
  batch: Batch;
  counts: Record<string, number>;
  ready: number;
  canRelease: boolean;
  jobs: ActivationJob[];
  onChanged: () => Promise<void>;
}) {
  const [confirming, setConfirming] = useState(false);
  const [notice, setNotice] = useState("");
  const dialog = useAction();
  const retryAction = useAction();

  const latest = jobs[0];
  const notReady: [string, number][] = (
    [
      ["no printing recorded yet", counts.CREATED ?? 0],
      ["waiting for QC", counts.PRINTED ?? 0],
      ["waiting for the scratch layer", counts.QC_PASSED ?? 0],
      // Coated but not counted ready: blocked, or a record is missing.
      ["coated but blocked", Math.max((counts.COVERED ?? 0) - ready, 0)],
    ] as [string, number][]
  ).filter(([, n]) => n > 0);
  const notReadyTotal = notReady.reduce((sum, [, n]) => sum + n, 0);

  const activate = () =>
    dialog.run(async () => {
      const job = await api.post<ActivationJob>("/v1/staff/activation-jobs", {
        batch: batch.id,
      });
      setConfirming(false);
      await onChanged();
      const skipped = Object.entries(job.not_attempted ?? {})
        .map(([state, n]) => `${n} ${state.replace(/_/g, " ").toLowerCase()}`)
        .join(", ");
      setNotice(
        (job.failed > 0
          ? `${job.succeeded} activated, ${job.failed} failed — see below.`
          : `${job.succeeded} unit(s) activated.`) +
          (skipped ? ` Not part of this run: ${skipped}.` : ""),
      );
    });

  const retry = (job: ActivationJob) =>
    retryAction.run(async () => {
      const result = await api.post<ActivationJob>(`/v1/staff/activation-jobs/${job.id}/retry`);
      await onChanged();
      return (
        `Retried ${result.requested} previously failed unit(s): ` +
        `${result.succeeded} activated, ${result.failed} still failing.`
      );
    });

  return (
    <>
      <div className="card">
        <h2>Readiness</h2>
        <div className="grid">
          <div className="stat">
            <div className="value">{ready}</div>
            <div className="label">ready to activate</div>
          </div>
          <div className="stat">
            <div className="value">{(counts.ACTIVE ?? 0) + (counts.REDEEMED ?? 0)}</div>
            <div className="label">already activated</div>
          </div>
          <div className="stat">
            <div className="value">{notReadyTotal}</div>
            <div className="label">not ready yet</div>
          </div>
        </div>
        {notReady.length > 0 && (
          <p className="muted">
            Not ready:{" "}
            {notReady.map(([why, n]) => `${n} ${why}`).join(" · ")}.
          </p>
        )}

        {batch.is_recalled ? (
          <p className="muted">This batch is recalled. Nothing more can be activated.</p>
        ) : canRelease ? (
          <>
            <p className="muted">
              Activation signs a credential for each ready unit. Units missing a
              record stay inactive.
            </p>
            <button
              onClick={() => {
                dialog.clear();
                setNotice("");
                setConfirming(true);
              }}
              disabled={ready === 0}
            >
              Activate {ready} unit(s)…
            </button>
          </>
        ) : (
          <div className="alert info">
            {ready > 0
              ? `${ready} unit(s) are ready. A release manager activates them — this batch shows as “Ready to activate” on their batch list and overview.`
              : "Only a release manager can activate units. Once units are ready, this batch shows as “Ready to activate” on their batch list."}
          </div>
        )}
        <Feedback notice={notice} />
      </div>

      <div className="card">
        <h2>Activation runs</h2>
        {jobs.length === 0 ? (
          <p className="muted">No activation runs for this batch yet.</p>
        ) : (
          <>
            {latest && latest.failed > 0 && (
              <div className="alert error">
                <strong>
                  The latest run left {latest.failed} unit(s) inactive. This batch is
                  not fully activated.
                </strong>
                <ul className="failure-list">
                  {latest.failures.slice(0, 10).map((f) => (
                    <li key={f.unit_id}>
                      <span className="mono">{f.external_reference}</span> — {f.reason}
                    </li>
                  ))}
                </ul>
                {latest.failures.length > 10 && (
                  <p style={{ margin: 0 }}>…and {latest.failures.length - 10} more.</p>
                )}
                {canRelease && !batch.is_recalled && (
                  <button
                    style={{ marginTop: "0.75rem" }}
                    onClick={() => void retry(latest)}
                    disabled={retryAction.busy}
                  >
                    {retryAction.busy ? "Retrying…" : "Retry only the failures"}
                  </button>
                )}
              </div>
            )}
            <Feedback error={retryAction.error} notice={retryAction.notice} />
            <table>
              <thead>
                <tr><th>Started</th><th>Requested</th><th>Activated</th><th>Failed</th><th>Status</th></tr>
              </thead>
              <tbody>
                {jobs.map((j) => (
                  <tr key={j.id}>
                    <td className="muted">{new Date(j.created_at).toLocaleString()}</td>
                    <td>{j.requested}</td>
                    <td>{j.succeeded}</td>
                    <td>{j.failed}</td>
                    <td>
                      <span className={`badge ${j.failed > 0 ? "danger" : "ok"}`}>
                        {j.status.replace(/_/g, " ").toLowerCase()}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      </div>

      <ActionDialog
        open={confirming}
        title={`Activate ${ready} unit(s)?`}
        confirmLabel={`Activate ${ready}`}
        busy={dialog.busy}
        error={dialog.error}
        onConfirm={() => void activate()}
        onClose={() => setConfirming(false)}
      >
        <p>
          Batch <strong>{batch.batch_number}</strong> · {batch.product_brand} ·
          expires {batch.expires_on}
        </p>
        <ul>
          <li><strong>{ready}</strong> unit(s) have printing, QC and coating recorded and will be activated.</li>
          {notReadyTotal > 0 && (
            <li>
              <strong>{notReadyTotal}</strong> will stay inactive:{" "}
              {notReady.map(([why, n]) => `${n} ${why}`).join(", ")}.
            </li>
          )}
        </ul>
        <p className="muted">
          Once activated, a unit can be verified by the public. This is recorded
          against your name as the release approval.
        </p>
      </ActionDialog>
    </>
  );
}
