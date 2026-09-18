"use client";

import { useEffect, useMemo, useState } from "react";
import QRCode from "qrcode";

/**
 * Renders the generated labels as QR codes, and as a print-ready sheet.
 *
 * The codes are drawn in the browser from URLs this page already holds, so
 * nothing extra is sent anywhere and the tokens are not written to a server.
 *
 * Sizing follows docs/11: the footprint includes the four-module quiet zone, and
 * no logo goes inside the symbol. At a 20mm footprint with error correction Q
 * each module is about 0.377mm, which is the smallest and most print-sensitive
 * combination in the matrix -- print at 100% scale and measure one with
 * callipers before committing to a run.
 */

export type LabelEntry = { external_reference: string; qr_url: string };

const EC_LEVEL = "Q" as const;
const QUIET_ZONE_MODULES = 4;

/** How many to draw on screen. A full run can be thousands; the sheet has all. */
const PREVIEW_LIMIT = 12;

async function renderSvg(url: string): Promise<string> {
  return QRCode.toString(url, {
    type: "svg",
    errorCorrectionLevel: EC_LEVEL,
    margin: QUIET_ZONE_MODULES,
  });
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
  const [svgs, setSvgs] = useState<string[]>([]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const rendered = await Promise.all(preview.map((e) => renderSvg(e.qr_url)));
      if (!cancelled) setSvgs(rendered);
    })();
    return () => {
      cancelled = true;
    };
  }, [preview]);

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
      <p className="muted">
        {sizeMm}&nbsp;mm footprint including the quiet zone, error correction{" "}
        {EC_LEVEL}. Print at 100% scale with no fitting, on the real packaging
        material, and measure one label before running the job.
      </p>
      <button onClick={() => openPrintableSheet(entries, batchNumber, sizeMm)}>
        Open printable sheet
      </button>
    </div>
  );
}

/**
 * Opens a print-ready sheet in a new window.
 *
 * A new window rather than a file download: the labels exist only in this
 * page's memory, and printing directly avoids writing thousands of tokens to
 * disk as a side effect of wanting to print them.
 */
export async function openPrintableSheet(
  entries: LabelEntry[],
  batchNumber: string,
  sizeMm: number,
) {
  const win = window.open("", "_blank");
  if (!win) {
    window.alert("Allow pop-ups for this site to open the printable sheet.");
    return;
  }

  win.document.write(
    `<!doctype html><title>Labels — ${batchNumber}</title>` +
      `<p style="font:14px system-ui;padding:16px">Rendering ${entries.length} labels…</p>`,
  );

  const svgs = await Promise.all(entries.map((e) => renderSvg(e.qr_url)));
  const labels = entries
    .map(
      (e, i) =>
        `<figure class="label"><div class="qr">${svgs[i]}</div>` +
        `<figcaption>${e.external_reference}</figcaption></figure>`,
    )
    .join("");

  win.document.open();
  win.document.write(`<!doctype html>
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
  @media print { .warn { border-color: #000; } }
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
</html>`);
  win.document.close();
}
