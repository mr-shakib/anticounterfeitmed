"use client";

import { use, useCallback, useEffect, useState } from "react";
import {
  ActivationJob, ApiError, Batch, BatchUnits, LabelExport, PrintJob, Unit, api,
} from "@/lib/api";
import { PrintScanner } from "@/components/PrintScanner";
import { LabelSheet, LABEL_SIZES_MM } from "@/components/LabelSheet";
import { useSession } from "@/components/Session";

const STEPS = [
  { value: "PRINTED", label: "Printed" },
  { value: "QC_PASSED", label: "QC passed" },
  { value: "QC_REJECTED", label: "QC rejected — voids the unit" },
  { value: "COATED", label: "Scratch layer applied" },
];

function lifecycleTone(lifecycle: string) {
  if (lifecycle === "ACTIVE") return "ok";
  if (lifecycle === "REDEEMED") return "warn";
  if (lifecycle === "VOID") return "danger";
  return "";
}

export default function BatchDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const { membership } = useSession();
  const canRelease = membership?.role === "RELEASE_MANAGER";

  const [batch, setBatch] = useState<Batch | null>(null);
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [stepCounts, setStepCounts] = useState<Record<string, number>>({});
  const [unitsReady, setUnitsReady] = useState(0);
  const [unitsScanned, setUnitsScanned] = useState(0);
  const [units, setUnits] = useState<Unit[]>([]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);

  const [count, setCount] = useState("100");
  const [exported, setExported] = useState<LabelExport | null>(null);
  const [labelSizeMm, setLabelSizeMm] = useState(20);

  const [step, setStep] = useState("PRINTED");
  const [completedAt, setCompletedAt] = useState("");
  const [sourceReference, setSourceReference] = useState("");

  const [job, setJob] = useState<ActivationJob | null>(null);
  const [recallNotice, setRecallNotice] = useState("");
  const [printJobs, setPrintJobs] = useState<PrintJob[]>([]);

  const totalUnits = Object.values(counts).reduce((a, b) => a + b, 0);

  const load = useCallback(async () => {
    try {
      const [b, u] = await Promise.all([
        api.get<Batch>(`/v1/staff/batches/${id}`),
        api.get<BatchUnits>(`/v1/staff/batches/${id}/units`),
      ]);
      setBatch(b);
      setCounts(u.counts_by_lifecycle);
      setStepCounts(u.counts_by_step);
      setUnitsReady(u.units_ready);
      setUnitsScanned(u.units_scan_verified);
      setUnits(u.units);
      setPrintJobs(await api.get<PrintJob[]>(`/v1/staff/batches/${id}/print-jobs`));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not load the batch.");
    }
  }, [id]);

  useEffect(() => { void load(); }, [load]);

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await action();
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  }

  const generate = () =>
    run(async () => {
      const result = await api.post<LabelExport>("/v1/staff/print-jobs", {
        batch: id,
        count: Number(count),
      });
      setExported(result);
    });

  const reopenExport = (printJobId: string) =>
    run(async () => {
      const result = await api.get<LabelExport>(
        `/v1/staff/print-jobs/${printJobId}/export`,
      );
      setExported(result);
      setNotice("Labels reopened. They remain available until the date shown.");
    });

  const reconcile = (printJob: PrintJob) => {
    const printed = window.prompt(
      `How many of the ${printJob.issued_count} labels were printed?`,
      String(printJob.issued_count),
    );
    if (printed === null) return;
    const rejected = window.prompt("How many were rejected or destroyed?", "0");
    if (rejected === null) return;
    void run(async () => {
      await api.post(`/v1/staff/print-jobs/${printJob.id}/reconcile`, {
        printed: Number(printed),
        rejected: Number(rejected),
      });
      setNotice(
        "Reconciled. The stored labels will be deleted within 24 hours; " +
          "download them now if you still need them.",
      );
    });
  };

  const recordStep = () =>
    run(async () => {
      // Against the batch rather than the units on screen: the table holds at
      // most 500, and recording only those would leave a larger run silently
      // half done.
      if (totalUnits === 0) {
        throw new ApiError(400, "NO_UNITS", "No units to record against.");
      }
      const result = await api.post<{ recorded: number; rejected: unknown[] }>(
        "/v1/staff/manufacturing-confirmations",
        {
          batch: id,
          step,
          completed_at: new Date(completedAt).toISOString(),
          source_reference: sourceReference,
        },
      );
      setNotice(
        `Recorded ${result.recorded} unit(s). ${result.rejected.length} not applicable in their current state.`,
      );
    });

  const activate = () =>
    run(async () => {
      const result = await api.post<ActivationJob>("/v1/staff/activation-jobs", { batch: id });
      setJob(result);
    });

  const blockUnit = (unit: Unit) => {
    const reason = window.prompt(
      `Block ${unit.external_reference}?\n\n` +
        'A blocked unit cannot record a first verification. Verifications ' +
        'already recorded remain in the record.\n\nReason:',
    );
    if (!reason) return;
    void run(async () => {
      await api.post(`/v1/staff/units/${unit.id}/block`, { reason });
      setNotice(`${unit.external_reference} blocked.`);
    });
  };

  const retryFailures = () =>
    run(async () => {
      if (!job) return;
      const result = await api.post<ActivationJob>(
        `/v1/staff/activation-jobs/${job.id}/retry`,
      );
      setJob(result);
      setNotice(
        `Retried ${result.requested} previously failed unit(s): ` +
          `${result.succeeded} activated, ${result.failed} still failing.`,
      );
    });

  const recall = () =>
    run(async () => {
      await api.post(`/v1/staff/batches/${id}/recall`, { notice: recallNotice });
      setNotice("Recall published.");
    });

  if (!batch) {
    return <>{error ? <div className="alert error">{error}</div> : <p className="muted">Loading…</p>}</>;
  }

  const downloadExport = () => {
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
      <h1>{batch.batch_number}</h1>
      <p className="muted">
        {batch.product_brand} · manufactured {batch.manufactured_on} · expires{" "}
        {batch.expires_on}
      </p>

      {batch.is_recalled && (
        <div className="alert error">
          This batch is recalled. Units cannot record a first verification.
          Verifications that already happened remain in the record.
        </div>
      )}
      {error && <div className="alert error">{error}</div>}
      {notice && <div className="alert success">{notice}</div>}

      <h2>Units</h2>
      <div className="grid">
        {Object.entries(counts).map(([lifecycle, n]) => (
          <div className="stat" key={lifecycle}>
            <div className="value">{n}</div>
            <div className="label">{lifecycle.toLowerCase().replace("_", " ")}</div>
          </div>
        ))}
        {Object.keys(counts).length === 0 && (
          <p className="muted">No units generated yet.</p>
        )}
      </div>

      <h2>1 · Generate labels</h2>
      <div className="card">
        <p className="muted" style={{ marginTop: 0 }}>
          One QR per strip. Printing happens outside this system; the sheet
          below is what you send to the printer.
        </p>
        <p className="muted">
          The codes stay available from <em>Label runs</em> below until you
          reconcile the job, and for 24 hours after that. Only a hash of each
          code is kept permanently, so once the export is deleted the codes
          cannot be recovered — replacing lost labels then means voiding those
          units and issuing new ones, which leaves a record.
        </p>
        <div className="row">
          <label>
            <span>How many strips</span>
            <input type="number" min={1} value={count} onChange={(e) => setCount(e.target.value)} />
          </label>
          <div className="shrink">
            <button onClick={generate} disabled={busy || batch.is_recalled}>
              Generate
            </button>
          </div>
        </div>

        {exported && (
          <div className="alert info" style={{ marginTop: "1rem" }}>
            <strong>{exported.export_notice}</strong>
            <p style={{ margin: "0.5rem 0" }}>
              {exported.label_export.length} label(s) generated. Print them now,
              or save the sheet somewhere controlled.
            </p>

            <div className="row" style={{ marginBottom: "0.75rem" }}>
              <label style={{ maxWidth: 200 }}>
                <span>Label footprint</span>
                <select
                  value={labelSizeMm}
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
                <button className="secondary" onClick={downloadExport}>
                  Download CSV of references
                </button>
              </div>
            </div>

            <LabelSheet
              entries={exported.label_export}
              batchNumber={batch.batch_number}
              sizeMm={labelSizeMm}
            />
          </div>
        )}
      </div>

      <h2>Label runs</h2>
      <div className="card">
        {printJobs.length === 0 ? (
          <p className="muted" style={{ margin: 0 }}>
            No labels generated for this batch yet.
          </p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Generated</th><th>Units</th><th>Status</th>
                <th>Labels</th><th></th>
              </tr>
            </thead>
            <tbody>
              {printJobs.map((p) => (
                <tr key={p.id}>
                  <td className="muted">
                    {new Date(p.created_at).toLocaleString()}
                  </td>
                  <td>{p.issued_count}</td>
                  <td>
                    <span className="badge">{p.status.toLowerCase()}</span>
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
                      <>
                        <button onClick={() => reopenExport(p.id)} disabled={busy}>
                          Show labels
                        </button>{" "}
                      </>
                    )}
                    {!p.reconciled_at && (
                      <button
                        className="secondary"
                        onClick={() => reconcile(p)}
                        disabled={busy}
                      >
                        Reconcile
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <h2>2 · Scan the printed codes</h2>
      <PrintScanner
        batchId={id}
        scanned={unitsScanned}
        total={totalUnits}
        onProgress={(p) => {
          setUnitsScanned(p.units_scan_verified);
          setUnitsReady(p.units_ready);
        }}
      />

      <h2>3 · Record QC and coating</h2>
      <div className="card">
        <div className="alert info" style={{ marginTop: 0 }}>
          These are operational records entered by your staff, not scan evidence
          captured by this system — only the print scan above is that. Both the
          completion time you enter and the time it was entered are stored.
        </div>
        {totalUnits > 0 && (
          <div className="grid" style={{ marginBottom: "1rem" }}>
            {STEPS.map((s) => (
              <div className="stat" key={s.value}>
                <div className="value">
                  {stepCounts[s.value] ?? 0}
                  <span className="muted" style={{ fontSize: "0.95rem" }}>
                    {" "}/ {totalUnits}
                  </span>
                </div>
                <div className="label">
                  {s.label} recorded
                  {s.value === "PRINTED" && unitsScanned > 0 && (
                    <>
                      {" "}— {unitsScanned} from a scan, the rest asserted
                    </>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
        <div className="row">
          <label>
            <span>Step</span>
            <select value={step} onChange={(e) => setStep(e.target.value)}>
              {STEPS.map((s) => (
                <option key={s.value} value={s.value}>{s.label}</option>
              ))}
            </select>
          </label>
          <label>
            <span>Actually completed at</span>
            <input
              type="datetime-local"
              value={completedAt}
              onChange={(e) => setCompletedAt(e.target.value)}
            />
          </label>
          <label>
            <span>Source record reference</span>
            <input
              value={sourceReference}
              onChange={(e) => setSourceReference(e.target.value)}
              placeholder="Production log 2026-09-17"
            />
          </label>
          <div className="shrink">
            <button
              onClick={recordStep}
              disabled={busy || !completedAt || !sourceReference || totalUnits === 0}
            >
              Record
            </button>
          </div>
        </div>
      </div>

      <h2>4 · Activate</h2>
      <div className="card">
        {!canRelease ? (
          <p className="muted" style={{ margin: 0 }}>
            Only a release manager can activate units.
          </p>
        ) : (
          <>
            <p className="muted" style={{ marginTop: 0 }}>
              Signs a credential for every unit that has printing, QC and coating
              recorded. Units missing a record stay inactive and are listed below.
            </p>
            <p style={{ margin: "0 0 0.75rem" }}>
              <strong>{unitsReady}</strong> of {totalUnits} unit(s) ready to activate.
              {unitsReady === 0 && totalUnits > 0 && (
                <span className="muted">
                  {" "}Record printing, QC and coating first.
                </span>
              )}
            </p>
            <button
              onClick={activate}
              disabled={busy || batch.is_recalled || unitsReady === 0}
            >
              Activate {unitsReady} unit(s)
            </button>

            {job && (
              <div
                className={`alert ${job.failed > 0 ? "info" : "success"}`}
                style={{ marginTop: "1rem" }}
              >
                <strong>
                  {job.succeeded} activated, {job.failed} failed — {job.status.replace(/_/g, " ").toLowerCase()}
                </strong>
                {job.failed > 0 && (
                  <>
                    <p style={{ margin: "0.5rem 0 0.25rem" }}>
                      This batch is not fully activated.
                    </p>
                    <ul style={{ margin: 0 }}>
                      {job.failures.slice(0, 10).map((f) => (
                        <li key={f.unit_id} className="mono">{f.reason}</li>
                      ))}
                    </ul>
                    <p style={{ margin: "0.75rem 0 0" }}>
                      <button onClick={retryFailures} disabled={busy}>
                        Retry only the failures
                      </button>
                    </p>
                  </>
                )}
              </div>
            )}
          </>
        )}
      </div>

      {canRelease && !batch.is_recalled && (
        <>
          <h2>Recall</h2>
          <div className="card">
            <label>
              <span>Recall notice shown to consumers</span>
              <textarea
                rows={2}
                value={recallNotice}
                onChange={(e) => setRecallNotice(e.target.value)}
              />
            </label>
            <button className="danger" onClick={recall} disabled={busy || !recallNotice}>
              Publish recall
            </button>
          </div>
        </>
      )}

      <h2>Unit list</h2>
      <table>
        <thead>
          <tr><th>Reference</th><th>Lifecycle</th><th>Activated</th><th>Verified</th><th></th></tr>
        </thead>
        <tbody>
          {units.slice(0, 50).map((u) => (
            <tr key={u.id}>
              <td className="mono">{u.external_reference}</td>
              <td>
                <span className={`badge ${lifecycleTone(u.lifecycle)}`}>
                  {u.lifecycle.toLowerCase()}
                </span>
                {u.is_blocked && <span className="badge danger"> blocked</span>}
              </td>
              <td className="muted">{u.activated_at?.slice(0, 10) ?? "—"}</td>
              <td className="muted">{u.redeemed_at?.slice(0, 10) ?? "—"}</td>
              <td>
                {!u.is_blocked && u.lifecycle !== "VOID" && (
                  <button className="danger" onClick={() => blockUnit(u)} disabled={busy}>
                    Block
                  </button>
                )}
              </td>
            </tr>
          ))}
          {units.length === 0 && (
            <tr><td colSpan={5} className="muted">No units yet.</td></tr>
          )}
        </tbody>
      </table>
      {units.length > 50 && (
        <p className="muted">Showing the first 50 of {units.length}.</p>
      )}
    </>
  );
}
