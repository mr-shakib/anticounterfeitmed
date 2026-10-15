/**
 * Where a batch stands, and what the next piece of work on it is.
 *
 * The batch list and the batch page both answer this from the same counts, so
 * they cannot disagree about which batch is waiting on whom. Kept free of React
 * so it can be tested on its own (`npm test`).
 */

export type StepKey = "labels" | "printing" | "qc" | "activate";
export type TabKey = StepKey | "units" | "recall";

/** done: nothing left here · current: work outstanding · todo: not reached yet. */
export type StepState = "done" | "current" | "todo";

export type StageInput = {
  isRecalled: boolean;
  total: number;
  counts: Record<string, number>;
  ready: number;
};

export type Stage = {
  label: string;
  tone: "" | "ok" | "warn" | "danger";
  /** The step that holds the earliest outstanding work. */
  step: TabKey;
  /** Who acts next: anyone in the manufacturer, or a release manager only. */
  waitingOn: "staff" | "release-manager" | "nobody";
};

const n = (counts: Record<string, number>, lifecycle: string) => counts[lifecycle] ?? 0;

export function batchStage({ isRecalled, total, counts, ready }: StageInput): Stage {
  if (isRecalled) {
    return { label: "Recalled", tone: "danger", step: "units", waitingOn: "nobody" };
  }
  if (total === 0) {
    return { label: "Needs labels", tone: "", step: "labels", waitingOn: "staff" };
  }
  if (n(counts, "CREATED") > 0) {
    return { label: "Printing", tone: "warn", step: "printing", waitingOn: "staff" };
  }
  if (n(counts, "PRINTED") > 0) {
    return { label: "Awaiting QC", tone: "warn", step: "qc", waitingOn: "staff" };
  }
  if (n(counts, "QC_PASSED") > 0) {
    return { label: "Awaiting coating", tone: "warn", step: "qc", waitingOn: "staff" };
  }
  if (ready > 0) {
    return {
      label: "Ready to activate",
      tone: "warn",
      step: "activate",
      waitingOn: "release-manager",
    };
  }
  if (n(counts, "ACTIVE") + n(counts, "REDEEMED") > 0) {
    return { label: "Activated", tone: "ok", step: "activate", waitingOn: "nobody" };
  }
  return { label: "Nothing to activate", tone: "", step: "units", waitingOn: "nobody" };
}

/** Units still to be dealt with at each step; the badge on each step tab. */
export function outstanding({ total, counts, ready }: StageInput): Record<StepKey, number> {
  return {
    labels: total === 0 ? 1 : 0,
    printing: n(counts, "CREATED"),
    qc: n(counts, "PRINTED") + n(counts, "QC_PASSED"),
    activate: ready,
  };
}

export function stepStates(input: StageInput): Record<StepKey, StepState> {
  const left = outstanding(input);
  const { total, counts } = input;
  const beyondQc = n(counts, "COVERED") + n(counts, "ACTIVE") + n(counts, "REDEEMED");
  const reached: Record<StepKey, boolean> = {
    labels: total > 0,
    printing: total - n(counts, "CREATED") > 0,
    qc: beyondQc > 0,
    activate: n(counts, "ACTIVE") + n(counts, "REDEEMED") > 0,
  };
  const state = (step: StepKey): StepState =>
    left[step] > 0 ? "current" : reached[step] ? "done" : "todo";
  return {
    labels: state("labels"),
    printing: state("printing"),
    qc: state("qc"),
    activate: state("activate"),
  };
}

/**
 * The tab a batch page opens on. A release manager with units ready goes
 * straight to activation; everyone else to the earliest unfinished work.
 */
export function openingTab(input: StageInput, canRelease: boolean): TabKey {
  if (canRelease && input.ready > 0 && !input.isRecalled) return "activate";
  return batchStage(input).step;
}
