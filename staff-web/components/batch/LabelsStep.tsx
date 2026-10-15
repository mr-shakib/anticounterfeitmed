"use client";

import { useEffect, useState } from "react";
import { ActionDialog } from "@/components/Dialog";
import { Feedback, useAction } from "@/components/Feedback";
import { LabelSheet, LABEL_SIZES_MM } from "@/components/LabelSheet";
import { ApiError, Batch, LabelExport, PrintJob, api } from "@/lib/api";
import { DEFAULT_LABEL_LAYOUT, type LabelLayout } from "@/lib/labelPrint.ts";

/**
 * Step 1: generate the codes and get them to the printer.
 *
 * The codes are shown again from "Label runs" until a run is reconciled and
 * for 24 hours after, so leaving the page does not lose them.
 */
export function LabelsStep({
  batch,
  total,
  printJobs,
  onChanged,
}: {
  batch: Batch;
  total: number;
  printJobs: PrintJob[];
  onChanged: () => Promise<void>;
}) {
  const remaining = Math.max(batch.planned_unit_count - total, 0);
  const [count, setCount] = useState(String(remaining || batch.planned_unit_count));
  const [exported, setExported] = useState<LabelExport | null>(null);
  const [layout, setLayout] = useState<LabelLayout>(DEFAULT_LABEL_LAYOUT);
  const [layoutError, setLayoutError] = useState("");
  // Null until someone picks one for this run: the layout's default applies.
  const [labelSizeMm, setLabelSizeMm] = useState<number | null>(null);
  const [confirming, setConfirming] = useState(false);
  const generateAction = useAction();
  const runsAction = useAction();

  useEffect(() => {
    let live = true;
    api
      .get<LabelLayout>("/v1/staff/label-layout")
      .then((saved) => live && setLayout(saved))
      .catch((e) => {
        if (live) {
          setLayoutError(
            e instanceof ApiError ? e.message : "Could not load the sheet layout.",
          );
        }
      });
    return () => {
      live = false;
    };
  }, []);

  const requested = Number(count);
  const overPlan = total + requested - batch.planned_unit_count;

  const generate = () =>
    generateAction.run(async () => {
      const result = await api.post<LabelExport>("/v1/staff/print-jobs", {
        batch: batch.id,
        count: requested,
      });
      setConfirming(false);
      setExported(result);
      await onChanged();
      return `${result.label_export.length} label(s) generated. They are shown below.`;
    });

  const reopen = (job: PrintJob) =>
    runsAction.run(async () => {
      setExported(await api.get<LabelExport>(`/v1/staff/print-jobs/${job.id}/export`));
      return "Labels reopened below. They remain available until the date shown.";
    });

  const downloadReferences = () => {
    if (!exported) return;
    // References only, for reconciliation. A code cannot be rebuilt from a line
    // of text any more -- label software would print the public URL alone --
    // so the printable sheet and the SVG archive are what carry the codes.
    const rows = [
      "external_reference",
      ...exported.label_export.map((e) => e.external_reference),
    ].join("\n");
    const url = URL.createObjectURL(new Blob([rows], { type: "text/csv" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = `labels-${batch.batch_number}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  };

  return (
    <>
      <div className="card">
        <h2>Generate labels</h2>
        <p className="muted">
          One code per strip. {total} of {batch.planned_unit_count} planned unit(s)
          have codes so far. Printing happens outside this system; the sheet
          generated here is what you send to the printer.
        </p>
        <form
          className="row"
          onSubmit={(event) => {
            event.preventDefault();
            generateAction.clear();
            if (overPlan > 0) setConfirming(true);
            else void generate();
          }}
        >
          <label>
            <span>How many strips</span>
            <input
              type="number"
              min={1}
              max={100000}
              value={count}
              onChange={(e) => setCount(e.target.value)}
              required
            />
          </label>
          <div className="shrink">
            <button type="submit" disabled={generateAction.busy || batch.is_recalled}>
              {generateAction.busy ? "Generating…" : "Generate"}
            </button>
          </div>
        </form>
        <Feedback error={generateAction.error} notice={generateAction.notice} />
        <p className="muted" style={{ marginTop: "0.75rem", fontSize: "0.85rem" }}>
          Only a hash of each code is kept permanently. Once a run&rsquo;s labels
          are deleted they cannot be recovered — replacing lost labels then means
          voiding those units and issuing new ones, which leaves a record.
        </p>
      </div>

      {exported && (
        <div className="card">
          <h2>Labels to print</h2>
          <div className="alert info">
            <strong>{exported.export_notice}</strong>
          </div>
          <div className="row" style={{ marginBottom: "0.75rem" }}>
            <label style={{ maxWidth: 200 }}>
              <span>Label footprint</span>
              <select
                value={labelSizeMm ?? layout.footprint_mm}
                onChange={(e) => setLabelSizeMm(Number(e.target.value))}
              >
                {LABEL_SIZES_MM.map((mm) => (
                  <option key={mm} value={mm}>
                    {mm} mm
                  </option>
                ))}
              </select>
            </label>
            <div className="shrink">
              <button className="secondary" onClick={downloadReferences}>
                Download CSV of references
              </button>
            </div>
            <div className="shrink">
              <button className="secondary" onClick={() => setExported(null)}>
                Hide labels
              </button>
            </div>
          </div>
          {layoutError && (
            <div className="alert error">
              {layoutError} The sheet uses the default layout: codes only, 15&nbsp;mm apart.
            </div>
          )}
          <LabelSheet
            entries={exported.label_export}
            batchNumber={batch.batch_number}
            layout={{ ...layout, footprint_mm: labelSizeMm ?? layout.footprint_mm }}
          />
        </div>
      )}

      <div className="card">
        <h2>Label runs</h2>
        {printJobs.length === 0 ? (
          <p className="muted">No labels generated for this batch yet.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Generated</th><th>Units</th><th>Status</th><th>Labels</th><th></th>
              </tr>
            </thead>
            <tbody>
              {printJobs.map((p) => (
                <tr key={p.id}>
                  <td className="muted">{new Date(p.created_at).toLocaleString()}</td>
                  <td>{p.issued_count}</td>
                  <td>
                    <span className={`badge ${p.reconciled_at ? "ok" : "warn"}`}>
                      {p.reconciled_at ? "reconciled" : "not reconciled"}
                    </span>
                  </td>
                  <td className="muted">
                    {p.export_available ? (
                      <>
                        available until{" "}
                        {p.export_expires_at
                          ? new Date(p.export_expires_at).toLocaleDateString()
                          : "—"}
                      </>
                    ) : (
                      <span className="badge danger">deleted</span>
                    )}
                  </td>
                  <td>
                    {p.export_available && (
                      <button onClick={() => void reopen(p)} disabled={runsAction.busy}>
                        Show labels
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <Feedback error={runsAction.error} notice={runsAction.notice} />
      </div>

      <ActionDialog
        open={confirming}
        title="Generate more than planned?"
        confirmLabel={`Generate ${requested}`}
        busy={generateAction.busy}
        error={generateAction.error}
        onConfirm={() => void generate()}
        onClose={() => setConfirming(false)}
      >
        <p>
          This batch was planned at <strong>{batch.planned_unit_count}</strong> unit(s)
          and already has <strong>{total}</strong>. Generating {requested} more puts
          it <strong>{overPlan}</strong> over plan.
        </p>
        <p className="muted">
          Extra codes are real units. Any that are not printed and used should be
          voided, so they cannot be activated later.
        </p>
      </ActionDialog>
    </>
  );
}
