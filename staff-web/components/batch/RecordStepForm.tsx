"use client";

import { useState } from "react";
import { ActionDialog } from "@/components/Dialog";
import { Feedback, useAction } from "@/components/Feedback";
import { api } from "@/lib/api";

/** The steps a person records by hand, and the unit state each one follows. */
export const RECORDABLE = {
  PRINTED: { label: "Printed", from: "CREATED", fromLabel: "not yet printed" },
  QC_PASSED: { label: "QC passed", from: "PRINTED", fromLabel: "printed" },
  COATED: { label: "Scratch layer applied", from: "QC_PASSED", fromLabel: "QC-passed" },
} as const;

export type RecordableStep = keyof typeof RECORDABLE;

/**
 * Record a manufacturing step against every unit of a batch that has reached it.
 *
 * Only the steps passed in are offered, so the printing step cannot record QC
 * and the QC step cannot record a rejection by picking the wrong option. Before
 * anything is written the dialog states exactly how many units it will touch.
 */
export function RecordStepForm({
  batchId,
  steps,
  counts,
  onRecorded,
}: {
  batchId: string;
  steps: RecordableStep[];
  counts: Record<string, number>;
  onRecorded: () => Promise<void>;
}) {
  const firstOutstanding =
    steps.find((s) => (counts[RECORDABLE[s].from] ?? 0) > 0) ?? steps[0];
  const [step, setStep] = useState<RecordableStep>(firstOutstanding);
  const [completedAt, setCompletedAt] = useState("");
  const [sourceReference, setSourceReference] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [notice, setNotice] = useState("");
  const dialog = useAction();

  const eligible = counts[RECORDABLE[step].from] ?? 0;

  const record = () =>
    dialog.run(async () => {
      const result = await api.post<{ recorded: number; rejected: unknown[] }>(
        "/v1/staff/manufacturing-confirmations",
        {
          batch: batchId,
          step,
          completed_at: new Date(completedAt).toISOString(),
          source_reference: sourceReference,
        },
      );
      setConfirming(false);
      setSourceReference("");
      await onRecorded();
      const skipped = result.rejected.length;
      setNotice(
        `${RECORDABLE[step].label} recorded for ${result.recorded} unit(s).` +
          (skipped ? ` ${skipped} at another stage were left as they were.` : ""),
      );
    });

  return (
    <>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          setNotice("");
          dialog.clear();
          setConfirming(true);
        }}
      >
        <div className="row">
          {steps.length > 1 && (
            <label>
              <span>Step</span>
              <select value={step} onChange={(e) => setStep(e.target.value as RecordableStep)}>
                {steps.map((s) => (
                  <option key={s} value={s}>
                    {RECORDABLE[s].label} — {counts[RECORDABLE[s].from] ?? 0} unit(s) waiting
                  </option>
                ))}
              </select>
            </label>
          )}
          <label>
            <span>Actually completed at</span>
            <input
              type="datetime-local"
              value={completedAt}
              max={new Date(Date.now() - new Date().getTimezoneOffset() * 60_000)
                .toISOString()
                .slice(0, 16)}
              onChange={(e) => setCompletedAt(e.target.value)}
              required
            />
          </label>
          <label>
            <span>Source record reference</span>
            <input
              value={sourceReference}
              onChange={(e) => setSourceReference(e.target.value)}
              placeholder="Production log 2026-09-17"
              required
            />
          </label>
          <div className="shrink">
            <button type="submit" disabled={dialog.busy || eligible === 0}>
              Record {RECORDABLE[step].label.toLowerCase()}…
            </button>
          </div>
        </div>
        {eligible === 0 && (
          <p className="muted" style={{ marginTop: "0.5rem" }}>
            No units are {RECORDABLE[step].fromLabel} right now, so there is nothing to
            record for this step.
          </p>
        )}
        <Feedback notice={notice} />
      </form>

      {/* Outside the form: a form nested in another submits the outer one. */}
      <ActionDialog
        open={confirming}
        title={`Record "${RECORDABLE[step].label}"?`}
        confirmLabel={`Record for ${eligible} unit(s)`}
        busy={dialog.busy}
        error={dialog.error}
        onConfirm={() => void record()}
        onClose={() => setConfirming(false)}
      >
        <p>
          This records <strong>{RECORDABLE[step].label.toLowerCase()}</strong> for
          the <strong>{eligible}</strong> unit(s) in this batch that are currently{" "}
          {RECORDABLE[step].fromLabel}. Units at any other stage are left alone.
        </p>
        <p className="muted">
          Completed {completedAt ? new Date(completedAt).toLocaleString() : "—"}, from{" "}
          &ldquo;{sourceReference}&rdquo;. This is recorded as your organization&rsquo;s
          assertion, with your name and the time you entered it. It cannot be undone.
        </p>
      </ActionDialog>
    </>
  );
}
