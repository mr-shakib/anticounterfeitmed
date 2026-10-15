"use client";

import type { StepKey, StepState, TabKey } from "@/lib/batchStage.ts";

const STEPS: { key: StepKey; label: string }[] = [
  { key: "labels", label: "Labels" },
  { key: "printing", label: "Printing" },
  { key: "qc", label: "QC & coating" },
  { key: "activate", label: "Activate" },
];

/**
 * The four steps of a batch, each marked done, in progress, or not reached,
 * plus the two places that are not steps: the unit list and the recall.
 */
export function Stepper({
  active,
  states,
  outstanding,
  showRecall,
  onSelect,
}: {
  active: TabKey;
  states: Record<StepKey, StepState>;
  outstanding: Record<StepKey, number>;
  showRecall: boolean;
  onSelect: (tab: TabKey) => void;
}) {
  return (
    <nav className="stepper" aria-label="Batch steps">
      <ol className="steps">
        {STEPS.map((step, index) => {
          const state = states[step.key];
          return (
            <li key={step.key}>
              <button
                type="button"
                className={`step ${state} ${active === step.key ? "selected" : ""}`}
                aria-current={active === step.key ? "step" : undefined}
                onClick={() => onSelect(step.key)}
              >
                <span className="step-number" aria-hidden>
                  {state === "done" ? "✓" : index + 1}
                </span>
                <span className="step-text">
                  <span className="step-label">{step.label}</span>
                  <span className="step-status">
                    {state === "done"
                      ? "Done"
                      : state === "current"
                        ? step.key === "labels"
                          ? "Start here"
                          : `${outstanding[step.key]} to do`
                        : "Not yet"}
                  </span>
                </span>
              </button>
            </li>
          );
        })}
      </ol>
      <div className="step-extras">
        <button
          type="button"
          className={`tab ${active === "units" ? "selected" : ""}`}
          onClick={() => onSelect("units")}
        >
          Units
        </button>
        {showRecall && (
          <button
            type="button"
            className={`tab ${active === "recall" ? "selected" : ""}`}
            onClick={() => onSelect("recall")}
          >
            Recall
          </button>
        )}
      </div>
    </nav>
  );
}
