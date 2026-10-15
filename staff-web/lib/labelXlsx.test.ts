/**
 * The Excel workbook: pictures of the codes, each with its serial, and nothing else.
 *
 * Run with `npm test`. Each picture is decoded back, so a slip in drawing the
 * PNG fails here rather than on a press.
 */

import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";

import JSZip from "jszip";
import {
  CAPTION_OFFSET_MM,
  DEFAULT_LABEL_LAYOUT,
  PAGE_SIZES,
  type LabelEntry,
  type LabelLayout,
} from "./labelPrint.ts";
import { buildLabelWorkbook, columnPixels, planWorkbook } from "./labelXlsx.ts";
import { PUBLIC_URL } from "./labelSymbol.ts";
import { decodeFrame } from "./readLabel.ts";
import { readScan } from "./scanned.ts";

const VECTORS = join(import.meta.dirname, "../../crypto-vectors/label");
const valid = readdirSync(VECTORS)
  .filter((f) => f.endsWith(".json"))
  .map((f) => JSON.parse(readFileSync(join(VECTORS, f), "utf8")))
  .find((v) => v.name === "valid-label");

const entries = (count: number): LabelEntry[] =>
  Array.from({ length: count }, (_, i) => ({
    external_reference: `BN-1-${String(i + 1).padStart(6, "0")}`,
    qr: { version: 6, error_correction: "Q", data_codewords: valid.data_codewords },
  }));

/** A header is for the printed sheet; the workbook never carries one. */
const withText: LabelLayout = {
  ...DEFAULT_LABEL_LAYOUT,
  show_header: true,
  header_text: "Batch {batch}",
  show_reference: true,
};
const codesOnly: LabelLayout = { ...DEFAULT_LABEL_LAYOUT, show_reference: false };

const open = async (layout: LabelLayout, count: number) =>
  JSZip.loadAsync(await buildLabelWorkbook(entries(count), layout));

test("the workbook holds the codes and, in each one's cell, its serial", async () => {
  const zip = await open(withText, 12);
  const sheet = await zip.file("xl/worksheets/sheet1.xml")!.async("string");
  const drawing = await zip.file("xl/drawings/drawing1.xml")!.async("string");
  const styles = await zip.file("xl/styles.xml")!.async("string");
  const cells = [...sheet.matchAll(/<c r="A(\d+)" s="1" t="inlineStr"><is><t>([^<]*)<\/t><\/is><\/c>/g)];

  assert.equal(cells.length, 12);
  assert.equal((sheet.match(/<c[ >]/g) ?? []).length, 12, "no other cell has a value");
  assert.deepEqual(cells.map((m) => [m[1], m[2]]).slice(0, 2), [["1", "0001"], ["2", "0002"]]);
  assert.match(styles, /<font><sz val="8"\/>/);
  assert.match(styles, /<alignment horizontal="center" vertical="bottom"\/>/);
  assert.ok(!/headerFooter|oddHeader/.test(sheet), "no printed header or footer");
  assert.equal(zip.file("xl/sharedStrings.xml"), null);
  assert.ok(!/BN-1-0|Batch/.test(sheet + drawing), "never a header or a full reference");
  assert.equal(drawing.match(/<xdr:pic>/g)?.length, 12);
  assert.equal(zip.file(/^xl\/media\/code\d+\.png$/).length, 12);
});

test("with serials turned off the workbook holds the codes alone", async () => {
  const sheet = await (await open(codesOnly, 12)).file("xl/worksheets/sheet1.xml")!.async("string");
  assert.ok(!/<c[ >]/.test(sheet), "no cell has a value");
});

test("it prints at 100% on the layout's paper", async () => {
  const sheet = await (await open(DEFAULT_LABEL_LAYOUT, 3)).file("xl/worksheets/sheet1.xml")!.async("string");
  assert.match(sheet, /<pageSetup paperSize="9" scale="100" orientation="portrait"\/>/);
  // A 20 mm code centred on 210 mm starts at 95 mm; column A starts half the
  // 15 mm spacing before it, at 87.5 mm.
  assert.match(sheet, /<pageMargins left="3.4449" /);
  assert.match(sheet, /<sheetProtection sheet="1" objects="1"\/>/);

  const letter = await (await open({ ...DEFAULT_LABEL_LAYOUT, page_size: "LETTER" }, 3))
    .file("xl/worksheets/sheet1.xml")!.async("string");
  assert.match(letter, /paperSize="1"/);
});

for (const layout of [
  DEFAULT_LABEL_LAYOUT,
  codesOnly,
  { ...DEFAULT_LABEL_LAYOUT, footprint_mm: 12, gap_mm: 22.5, page_size: "LETTER" as const },
  { ...DEFAULT_LABEL_LAYOUT, footprint_mm: 25, gap_mm: 0, page_margin_mm: 0 },
  { ...DEFAULT_LABEL_LAYOUT, footprint_mm: 5, gap_mm: 15 },
]) {
  test(`one code per row, the spacing apart and centred (${JSON.stringify(layout)})`, async () => {
    const plan = planWorkbook(40, layout);
    const drawing = await (await open(layout, 40)).file("xl/drawings/drawing1.xml")!.async("string");
    const mm = (emu: string) => Number(emu) / 36000;
    const codes = [...drawing.matchAll(
      /<xdr:col>(\d+)<\/xdr:col><xdr:colOff>(\d+)<\/xdr:colOff><xdr:row>(\d+)<\/xdr:row><xdr:rowOff>(\d+)<\/xdr:rowOff>/g,
    )].map(([, col, colOff, row, rowOff]) => ({ col: Number(col), x: mm(colOff), row: Number(row), y: mm(rowOff) }));
    const size = layout.footprint_mm;
    const columnMm = columnPixels(plan.columnWidth) / (96 / 25.4);
    const rowMm = plan.rowHeightPt / (72 / 25.4);

    assert.equal(codes.length, 40);
    assert.equal(columnPixels(plan.columnWidth), plan.columnPx);
    assert.equal(plan.rows, 40);
    for (const [i, code] of codes.entries()) {
      assert.deepEqual([code.col, code.row], [0, i], "column A, one row each");
      assert.ok(Math.abs(code.x - layout.gap_mm / 2) < 1e-4);
      // With a serial under it the code starts a full spacing down, so the
      // spacing runs from one serial to the next code; alone, half of it.
      const top = layout.show_reference ? layout.gap_mm : layout.gap_mm / 2;
      assert.ok(Math.abs(code.y - top) < 1e-4);
      assert.ok(code.x + size <= columnMm + 1e-4, "inside its cell as Excel draws it");
    }
    const band = plan.captionPt ? CAPTION_OFFSET_MM + (plan.captionPt * 1.3 * 25.4) / 72 : 0;
    assert.equal(plan.captionPt !== null, layout.show_reference);
    assert.ok(rowMm - size - band >= layout.gap_mm - 1e-9, "at least the spacing down");
    assert.ok(rowMm - size - band - layout.gap_mm < 25.4 / 96, "never more than a pixel over");

    // Printed, each code is in the middle of the page, at least the layout's
    // margin from the sides; the printable width leaves room for a program
    // that draws the column wider.
    const { width } = PAGE_SIZES[layout.page_size];
    assert.ok(Math.abs(plan.leftMm + codes[0].x + size / 2 - width / 2) < 1e-4, "centred");
    assert.ok(plan.leftMm + codes[0].x >= layout.page_margin_mm - 1e-9);
    if (plan.rightMm > 0) assert.ok(width - plan.leftMm - plan.rightMm >= 1.1 * columnMm - 1e-6);
  });
}

test("the print area covers one row per code", async () => {
  const workbook = await (await open(DEFAULT_LABEL_LAYOUT, 41)).file("xl/workbook.xml")!.async("string");
  assert.match(workbook, /Labels!\$A\$1:\$A\$41</);
});

/** Reads a one-bit greyscale PNG into 0/255 pixels. */
async function readPng(png: Uint8Array) {
  const view = new DataView(png.buffer, png.byteOffset, png.byteLength);
  const width = view.getUint32(16);
  assert.equal(png[24], 1, "bit depth");
  assert.equal(png[25], 0, "greyscale");
  let at = 8;
  const idat: Uint8Array[] = [];
  while (at < png.length) {
    const length = view.getUint32(at);
    const type = String.fromCharCode(...png.subarray(at + 4, at + 8));
    if (type === "IDAT") idat.push(png.subarray(at + 8, at + 8 + length));
    at += 12 + length;
  }
  const stream = new Blob(idat as BlobPart[]).stream().pipeThrough(new DecompressionStream("deflate"));
  const raw = new Uint8Array(await new Response(stream).arrayBuffer());
  const stride = 1 + Math.ceil(width / 8);
  const grey = new Uint8ClampedArray(width * width);
  for (let y = 0; y < width; y++) {
    assert.equal(raw[y * stride], 0, "unfiltered rows");
    for (let x = 0; x < width; x++) {
      grey[y * width + x] = (raw[y * stride + 1 + (x >> 3)] >> (7 - (x & 7))) & 1 ? 255 : 0;
    }
  }
  return { grey, width };
}

test("each picture reads as the public URL, and as the token to us", async () => {
  const zip = await open(DEFAULT_LABEL_LAYOUT, 2);
  for (const file of zip.file(/^xl\/media\/code\d+\.png$/)) {
    const { grey, width } = await readPng(await file.async("uint8array"));
    // 20 mm at 600 dpi or better: 10 pixels to the module.
    assert.equal(width, 49 * 10);
    const scan = decodeFrame(grey, width, width);
    assert.ok(scan, `${file.name} did not decode`);
    assert.equal(scan.text, PUBLIC_URL);
    assert.deepEqual(readScan(scan), { kind: "token", token: valid.token });
  }
});
