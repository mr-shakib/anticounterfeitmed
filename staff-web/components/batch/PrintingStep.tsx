"use client";

import { useState } from "react";
import { ActionDialog } from "@/components/Dialog";
import { Feedback, useAction } from "@/components/Feedback";
import { PrintScanner } from "@/components/PrintScanner";
import { RecordStepForm } from "@/components/batch/RecordStepForm";
import { PrintJob, api } from "@/lib/api";

/**
 * Step 2: confirm what came off the printer.
 *
 * Scanning each printed code is the evidence; recording printing by hand is
 * the fallback, and is labelled as an assertion. Reconciling a run records
 * how many labels were printed and spoiled, and starts the clock on deleting
 * its stored codes.
 */
export function PrintingStep({
  batchId,
  counts,
  total,
  scanned,
  printJobs,
  onChanged,
  onScanned,
}: {
  batchId: string;
  counts: Record<string, number>;
  total: number;
  scanned: number;
  printJobs: PrintJob[];
  onChanged: () => Promise<void>;
  /** Called after every scan; the page batches these into one refresh. */
  onScanned: () => void;
}) {
  const unreconciled = printJobs.filter((p) => !p.reconciled_at);
  const [reconciling, setReconciling] = useState<PrintJob | null>(null);
  const [printed, setPrinted] = useState("");
  const [rejected, setRejected] = useState("0");
  const [notice, setNotice] = useState("");
  const dialog = useAction();

  const open = (job: PrintJob) => {
    dialog.clear();
    setNotice("");
    setPrinted(String(job.issued_count));
    setRejected("0");
    setReconciling(job);
  };

  const reconcile = () =>
    dialog.run(async () => {
      if (!reconciling) return;
      await api.post(`/v1/staff/print-jobs/${reconciling.id}/reconcile`, {
        printed: Number(printed),
        rejected: Number(rejected),
      });
      setReconciling(null);
      await onChanged();
      setNotice(
        "Reconciled. This run's stored labels will be deleted within 24 hours; " +
          "open them from step 1 now if you still need them.",
      );
    });

  return (
    <>
      <h2 className="panel-heading">Scan the printed codes</h2>
      <PrintScanner
        batchId={batchId}
        scanned={scanned}
        total={total}
        onProgress={onScanned}
      />

      <div className="card">
        <h2>Record printing by hand</h2>
        <div className="alert info">
          For units printed but not scanned. This is an operational record
          entered by your staff, not scan evidence captured by this system. Both
          the completion time you enter and the time it was entered are stored.
        </div>
        <RecordStepForm
          batchId={batchId}
          steps={["PRINTED"]}
          counts={counts}
          onRecorded={onChanged}
        />
      </div>

      <div className="card">
        <h2>Reconcile label runs</h2>
        <p className="muted">
          Once printing is finished, record how many labels of each run were
          printed and how many were spoiled or destroyed.
        </p>
        {unreconciled.length === 0 ? (
          <p className="muted">
            {printJobs.length === 0
              ? "No label runs yet."
              : "Every label run is reconciled."}
          </p>
        ) : (
          <table>
            <thead>
              <tr><th>Generated</th><th>Labels issued</th><th></th></tr>
            </thead>
            <tbody>
              {unreconciled.map((p) => (
                <tr key={p.id}>
                  <td className="muted">{new Date(p.created_at).toLocaleString()}</td>
                  <td>{p.issued_count}</td>
                  <td>
                    <button onClick={() => open(p)}>Reconcile…</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <Feedback notice={notice} />
      </div>

      <ActionDialog
        open={reconciling !== null}
        title="Reconcile this label run"
        confirmLabel="Reconcile"
        busy={dialog.busy}
        error={dialog.error}
        onConfirm={() => void reconcile()}
        onClose={() => setReconciling(null)}
      >
        {reconciling && (
          <>
            <p className="muted">
              Run of {reconciling.issued_count} label(s), generated{" "}
              {new Date(reconciling.created_at).toLocaleString()}.
            </p>
            <div className="row">
              <label>
                <span>Labels printed</span>
                <input
                  type="number"
                  min={0}
                  max={reconciling.issued_count}
                  value={printed}
                  onChange={(e) => setPrinted(e.target.value)}
                  required
                  autoFocus
                />
              </label>
              <label>
                <span>Spoiled or destroyed</span>
                <input
                  type="number"
                  min={0}
                  max={reconciling.issued_count}
                  value={rejected}
                  onChange={(e) => setRejected(e.target.value)}
                  required
                />
              </label>
            </div>
            <p className="muted" style={{ marginTop: "0.75rem" }}>
              After reconciling, this run&rsquo;s stored labels are deleted within
              24 hours and cannot be shown again.
            </p>
          </>
        )}
      </ActionDialog>
    </>
  );
}
