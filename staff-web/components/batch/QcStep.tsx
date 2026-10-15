"use client";

import { useState } from "react";
import { ActionDialog } from "@/components/Dialog";
import { Feedback, useAction } from "@/components/Feedback";
import { RecordStepForm } from "@/components/batch/RecordStepForm";
import { Batch, api } from "@/lib/api";

/** Unit states a QC rejection can still void. Activated units are past it. */
const REJECTABLE = ["CREATED", "PRINTED", "QC_PASSED", "COVERED"];

function parseReferences(text: string): string[] {
  return Array.from(
    new Set(
      text
        .split(/[\s,;]+/)
        .map((r) => r.trim())
        .filter(Boolean),
    ),
  );
}

/**
 * Step 3: QC and the scratch coating, and rejecting what failed QC.
 *
 * Rejection used to be one option in the same dropdown as "QC passed", applied
 * to the whole batch with no confirmation -- so one slip voided every unit. It
 * is now its own section: named units by default, and the whole batch only
 * after typing its number back.
 */
export function QcStep({
  batch,
  counts,
  stepCounts,
  total,
  onChanged,
}: {
  batch: Batch;
  counts: Record<string, number>;
  stepCounts: Record<string, number>;
  total: number;
  onChanged: () => Promise<void>;
}) {
  return (
    <>
      <div className="card">
        <h2>Record QC and coating</h2>
        <div className="alert info">
          These are operational records entered by your staff, not scan evidence
          captured by this system. Both the completion time you enter and the time
          it was entered are stored. The coating is applied after scanning and
          covers the code, so no scan can evidence it.
        </div>
        <div className="grid">
          {[
            ["QC_PASSED", "QC passed"],
            ["COATED", "Scratch layer applied"],
            ["QC_REJECTED", "Rejected at QC"],
          ].map(([step, label]) => (
            <div className="stat" key={step}>
              <div className="value">
                {stepCounts[step] ?? 0}
                <span className="muted" style={{ fontSize: "0.95rem" }}> / {total}</span>
              </div>
              <div className="label">{label}</div>
            </div>
          ))}
        </div>
        <RecordStepForm
          batchId={batch.id}
          steps={["QC_PASSED", "COATED"]}
          counts={counts}
          onRecorded={onChanged}
        />
      </div>

      <RejectUnits batch={batch} counts={counts} onChanged={onChanged} />
    </>
  );
}

function RejectUnits({
  batch,
  counts,
  onChanged,
}: {
  batch: Batch;
  counts: Record<string, number>;
  onChanged: () => Promise<void>;
}) {
  const [mode, setMode] = useState<"units" | "batch" | null>(null);
  const [references, setReferences] = useState("");
  const [reason, setReason] = useState("");
  const [completedAt, setCompletedAt] = useState("");
  const [sourceReference, setSourceReference] = useState("");
  const [typedBatch, setTypedBatch] = useState("");
  const [notice, setNotice] = useState("");
  const dialog = useAction();

  const parsed = parseReferences(references);
  const rejectable = REJECTABLE.reduce((sum, state) => sum + (counts[state] ?? 0), 0);

  const open = (next: "units" | "batch") => {
    dialog.clear();
    setNotice("");
    setTypedBatch("");
    setMode(next);
  };

  const reject = () =>
    dialog.run(async () => {
      const result = await api.post<{ recorded: number; rejected: unknown[] }>(
        "/v1/staff/manufacturing-confirmations",
        {
          batch: batch.id,
          step: "QC_REJECTED",
          completed_at: new Date(completedAt).toISOString(),
          source_reference: sourceReference,
          reason,
          ...(mode === "units"
            ? { external_references: parsed }
            : { confirm_batch_number: typedBatch }),
        },
      );
      setMode(null);
      setReferences("");
      setReason("");
      await onChanged();
      const skipped = result.rejected.length;
      setNotice(
        `${result.recorded} unit(s) rejected and voided.` +
          (skipped ? ` ${skipped} were already activated or void and were left alone.` : ""),
      );
    });

  const fields = (
    <>
      <label>
        <span>Why they were rejected</span>
        <input
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="Smudged print, failed readability check"
          required
        />
      </label>
      <div className="row">
        <label>
          <span>Rejected at</span>
          <input
            type="datetime-local"
            value={completedAt}
            onChange={(e) => setCompletedAt(e.target.value)}
            required
          />
        </label>
        <label>
          <span>Source record reference</span>
          <input
            value={sourceReference}
            onChange={(e) => setSourceReference(e.target.value)}
            placeholder="QC sheet 14"
            required
          />
        </label>
      </div>
    </>
  );

  return (
    <div className="card card-danger">
      <h2>Reject units that failed QC</h2>
      <p className="muted">
        A rejected unit is voided permanently. Its label must be destroyed, and
        a replacement needs a new code from step 1.
      </p>
      <label>
        <span>References of the rejected strips — one per line, or separated by commas</span>
        <textarea
          rows={3}
          value={references}
          onChange={(e) => setReferences(e.target.value)}
          placeholder={`${batch.batch_number}-000014\n${batch.batch_number}-000027`}
          spellCheck={false}
        />
      </label>
      <div className="row">
        <div className="shrink">
          <button
            className="danger"
            onClick={() => open("units")}
            disabled={parsed.length === 0}
          >
            Reject {parsed.length || ""} unit(s)…
          </button>
        </div>
        <div className="shrink">
          <button
            className="secondary"
            onClick={() => open("batch")}
            disabled={rejectable === 0}
          >
            Reject the whole batch…
          </button>
        </div>
      </div>
      <Feedback notice={notice} />

      <ActionDialog
        open={mode === "units"}
        title={`Reject ${parsed.length} unit(s)?`}
        confirmLabel={`Reject and void ${parsed.length}`}
        danger
        busy={dialog.busy}
        error={dialog.error}
        onConfirm={() => void reject()}
        onClose={() => setMode(null)}
      >
        <p>
          These units will be <strong>voided permanently</strong> and can never be
          activated:
        </p>
        <p className="mono reference-list">{parsed.slice(0, 30).join(", ")}
          {parsed.length > 30 && ` … and ${parsed.length - 30} more`}
        </p>
        <p className="muted">
          If any reference is not a unit of this batch, nothing is recorded and
          you are told which.
        </p>
        {fields}
      </ActionDialog>

      <ActionDialog
        open={mode === "batch"}
        title="Reject the whole batch?"
        confirmLabel={`Void ${rejectable} unit(s)`}
        danger
        busy={dialog.busy}
        error={dialog.error}
        onConfirm={() => void reject()}
        onClose={() => setMode(null)}
      >
        <p>
          This voids <strong>every one of the {rejectable} unit(s)</strong> in batch{" "}
          <strong>{batch.batch_number}</strong> that is not yet activated. It cannot
          be undone.
        </p>
        {fields}
        <label>
          <span>Type the batch number to confirm</span>
          <input
            value={typedBatch}
            onChange={(e) => setTypedBatch(e.target.value)}
            placeholder={batch.batch_number}
            autoComplete="off"
            spellCheck={false}
            required
            pattern={batch.batch_number.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}
            title={`Type ${batch.batch_number} exactly`}
          />
        </label>
      </ActionDialog>
    </div>
  );
}
