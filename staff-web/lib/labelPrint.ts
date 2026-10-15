/**
 * Where each label goes on a printed sheet, and the sheet as HTML.
 *
 * One plan drives both the HTML sheet and the PDF (labelPdf.ts), so the two
 * print the same codes in the same places. Positions are in millimetres from
 * the top-left corner of the page, measured on the footprint -- the symbol
 * with its quiet zone.
 *
 * By default a sheet carries the codes and, under each, its short serial
 * (shortSerial). The serials can be turned off, and a header added, in the
 * organization's layout (Settings, served by /v1/staff/label-layout).
 */

import { symbolSvg, type LabelSymbol } from "./labelSymbol.ts";

export type LabelEntry = { external_reference: string; qr: LabelSymbol };

export type PageSize = "A4" | "LETTER";

/** An organization's sheet layout, as /v1/staff/label-layout serves it. */
export type LabelLayout = {
  page_size: PageSize;
  page_margin_mm: number;
  /** Clear space between neighbouring footprints, across and down. */
  gap_mm: number;
  footprint_mm: number;
  show_header: boolean;
  /** `{batch}` and `{count}` are filled in for each run. */
  header_text: string;
  /** Print each code's short serial under it. */
  show_reference: boolean;
};

/** What the server hands out until a layout is saved: codes 15 mm apart, each with its serial. */
export const DEFAULT_LABEL_LAYOUT: LabelLayout = {
  page_size: "A4",
  page_margin_mm: 10,
  gap_mm: 15,
  footprint_mm: 20,
  show_header: false,
  header_text: "",
  show_reference: true,
};

/** Footprints offered, in millimetres; the server accepts the same. */
export const LABEL_SIZES_MM = [5, 8, 10, 12, 15, 20, 25] as const;

export const PAGE_SIZES: Record<PageSize, { width: number; height: number; name: string }> = {
  A4: { width: 210, height: 297, name: "A4" },
  LETTER: { width: 215.9, height: 279.4, name: "US Letter" },
};

/** Space the header takes at the top of each page, when shown. */
export const HEADER_BAND_MM = 8;
/** Between the bottom of a footprint and the top of its serial. */
export const CAPTION_OFFSET_MM = 0.8;
export const HEADER_FONT_PT = 9;
const PT_PER_MM = 72 / 25.4;
/** A monospace digit advances 0.6 em. */
export const MONO_ADVANCE = 0.6;
/** The serial takes at most this share of its code's width... */
const CAPTION_MAX_SHARE = 0.6;
/** ...even at six digits, a batch of 100,000 units or more. */
const CAPTION_MAX_CHARS = 6;
const CAPTION_MAX_PT = 8;

/**
 * The serial printed under a code: the unit's number within its batch, at
 * least four digits. References are `{batch}-{index:06d}`, so 000042 is 0042;
 * it is unique within the batch, not across batches.
 */
export function shortSerial(reference: string): string {
  const match = /-(\d+)$/.exec(reference);
  return match ? String(Number(match[1])).padStart(4, "0") : reference.slice(-5);
}

/**
 * The serial's size for a footprint: up to 8 pt, and small enough that even a
 * six-digit serial is narrower than the code. In half points.
 */
export function captionFontPt(footprintMm: number): number {
  const fit = (CAPTION_MAX_SHARE * footprintMm * PT_PER_MM) / (CAPTION_MAX_CHARS * MONO_ADVANCE);
  return Math.floor(Math.min(CAPTION_MAX_PT, fit) * 2) / 2;
}

/** Space a serial takes under its code, when shown. */
export function captionBandMm(footprintMm: number): number {
  return CAPTION_OFFSET_MM + captionFontPt(footprintMm) / PT_PER_MM + 0.2;
}

const DEFAULT_HEADER = "Batch {batch}";

/** Where one label sits: its footprint's top-left corner, in mm. */
export type Placement = { index: number; x: number; y: number };

export type SheetPlan = {
  width: number;
  height: number;
  /** Where the first column starts; the grid is centred across the page. */
  left: number;
  columns: number;
  rows: number;
  perPage: number;
  pages: Placement[][];
};

/**
 * Lays `count` labels out in a grid, page by page.
 *
 * The grid is centred across the page: the margin is the least space at
 * either side, and whatever a whole column cannot use is split evenly between
 * the two. A short last row keeps to the same columns. Neighbouring footprints
 * are exactly `gap_mm` apart across, and down when no serials are shown; a
 * serial sits in its own label's cell, so the gap is measured from the bottom
 * of the serial to the next code. Throws when not even one label fits.
 */
export function planSheet(count: number, layout: LabelLayout): SheetPlan {
  const { width, height } = PAGE_SIZES[layout.page_size];
  const size = layout.footprint_mm;
  const gap = layout.gap_mm;
  const margin = layout.page_margin_mm;
  const top = margin + (layout.show_header ? HEADER_BAND_MM : 0);
  const cellHeight = size + (layout.show_reference ? captionBandMm(size) : 0);
  // Tolerates the float error in, say, 5 * 35 - 15 against 190.
  const slack = 1e-6;

  const columns = Math.floor((width - 2 * margin + gap + slack) / (size + gap));
  const rows = Math.floor((height - margin - top + gap + slack) / (cellHeight + gap));
  if (columns < 1 || rows < 1) {
    throw new Error(
      "Not even one label fits on the page with this margin, footprint and spacing.",
    );
  }

  const left = (width - (columns * size + (columns - 1) * gap)) / 2;
  const perPage = columns * rows;
  const pages: Placement[][] = [];
  for (let index = 0; index < count; index++) {
    const slot = index % perPage;
    if (slot === 0) pages.push([]);
    pages[pages.length - 1].push({
      index,
      x: left + (slot % columns) * (size + gap),
      y: top + Math.floor(slot / columns) * (cellHeight + gap),
    });
  }
  return { width, height, left, columns, rows, perPage, pages };
}

/** The header line for a run, with its placeholders filled in. */
export function headerText(layout: LabelLayout, batchNumber: string, count: number): string {
  return (layout.header_text.trim() || DEFAULT_HEADER)
    .replaceAll("{batch}", batchNumber)
    .replaceAll("{count}", String(count));
}

export function escapeHtml(text: string): string {
  return text
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

const mm = (value: number) => `${Number(value.toFixed(3))}mm`;

/**
 * The print-ready sheet as a standalone HTML document.
 *
 * Self-contained: the QR codes are inline SVG, so the file prints correctly
 * from any machine with no network and nothing else to copy alongside it.
 *
 * Each page is drawn at its full paper size and the printed page itself has no
 * margin, so the margin is the layout's own and the browser has nowhere to put
 * its date, address and page number. Everything that reaches the page from a
 * person -- batch number, serials, header -- is escaped: the sheet opens in a
 * window belonging to the portal.
 */
export function buildSheetHtml(
  entries: LabelEntry[],
  batchNumber: string,
  layout: LabelLayout,
): string {
  const plan = planSheet(entries.length, layout);
  const size = layout.footprint_mm;
  const header = layout.show_header
    ? `<div class="head" style="left:${mm(plan.left)};top:${mm(layout.page_margin_mm)}">` +
      `${escapeHtml(headerText(layout, batchNumber, entries.length))}</div>`
    : "";

  const pages = plan.pages
    .map((page) => {
      const labels = page
        .map(({ index, x, y }) => {
          const code =
            `<div class="qr" style="left:${mm(x)};top:${mm(y)}">` +
            `${symbolSvg(entries[index].qr)}</div>`;
          const serial = layout.show_reference
            ? `<div class="ref" style="left:${mm(x + size / 2)};top:${mm(y + size + CAPTION_OFFSET_MM)}">` +
              `${escapeHtml(shortSerial(entries[index].external_reference))}</div>`
            : "";
          return code + serial;
        })
        .join("");
      return `<section class="page">${header}${labels}</section>`;
    })
    .join("\n");

  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Labels — ${escapeHtml(batchNumber)}</title>
<style>
  @page { size: ${mm(plan.width)} ${mm(plan.height)}; margin: 0; }
  html, body { margin: 0; padding: 0; background: #fff; }
  /* A hair short of the paper, so rounding cannot spill a blank page. */
  .page { position: relative; width: ${mm(plan.width)}; height: calc(${mm(plan.height)} - 0.2mm);
          overflow: hidden; break-after: page; background: #fff; }
  .page:last-child { break-after: auto; }
  .qr { position: absolute; width: ${mm(size)}; height: ${mm(size)}; }
  .qr svg { display: block; width: 100%; height: 100%; }
  .ref { position: absolute; transform: translateX(-50%); white-space: nowrap; color: #000;
         font: ${captionFontPt(size)}pt/1 ui-monospace, Menlo, Consolas, monospace; }
  .head { position: absolute; white-space: nowrap; color: #000;
          font: ${HEADER_FONT_PT}pt/1 system-ui, Helvetica, Arial, sans-serif; }
  @media screen {
    body { background: #e5e5e5; padding: 10mm 0; }
    .page { margin: 0 auto 10mm; box-shadow: 0 1px 4px rgba(0, 0, 0, 0.3); }
  }
</style>
</head>
<body>
${pages}
</body>
</html>`;
}
