/**
 * The batch list and the batch page both decide "what is next" from here.
 *
 * Run with `npm test`.
 */

import assert from "node:assert/strict";
import { test } from "node:test";

import { batchStage, openingTab, outstanding, stepStates } from "./batchStage.ts";

const base = { isRecalled: false, total: 0, counts: {}, ready: 0 };

test("a batch with no units needs labels", () => {
  const stage = batchStage(base);
  assert.equal(stage.label, "Needs labels");
  assert.equal(stage.step, "labels");
  assert.deepEqual(stepStates(base), {
    labels: "current", printing: "todo", qc: "todo", activate: "todo",
  });
});

test("the earliest unfinished work decides the stage", () => {
  const mixed = {
    ...base,
    total: 10,
    counts: { CREATED: 2, PRINTED: 3, COVERED: 5 },
    ready: 5,
  };
  assert.equal(batchStage(mixed).label, "Printing");
  assert.deepEqual(stepStates(mixed), {
    labels: "done", printing: "current", qc: "current", activate: "current",
  });
  assert.deepEqual(outstanding(mixed), { labels: 0, printing: 2, qc: 3, activate: 5 });
});

test("printed units wait on QC, then coating", () => {
  assert.equal(batchStage({ ...base, total: 4, counts: { PRINTED: 4 } }).label, "Awaiting QC");
  assert.equal(
    batchStage({ ...base, total: 4, counts: { QC_PASSED: 4 } }).label,
    "Awaiting coating",
  );
});

test("ready units wait on a release manager", () => {
  const ready = { ...base, total: 4, counts: { COVERED: 4 }, ready: 4 };
  const stage = batchStage(ready);
  assert.equal(stage.label, "Ready to activate");
  assert.equal(stage.waitingOn, "release-manager");
});

test("a release manager opens on activation when anything is ready", () => {
  const input = { ...base, total: 4, counts: { CREATED: 1, COVERED: 3 }, ready: 3 };
  assert.equal(openingTab(input, true), "activate");
  assert.equal(openingTab(input, false), "printing");
});

test("a finished batch is activated, and a recalled one says so first", () => {
  const done = { ...base, total: 3, counts: { ACTIVE: 2, VOID: 1 } };
  assert.equal(batchStage(done).label, "Activated");
  assert.equal(stepStates(done).activate, "done");
  assert.equal(batchStage({ ...done, isRecalled: true }).label, "Recalled");
  assert.equal(openingTab({ ...done, isRecalled: true, ready: 2 }, true), "units");
});

test("covered units that are blocked are not counted as ready", () => {
  const blocked = { ...base, total: 2, counts: { COVERED: 2 }, ready: 0 };
  assert.equal(batchStage(blocked).label, "Nothing to activate");
});
