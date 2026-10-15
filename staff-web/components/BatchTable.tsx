"use client";

import Link from "next/link";
import { Batch } from "@/lib/api";
import { batchStage, type StageInput } from "@/lib/batchStage.ts";

export function stageInput(batch: Batch): StageInput {
  const progress = batch.progress;
  return {
    isRecalled: batch.is_recalled,
    total: progress?.units_total ?? 0,
    counts: progress?.counts_by_lifecycle ?? {},
    ready: progress?.units_ready ?? 0,
  };
}

/** Whether a batch is waiting on something this person can do. */
export function waitingOnMe(batch: Batch, canRelease: boolean): boolean {
  const stage = batchStage(stageInput(batch));
  if (stage.waitingOn === "staff") return true;
  if (stage.waitingOn === "release-manager") return canRelease;
  // Earlier work outstanding, but some units are ready already.
  return canRelease && (batch.progress?.units_ready ?? 0) > 0 && !batch.is_recalled;
}

/**
 * Batches with where each one stands, so the list says which batch needs
 * attention instead of only "active" or "recalled".
 */
export function BatchTable({
  batches,
  canRelease,
  showDates = true,
  markMine = true,
}: {
  batches: Batch[];
  canRelease: boolean;
  showDates?: boolean;
  /** Flag rows waiting on this person. Off where the whole table is that. */
  markMine?: boolean;
}) {
  return (
    <table>
      <thead>
        <tr>
          <th>Batch</th>
          <th>Product</th>
          {showDates && <th>Expires</th>}
          <th>Units</th>
          <th>Stage</th>
        </tr>
      </thead>
      <tbody>
        {batches.map((b) => {
          const input = stageInput(b);
          const stage = batchStage(input);
          const active = (input.counts.ACTIVE ?? 0) + (input.counts.REDEEMED ?? 0);
          const mine = markMine && waitingOnMe(b, canRelease);
          return (
            <tr key={b.id} className={mine ? "attention" : undefined}>
              <td><Link href={`/batches/${b.id}`}>{b.batch_number}</Link></td>
              <td>{b.product_brand}</td>
              {showDates && <td className="nowrap">{b.expires_on}</td>}
              <td className="nowrap">
                {input.total === 0 ? (
                  <span className="muted">0 of {b.planned_unit_count} planned</span>
                ) : (
                  <>
                    {active} of {input.total} active
                    <div className="meter" aria-hidden>
                      <span style={{ width: `${(active / input.total) * 100}%` }} />
                    </div>
                  </>
                )}
              </td>
              <td>
                <span className={`badge ${stage.tone}`}>{stage.label}</span>
                {stage.label !== "Ready to activate" && input.ready > 0 && !b.is_recalled && (
                  <> <span className="badge ok">{input.ready} ready</span></>
                )}
                {mine && <span className="attention-note">Waiting on you</span>}
              </td>
            </tr>
          );
        })}
        {batches.length === 0 && (
          <tr><td colSpan={showDates ? 5 : 4} className="muted">No batches yet.</td></tr>
        )}
      </tbody>
    </table>
  );
}
