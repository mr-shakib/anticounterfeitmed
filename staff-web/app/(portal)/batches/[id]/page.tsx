"use client";

import { use, useCallback, useEffect, useState } from "react";
import {
  ActivationJob, ApiError, Batch, LabelExport, Unit, api,
} from "@/lib/api";
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
  const [units, setUnits] = useState<Unit[]>([]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);

  const [count, setCount] = useState("100");
  const [exported, setExported] = useState<LabelExport | null>(null);

  const [step, setStep] = useState("PRINTED");
  const [completedAt, setCompletedAt] = useState("");
  const [sourceReference, setSourceReference] = useState("");

  const [job, setJob] = useState<ActivationJob | null>(null);
  const [recallNotice, setRecallNotice] = useState("");

  const load = useCallback(async () => {
    try {
      const [b, u] = await Promise.all([
        api.get<Batch>(`/v1/staff/batches/${id}`),
        api.get<{ counts_by_lifecycle: Record<string, number>; units: Unit[] }>(
          `/v1/staff/batches/${id}/units`,
        ),
      ]);
      setBatch(b);
      setCounts(u.counts_by_lifecycle);
      setUnits(u.units);
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

  const recordStep = () =>
    run(async () => {
      const ids = units
        .filter((u) => !u.is_blocked)
        .map((u) => u.id);
      if (ids.length === 0) throw new ApiError(400, "NO_UNITS", "No units to record against.");
      const result = await api.post<{ recorded: number; rejected: unknown[] }>(
        "/v1/staff/manufacturing-confirmations",
        {
          unit_ids: ids,
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
    const rows = [
      "external_reference,qr_url",
      ...exported.label_export.map((e) => `${e.external_reference},${e.qr_url}`),
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
          One QR per strip. Printing happens outside this system; the export
          below is what you send to the printer.
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
              {exported.label_export.length} label(s) ready.
            </p>
            <button onClick={downloadExport}>Download CSV</button>
          </div>
        )}
      </div>

      <h2>2 · Record manufacturing</h2>
      <div className="card">
        <div className="alert info" style={{ marginTop: 0 }}>
          These are operational records entered by your staff, not scan evidence
          captured by this system. Both the completion time you enter and the
          time it was entered are stored.
        </div>
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
              disabled={busy || !completedAt || !sourceReference || units.length === 0}
            >
              Record
            </button>
          </div>
        </div>
      </div>

      <h2>3 · Activate</h2>
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
            <button onClick={activate} disabled={busy || batch.is_recalled}>
              Activate eligible units
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
