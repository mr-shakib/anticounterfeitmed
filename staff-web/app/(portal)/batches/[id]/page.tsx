"use client";

import Link from "next/link";
import { use, useCallback, useEffect, useRef, useState } from "react";
import { ActivationJob, ApiError, Batch, BatchUnits, PrintJob, api } from "@/lib/api";
import {
  batchStage,
  openingTab,
  outstanding,
  stepStates,
  type StageInput,
  type TabKey,
} from "@/lib/batchStage.ts";
import { useSession } from "@/components/Session";
import { Stepper } from "@/components/batch/Stepper";
import { LabelsStep } from "@/components/batch/LabelsStep";
import { PrintingStep } from "@/components/batch/PrintingStep";
import { QcStep } from "@/components/batch/QcStep";
import { ActivateStep } from "@/components/batch/ActivateStep";
import { UnitsPanel } from "@/components/batch/UnitsPanel";
import { RecallPanel } from "@/components/batch/RecallPanel";

type Summary = Omit<BatchUnits, "units">;

/**
 * One batch, one step at a time.
 *
 * This page used to show every stage at once -- labels, scanning, QC,
 * activation, recall and the unit list -- whatever state the batch was in, so
 * nothing said what to do next. It now opens on the step with the earliest
 * outstanding work and shows only that step, with the others a click away.
 */
export default function BatchDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const { membership } = useSession();
  const canRelease = membership?.role === "RELEASE_MANAGER";

  const [batch, setBatch] = useState<Batch | null>(null);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [printJobs, setPrintJobs] = useState<PrintJob[]>([]);
  const [jobs, setJobs] = useState<ActivationJob[]>([]);
  const [error, setError] = useState("");
  const [tab, setTab] = useState<TabKey | null>(null);

  const load = useCallback(async () => {
    try {
      const [b, u, p, j] = await Promise.all([
        api.get<Batch>(`/v1/staff/batches/${id}`),
        // Counts only; the unit list pages through its own requests.
        api.get<BatchUnits>(`/v1/staff/batches/${id}/units?limit=1`),
        api.get<PrintJob[]>(`/v1/staff/batches/${id}/print-jobs`),
        api.get<ActivationJob[]>(`/v1/staff/batches/${id}/activation-jobs`),
      ]);
      setBatch(b);
      setSummary(u);
      setPrintJobs(p);
      setJobs(j);
      setError("");
      // Chosen once, on arrival. Recomputing it after every action would move
      // the page out from under someone mid-step -- generating labels would
      // jump to printing and take the new labels off the screen.
      const counts = u.counts_by_lifecycle;
      setTab(
        (chosen) =>
          chosen ??
          openingTab(
            {
              isRecalled: b.is_recalled,
              total: Object.values(counts).reduce((a, c) => a + c, 0),
              counts,
              ready: u.units_ready,
            },
            canRelease,
          ),
      );
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not load the batch.");
    }
  }, [id, canRelease]);

  useEffect(() => { void load(); }, [load]);

  // A print line can scan several codes a second. Refresh once things go
  // quiet rather than four requests per scan.
  const scanTimer = useRef<number | undefined>(undefined);
  const refreshSoon = useCallback(() => {
    window.clearTimeout(scanTimer.current);
    scanTimer.current = window.setTimeout(() => void load(), 800);
  }, [load]);
  useEffect(() => () => window.clearTimeout(scanTimer.current), []);

  if (!batch || !summary) {
    return error ? <div className="alert error">{error}</div> : <p className="muted">Loading…</p>;
  }

  const counts = summary.counts_by_lifecycle;
  const total = Object.values(counts).reduce((a, b) => a + b, 0);
  const input: StageInput = {
    isRecalled: batch.is_recalled,
    total,
    counts,
    ready: summary.units_ready,
  };
  const stage = batchStage(input);
  const showRecall = canRelease && !batch.is_recalled;
  const chosen = tab ?? openingTab(input, canRelease);  // before the first load settles
  // Once a recall is published its tab goes away; land on the units instead.
  const current = chosen === "recall" && !showRecall ? "units" : chosen;

  return (
    <>
      <p className="breadcrumb">
        <Link href="/batches">Batches</Link> / {batch.batch_number}
      </p>
      <div className="title-row">
        <h1>{batch.batch_number}</h1>
        <span className={`badge ${stage.tone}`}>{stage.label}</span>
      </div>
      <p className="muted">
        {batch.product_brand} · manufactured {batch.manufactured_on} · expires{" "}
        {batch.expires_on} · {total} of {batch.planned_unit_count} planned unit(s) issued
      </p>

      {batch.is_recalled && (
        <div className="alert error">
          This batch is recalled. Units cannot record a first verification.
          Verifications that already happened remain in the record.
        </div>
      )}
      {error && <div className="alert error">{error}</div>}

      <Stepper
        active={current}
        states={stepStates(input)}
        outstanding={outstanding(input)}
        showRecall={showRecall}
        onSelect={setTab}
      />

      {current === "labels" && (
        <LabelsStep batch={batch} total={total} printJobs={printJobs} onChanged={load} />
      )}
      {current === "printing" && (
        <PrintingStep
          batchId={id}
          counts={counts}
          total={total}
          scanned={summary.units_scan_verified}
          printJobs={printJobs}
          onChanged={load}
          onScanned={refreshSoon}
        />
      )}
      {current === "qc" && (
        <QcStep
          batch={batch}
          counts={counts}
          stepCounts={summary.counts_by_step}
          total={total}
          onChanged={load}
        />
      )}
      {current === "activate" && (
        <ActivateStep
          batch={batch}
          counts={counts}
          ready={summary.units_ready}
          canRelease={canRelease}
          jobs={jobs}
          onChanged={load}
        />
      )}
      {current === "units" && <UnitsPanel batchId={id} onChanged={load} />}
      {current === "recall" && <RecallPanel batch={batch} onChanged={load} />}
    </>
  );
}
