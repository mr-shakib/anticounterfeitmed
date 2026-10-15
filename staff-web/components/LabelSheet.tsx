"use client";

import Link from "next/link";
import { useMemo } from "react";
import JSZip from "jszip";
import { SYMBOL_MODULES, symbolSvg } from "@/lib/labelSymbol.ts";
import { buildSheetPdf } from "@/lib/labelPdf.ts";
import { buildLabelWorkbook } from "@/lib/labelXlsx.ts";
import {
  LABEL_SIZES_MM,
  PAGE_SIZES,
  buildSheetHtml,
  headerText,
  planSheet,
  shortSerial,
  type LabelEntry,
  type LabelLayout,
} from "@/lib/labelPrint.ts";

/**
 * Renders the generated labels as QR codes, and as a print-ready sheet.
 *
 * The codes are drawn in the browser from the symbol data this page already
 * holds, so nothing extra is sent anywhere and the tokens are not written to a
 * server. An ordinary scanner reads only the public URL from these codes; the
 * token is in the symbol where only our own readers look (lib/labelSymbol.ts).
 *
 * Sizing follows docs/11: the footprint includes the four-module quiet zone, and
 * no logo goes inside the symbol. At a 20mm footprint with error correction Q
 * each module is about 0.408mm, which is the smallest and most print-sensitive
 * combination in the matrix -- print at 100% scale and measure one with
 * callipers before committing to a run.
 */

export type { LabelEntry };

const EC_LEVEL = "Q" as const;

export { LABEL_SIZES_MM };

/**
 * How wide one module is at a given footprint, and whether that can be read.
 *
 * The label format fixes the symbol at 49 modules across including the quiet
 * zone, so the footprint alone decides the module size. Below roughly a third of a
 * millimetre a phone camera struggles, and through a scratched coating it stops
 * working altogether -- which is worth knowing before a press run rather than
 * after one.
 */
export function moduleAdvice(sizeMm: number, modules = SYMBOL_MODULES) {
  const mm = sizeMm / modules;
  if (mm >= 0.33) return { mm, level: "ok" as const, note: "Readable." };
  if (mm >= 0.25)
    return {
      mm,
      level: "warn" as const,
      note: "Marginal. Test on the real packaging, after scratching, before committing to a run.",
    };
  if (mm >= 0.2)
    return {
      mm,
      level: "bad" as const,
      note: "Very likely to fail once the coating has been scratched.",
    };
  return {
    mm,
    level: "bad" as const,
    note: "Below what a phone camera can resolve. These labels will not scan.",
  };
}

/** How many to draw on screen. A full run can be thousands; the sheet has all. */
const PREVIEW_LIMIT = 12;

function renderSvg(entry: LabelEntry): string {
  return symbolSvg(entry.qr);
}

/**
 * `layout` is the organization's sheet layout, with the footprint chosen for
 * this run. The preview uses its spacing and shows serials only when the
 * sheet will, so what is on screen is what goes to the printer.
 */
export function LabelSheet({
  entries,
  batchNumber,
  layout,
}: {
  entries: LabelEntry[];
  batchNumber: string;
  layout: LabelLayout;
}) {
  const sizeMm = layout.footprint_mm;
  const preview = useMemo(() => entries.slice(0, PREVIEW_LIMIT), [entries]);
  const svgs = useMemo(() => preview.map(renderSvg), [preview]);
  const plan = useMemo(() => {
    try {
      return planSheet(entries.length, layout);
    } catch {
      return null;
    }
  }, [entries.length, layout]);

  return (
    <div>
      <div
        className="label-grid"
        style={{ gap: `${layout.gap_mm}mm`, justifyContent: "center" }}
      >
        {preview.map((entry, index) => (
          <figure className="label" key={entry.external_reference}>
            <div
              className="label-qr"
              style={{ width: `${sizeMm}mm`, height: `${sizeMm}mm` }}
              dangerouslySetInnerHTML={{ __html: svgs[index] ?? "" }}
            />
            {layout.show_reference && (
              <figcaption className="mono">{shortSerial(entry.external_reference)}</figcaption>
            )}
          </figure>
        ))}
      </div>
      {entries.length > preview.length && (
        <p className="muted">
          Showing {preview.length} of {entries.length}. The printable sheet
          contains all {entries.length}.
        </p>
      )}
      {(() => {
        const advice = moduleAdvice(sizeMm);
        return (
          <div
            className={`alert ${advice.level === "ok" ? "success" : advice.level === "warn" ? "info" : "error"}`}
          >
            <strong>
              {sizeMm}&nbsp;mm footprint &rarr; {advice.mm.toFixed(3)}&nbsp;mm per module
            </strong>
            <p style={{ margin: "0.25rem 0 0" }}>{advice.note}</p>
            <p className="muted" style={{ margin: "0.35rem 0 0", fontSize: "0.85rem" }}>
              Includes the quiet zone, error correction {EC_LEVEL}. Print at 100%
              scale with no fitting, on the real packaging material, and measure
              one label before running the job.
            </p>
          </div>
        );
      })()}
      {plan ? (
        <p className="muted" style={{ fontSize: "0.85rem" }}>
          {PAGE_SIZES[layout.page_size].name}, {layout.page_margin_mm}&nbsp;mm margin,{" "}
          {layout.gap_mm}&nbsp;mm between codes: {plan.perPage} per page ({plan.columns}
          &nbsp;&times;&nbsp;{plan.rows}), {plan.pages.length} page(s).{" "}
          {layout.show_header
            ? `Header on each page: “${headerText(layout, batchNumber, entries.length)}”. `
            : "No header. "}
          {layout.show_reference ? "Serial number under each code. " : "No serial numbers. "}
          <Link href="/settings">Change the layout in Settings.</Link>
        </p>
      ) : (
        <div className="alert error">
          Not even one {sizeMm}&nbsp;mm label fits on the page with the current layout.{" "}
          <Link href="/settings">Change it in Settings.</Link>
        </div>
      )}
      <div className="row" style={{ gap: "0.5rem" }}>
        <div className="shrink">
          <button
            disabled={!plan}
            onClick={() => openPrintableSheet(entries, batchNumber, layout)}
          >
            Open printable sheet
          </button>
        </div>
        <div className="shrink">
          <button
            className="secondary"
            disabled={!plan}
            onClick={() => void downloadSheetPdf(entries, batchNumber, layout)}
          >
            Download sheet (PDF)
          </button>
        </div>
        <div className="shrink">
          <button
            className="secondary"
            disabled={!plan}
            onClick={() => void downloadWorkbook(entries, batchNumber, layout)}
          >
            Download codes (Excel)
          </button>
        </div>
        <div className="shrink">
          <button
            className="secondary"
            disabled={!plan}
            onClick={() => downloadPrintableSheet(entries, batchNumber, layout)}
          >
            Download sheet (HTML)
          </button>
        </div>
        <div className="shrink">
          <button
            className="secondary"
            onClick={() => downloadQrArchive(entries, batchNumber, sizeMm)}
          >
            Download QR codes (ZIP)
          </button>
        </div>
      </div>
    </div>
  );
}

function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

/** Downloads the printable sheet as a single self-contained HTML file. */
export function downloadPrintableSheet(
  entries: LabelEntry[],
  batchNumber: string,
  layout: LabelLayout,
) {
  const html = buildSheetHtml(entries, batchNumber, layout);
  saveBlob(new Blob([html], { type: "text/html" }), `labels-${batchNumber}.html`);
}

/**
 * Downloads the codes as an Excel workbook: one picture per code, one code
 * per row, with its serial under it when the layout shows serials. Never a
 * header or a full reference.
 */
export async function downloadWorkbook(
  entries: LabelEntry[],
  batchNumber: string,
  layout: LabelLayout,
) {
  const bytes = await buildLabelWorkbook(entries, layout);
  saveBlob(
    new Blob([bytes as Uint8Array<ArrayBuffer>], {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }),
    `labels-${batchNumber}.xlsx`,
  );
}

/** Downloads the sheet as a PDF, with its page size and positions fixed. */
export async function downloadSheetPdf(
  entries: LabelEntry[],
  batchNumber: string,
  layout: LabelLayout,
) {
  saveBlob(await buildSheetPdf(entries, batchNumber, layout), `labels-${batchNumber}.pdf`);
}

/**
 * Downloads one SVG per label, zipped.
 *
 * This is the form label software and printers generally want: a file per unit,
 * named by its printed reference, so a run can be laid out without re-deriving
 * anything. SVG rather than PNG because the symbol must stay sharp at whatever
 * size the press uses.
 */
export async function downloadQrArchive(
  entries: LabelEntry[],
  batchNumber: string,
  sizeMm: number,
) {
  const zip = new JSZip();
  const folder = zip.folder(`labels-${batchNumber}`)!;

  const svgs = entries.map(renderSvg);
  entries.forEach((entry, index) => {
    // The mm size is written onto the SVG so the intended footprint travels
    // with the file rather than living only in an instruction someone forgets.
    const sized = svgs[index].replace(
      /<svg([^>]*)>/,
      `<svg$1 width="${sizeMm}mm" height="${sizeMm}mm">`,
    );
    folder.file(`${entry.external_reference}.svg`, sized);
  });

  folder.file(
    "README.txt",
    [
      `Labels for batch ${batchNumber}`,
      `${entries.length} units, ${sizeMm}mm footprint, error correction ${EC_LEVEL}.`,
      "",
      "One SVG per unit, named by its unit reference. The codes carry no text.",
      "The footprint includes the quiet zone. Print at 100% scale, on the real",
      "packaging material, and measure one label before running the job.",
      "Do not place a logo inside a code.",
      "",
      "These codes cannot be regenerated. Keep this archive under the same",
      "controls as the printed labels and destroy it once the job is reconciled.",
    ].join("\n"),
  );

  const blob = await zip.generateAsync({ type: "blob" });
  saveBlob(blob, `labels-${batchNumber}-qr.zip`);
}

/**
 * Opens a print-ready sheet in a new window, for printing straight away.
 */
export function openPrintableSheet(
  entries: LabelEntry[],
  batchNumber: string,
  layout: LabelLayout,
) {
  const win = window.open("", "_blank");
  if (!win) {
    window.alert("Allow pop-ups for this site, or use the download instead.");
    return;
  }
  win.document.write(
    `<!doctype html><title>Labels</title>` +
      `<p style="font:14px system-ui;padding:16px">Rendering ${entries.length} labels…</p>`,
  );

  const html = buildSheetHtml(entries, batchNumber, layout);
  win.document.open();
  win.document.write(html);
  win.document.close();
}
