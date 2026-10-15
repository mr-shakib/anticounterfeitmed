/**
 * The printed sheet: where the codes go, and that nothing else is on it.
 *
 * Run with `npm test`. The PDF check reads the drawing back out of the file and
 * decodes the first symbol, so a slip in the geometry fails here rather than
 * on a press.
 */

import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";

import {
  DEFAULT_LABEL_LAYOUT,
  buildSheetHtml,
  planSheet,
  type LabelEntry,
  type LabelLayout,
} from "./labelPrint.ts";
import { buildSheetPdf, pdfString } from "./labelPdf.ts";
import { PUBLIC_URL, SYMBOL_MODULES } from "./labelSymbol.ts";
import { decodeFrame } from "./readLabel.ts";
import { readScan } from "./scanned.ts";

const VECTORS = join(import.meta.dirname, "../../crypto-vectors/label");
const valid = readdirSync(VECTORS)
  .filter((f) => f.endsWith(".json"))
  .map((f) => JSON.parse(readFileSync(join(VECTORS, f), "utf8")))
  .find((v) => v.name === "valid-label");

const entries = (count: number): LabelEntry[] =>
  Array.from({ length: count }, (_, i) => ({
    external_reference: `REF-${String(i).padStart(5, "0")}`,
    qr: { version: 6, error_correction: "Q", data_codewords: valid.data_codewords },
  }));

const withText: LabelLayout = {
  ...DEFAULT_LABEL_LAYOUT,
  show_header: true,
  header_text: "Batch {batch} — {count} labels",
  show_reference: true,
};

test("the defaults match the server's", () => {
  // Pinned on the other side in backend/tests/test_label_layout.py.
  assert.deepEqual(DEFAULT_LABEL_LAYOUT, {
    page_size: "A4",
    page_margin_mm: 10,
    gap_mm: 15,
    footprint_mm: 20,
    show_header: false,
    header_text: "",
    show_reference: false,
  });
});

/** Clear space between two labels' cells; the larger of the two axes. */
function clearance(a: { x: number; y: number }, b: { x: number; y: number }, w: number, h: number) {
  const across = Math.max(a.x, b.x) - Math.min(a.x, b.x) - w;
  const down = Math.max(a.y, b.y) - Math.min(a.y, b.y) - h;
  return Math.max(across, down);
}

for (const layout of [
  DEFAULT_LABEL_LAYOUT,
  withText,
  { ...DEFAULT_LABEL_LAYOUT, page_size: "LETTER" as const, footprint_mm: 12, gap_mm: 22.5 },
]) {
  test(`codes keep their distance and stay inside the margins (${JSON.stringify(layout)})`, () => {
    const plan = planSheet(200, layout);
    const size = layout.footprint_mm;
    const cell = size + (layout.show_reference ? 3 : 0);

    assert.equal(plan.pages.flat().length, 200);
    const right = Math.max(...plan.pages[0].map((p) => p.x)) + size;
    assert.ok(Math.abs(plan.left - (plan.width - right)) < 1e-9, "centred across the page");
    for (const page of plan.pages) {
      for (const [i, a] of page.entries()) {
        assert.ok(a.x >= layout.page_margin_mm - 1e-9);
        assert.ok(a.y >= layout.page_margin_mm - 1e-9);
        assert.ok(a.x + size <= plan.width - layout.page_margin_mm + 1e-9);
        assert.ok(a.y + cell <= plan.height - layout.page_margin_mm + 1e-9);
        for (const b of page.slice(i + 1)) {
          assert.ok(clearance(a, b, size, cell) >= layout.gap_mm - 1e-9, `${a.index}/${b.index}`);
        }
      }
    }
  });
}

test("the default A4 page holds 5 × 8 codes of 20 mm, centred", () => {
  const plan = planSheet(41, DEFAULT_LABEL_LAYOUT);
  assert.equal(plan.columns, 5);
  assert.equal(plan.rows, 8);
  assert.equal(plan.pages.length, 2);
  // 5 codes and 4 gaps span 160 mm of the 210, leaving 25 mm either side.
  assert.equal(plan.left, 25);
  assert.deepEqual(plan.pages[0][1], { index: 1, x: 60, y: 10 });
  // The short last row keeps to the columns rather than re-centring.
  assert.deepEqual(plan.pages[1][0], { index: 40, x: 25, y: 10 });
});

test("a layout with no room for a code is refused", () => {
  assert.throws(() => planSheet(1, { ...DEFAULT_LABEL_LAYOUT, page_margin_mm: 100 }));
});

/** The text a reader of the page would see: everything but markup, styles and symbols. */
function visibleText(html: string) {
  const body = html.slice(html.indexOf("<body>"));
  return body
    .replace(/<svg[\s\S]*?<\/svg>/g, "")
    .replace(/<[^>]+>/g, "")
    .trim();
}

test("by default the HTML sheet carries the codes and nothing else", () => {
  const html = buildSheetHtml(entries(45), "BN-1", DEFAULT_LABEL_LAYOUT);

  assert.equal(visibleText(html), "");
  assert.equal(html.match(/<svg/g)?.length, 45);
  assert.equal(html.match(/class="page"/g)?.length, 2);
  assert.match(html, /@page \{ size: 210mm 297mm; margin: 0; \}/);
});

test("a header and references appear when the layout asks for them", () => {
  const html = buildSheetHtml(entries(45), "BN-1", withText);
  const text = visibleText(html);

  assert.equal(text.split("Batch BN-1 — 45 labels").length - 1, 2, "one header per page");
  assert.match(text, /REF-00000/);
  assert.match(text, /REF-00044/);
});

test("anything a person typed is escaped", () => {
  const evil = "<img src=x onerror=alert(1)>";
  const list = entries(1);
  list[0].external_reference = evil;
  const html = buildSheetHtml(list, evil, { ...withText, header_text: evil + " {batch}" });

  assert.ok(!html.includes(evil));
  assert.ok(html.includes("&lt;img src=x onerror=alert(1)&gt;"));
});

const text = async (blob: Blob) => Buffer.from(await blob.arrayBuffer()).toString("latin1");

test("by default the PDF has no text at all", async () => {
  const pdf = await text(await buildSheetPdf(entries(45), "BN-1", DEFAULT_LABEL_LAYOUT, { compress: false }));

  assert.ok(!/\bTj\b|\bBT\b|\/Font/.test(pdf));
  assert.match(pdf, /\/Count 2 /);
  assert.match(pdf, /\/MediaBox \[0 0 595.276 841.89\]/);
});

test("the PDF prints a header and references when asked", async () => {
  const pdf = await text(await buildSheetPdf(entries(3), "BN-1", withText, { compress: false }));

  assert.ok(pdf.includes(`${pdfString("Batch BN-1 — 3 labels")} Tj`));
  assert.ok(pdf.includes("(REF-00002) Tj"));
});

test("the PDF's cross-reference table points at its objects", async () => {
  for (const compress of [false, true]) {
    const pdf = await text(await buildSheetPdf(entries(45), "BN-1", withText, { compress }));
    const start = Number(pdf.match(/startxref\n(\d+)/)![1]);
    const rows = pdf.slice(start).match(/^\d{10} 00000 n $/gm)!;
    rows.forEach((row, i) => {
      assert.ok(pdf.startsWith(`${i + 1} 0 obj`, Number(row.slice(0, 10))), `object ${i + 1}`);
    });
    assert.ok(pdf.endsWith("%%EOF\n"));
  }
});

test("a code drawn in the PDF reads as the public URL, and as the token to us", async () => {
  const pdf = await text(await buildSheetPdf(entries(1), "BN-1", DEFAULT_LABEL_LAYOUT, { compress: false }));
  const drawing = pdf.slice(pdf.indexOf("\nq\n"), pdf.indexOf("\nQ"));

  // The footprint is the layout's, in the first column of the centred grid.
  const [scale, flipped, x, y] = drawing
    .match(/([\d.]+) 0 0 -([\d.]+) ([\d.]+) ([\d.]+) cm/)!
    .slice(1)
    .map(Number);
  assert.equal(scale, flipped);
  assert.ok(Math.abs(scale * SYMBOL_MODULES - 20 * (72 / 25.4)) < 0.01);
  assert.ok(Math.abs(x - 25 * (72 / 25.4)) < 0.01);
  assert.ok(Math.abs(y - (297 - 10) * (72 / 25.4)) < 0.01);

  const px = 6;
  const side = SYMBOL_MODULES * px;
  const grey = new Uint8ClampedArray(side * side).fill(255);
  for (const [, c, r, w] of drawing.matchAll(/^(\d+) (\d+) (\d+) 1 re$/gm)) {
    for (let dy = 0; dy < px; dy++) {
      for (let dx = 0; dx < Number(w) * px; dx++) {
        grey[(Number(r) * px + dy) * side + Number(c) * px + dx] = 0;
      }
    }
  }
  const scan = decodeFrame(grey, side, side);

  assert.ok(scan, "the drawn symbol did not decode");
  assert.equal(scan.text, PUBLIC_URL);
  assert.deepEqual(readScan(scan), { kind: "token", token: valid.token });
});

test("text outside the standard fonts prints as a question mark, not as garbage", () => {
  assert.equal(pdfString("a(b)\\ — é ব"), "(a\\(b\\)\\\\ \\227 \\351 ?)");
});
