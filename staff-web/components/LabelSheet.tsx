"use client";

import { useMemo } from "react";
import JSZip from "jszip";
import { SYMBOL_MODULES, symbolSvg, type LabelSymbol } from "@/lib/labelSymbol.ts";

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

export type LabelEntry = { external_reference: string; qr: LabelSymbol };

const EC_LEVEL = "Q" as const;

/** Footprints offered, in millimetres. */
export const LABEL_SIZES_MM = [5, 8, 10, 12, 15, 20, 25] as const;

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

export function LabelSheet({
  entries,
  batchNumber,
  sizeMm,
}: {
  entries: LabelEntry[];
  batchNumber: string;
  sizeMm: number;
}) {
  const preview = useMemo(() => entries.slice(0, PREVIEW_LIMIT), [entries]);
  const svgs = useMemo(() => preview.map(renderSvg), [preview]);

  return (
    <div>
      <div className="label-grid">
        {preview.map((entry, index) => (
          <figure className="label" key={entry.external_reference}>
            <div
              className="label-qr"
              style={{ width: `${sizeMm}mm`, height: `${sizeMm}mm` }}
              dangerouslySetInnerHTML={{ __html: svgs[index] ?? "" }}
            />
            <figcaption className="mono">{entry.external_reference}</figcaption>
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
      <div className="row" style={{ gap: "0.5rem" }}>
        <div className="shrink">
          <button onClick={() => openPrintableSheet(entries, batchNumber, sizeMm)}>
            Open printable sheet
          </button>
        </div>
        <div className="shrink">
          <button
            className="secondary"
            onClick={() => downloadPrintableSheet(entries, batchNumber, sizeMm)}
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

/**
 * Builds the print-ready sheet as a standalone HTML document.
 *
 * Self-contained: the QR codes are inline SVG, so the file prints correctly
 * from any machine with no network and nothing else to copy alongside it.
 */
async function buildSheetHtml(
  entries: LabelEntry[],
  batchNumber: string,
  sizeMm: number,
): Promise<string> {
  const svgs = entries.map(renderSvg);
  const labels = entries
    .map(
      (e, i) =>
        `<figure class="label"><div class="qr">${svgs[i]}</div>` +
        `<figcaption>${e.external_reference}</figcaption></figure>`,
    )
    .join("");

  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Labels — ${batchNumber}</title>
<style>
  @page { size: A4; margin: 10mm; }
  body { font-family: system-ui, sans-serif; margin: 0; color: #000; background: #fff; }
  .head { padding: 0 0 6mm; }
  h1 { font-size: 13pt; margin: 0 0 2mm; }
  .warn { font-size: 9pt; border: 1px solid #000; padding: 2mm; }
  .grid { display: flex; flex-wrap: wrap; gap: 4mm; }
  .label { margin: 0; text-align: center; page-break-inside: avoid; }
  .qr { width: ${sizeMm}mm; height: ${sizeMm}mm; }
  .qr svg { width: 100%; height: 100%; display: block; }
  figcaption { font-family: ui-monospace, monospace; font-size: 6pt; margin-top: 0.8mm; }
</style>
</head>
<body>
  <div class="head">
    <h1>Labels — batch ${batchNumber} — ${entries.length} units</h1>
    <div class="warn">
      <strong>Print at 100% scale.</strong> Turn off &ldquo;fit to page&rdquo; and any
      scaling, then measure one label with callipers before running the job.
      Print on the actual packaging material. Do not add a logo inside a code.
      <br><br>
      These codes are shown once and cannot be regenerated. Keep this file under
      the same controls as the printed labels, and destroy it once the job is
      reconciled.
    </div>
  </div>
  <div class="grid">${labels}</div>
</body>
</html>`;
}

/** Downloads the printable sheet as a single self-contained HTML file. */
export async function downloadPrintableSheet(
  entries: LabelEntry[],
  batchNumber: string,
  sizeMm: number,
) {
  const html = await buildSheetHtml(entries, batchNumber, sizeMm);
  saveBlob(new Blob([html], { type: "text/html" }), `labels-${batchNumber}.html`);
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
      "One SVG per unit, named by the reference printed beside the code.",
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
export async function openPrintableSheet(
  entries: LabelEntry[],
  batchNumber: string,
  sizeMm: number,
) {
  const win = window.open("", "_blank");
  if (!win) {
    window.alert("Allow pop-ups for this site, or use the download instead.");
    return;
  }
  win.document.write(
    `<!doctype html><title>Labels — ${batchNumber}</title>` +
      `<p style="font:14px system-ui;padding:16px">Rendering ${entries.length} labels…</p>`,
  );

  const html = await buildSheetHtml(entries, batchNumber, sizeMm);
  win.document.open();
  win.document.write(html);
  win.document.close();
}
