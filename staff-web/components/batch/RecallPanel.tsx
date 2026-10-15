"use client";

import { useState } from "react";
import { ActionDialog } from "@/components/Dialog";
import { useAction } from "@/components/Feedback";
import { Batch, api } from "@/lib/api";

/** Publish a recall. Release managers only; it cannot be withdrawn. */
export function RecallPanel({
  batch,
  onChanged,
}: {
  batch: Batch;
  onChanged: () => Promise<void>;
}) {
  const [notice, setNotice] = useState("");
  const [contact, setContact] = useState("");
  const [confirming, setConfirming] = useState(false);
  const dialog = useAction();

  const recall = () =>
    dialog.run(async () => {
      await api.post(`/v1/staff/batches/${batch.id}/recall`, { notice, contact });
      setConfirming(false);
      await onChanged();
    });

  return (
    <div className="card card-danger">
      <h2>Recall this batch</h2>
      <p className="muted">
        A recall stops any unit of this batch recording a first verification, and
        shows your notice to anyone who scans one. Verifications that already
        happened stay in the record.
      </p>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          dialog.clear();
          setConfirming(true);
        }}
      >
        <label>
          <span>Recall notice shown to consumers</span>
          <textarea
            rows={3}
            value={notice}
            onChange={(e) => setNotice(e.target.value)}
            required
          />
        </label>
        <label>
          <span>Contact instructions (optional)</span>
          <input
            value={contact}
            onChange={(e) => setContact(e.target.value)}
            placeholder="Call 16xxx or return to the pharmacy"
          />
        </label>
        <button type="submit" className="danger">Publish recall…</button>
      </form>

      <ActionDialog
        open={confirming}
        title={`Recall batch ${batch.batch_number}?`}
        confirmLabel="Publish recall"
        danger
        busy={dialog.busy}
        error={dialog.error}
        onConfirm={() => void recall()}
        onClose={() => setConfirming(false)}
      >
        <p>
          The recall takes effect immediately and <strong>cannot be withdrawn</strong>.
          Consumers will see:
        </p>
        <blockquote className="quote">{notice}</blockquote>
        {contact && <p className="muted">Contact: {contact}</p>}
      </ActionDialog>
    </div>
  );
}
