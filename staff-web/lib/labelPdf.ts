/**
 * The label sheet as a PDF, written in the browser.
 *
 * Same plan as the HTML sheet (labelPrint.ts), but the page size, positions
 * and footprints are fixed in the file, and nothing the browser would add on
 * printing -- date, address, page numbers -- can reach it. The codes are
 * vector rectangles, one path per symbol, so they stay sharp at any size.
 *
 * Text appears only when the layout asks for a header or references, in the
 * PDF standard fonts (nothing embedded), so it is limited to the Latin
 * characters those fonts carry; anything else prints as "?".
 *
 * The catalog asks viewers not to scale the page when printing. Acrobat
 * honours that; other viewers may still need "Actual size" choosing.
 */

import { QUIET_ZONE, SYMBOL_MODULES, symbolModules } from "./labelSymbol.ts";
import {
  CAPTION_FONT_PT,
  CAPTION_OFFSET_MM,
  HEADER_FONT_PT,
  headerText,
  planSheet,
  type LabelEntry,
  type LabelLayout,
} from "./labelPrint.ts";

const PT_PER_MM = 72 / 25.4;
/** Courier advances every glyph by 0.6 em, so a reference's width is exact. */
const COURIER_ADVANCE = 0.6;

/** WinAnsi codes for the characters outside Latin-1 that a header is likely to use. */
const WIN_ANSI: Record<string, number> = {
  "€": 0x80, "…": 0x85, "‘": 0x91, "’": 0x92, "“": 0x93, "”": 0x94,
  "•": 0x95, "–": 0x96, "—": 0x97, "™": 0x99,
};

const num = (value: number) => {
  const text = value.toFixed(3).replace(/\.?0+$/, "");
  return text === "-0" ? "0" : text;
};

/** A PDF string literal in WinAnsi, kept to ASCII with octal escapes. */
export function pdfString(text: string): string {
  let out = "(";
  for (const char of text) {
    const code = WIN_ANSI[char] ?? char.codePointAt(0)!;
    if (char === "\\" || char === "(" || char === ")") out += "\\" + char;
    else if (code >= 0x20 && code < 0x7f) out += char;
    else if ((code >= 0xa0 && code <= 0xff) || char in WIN_ANSI) {
      out += "\\" + code.toString(8).padStart(3, "0");
    } else out += "?";
  }
  return out + ")";
}

/**
 * Draws one symbol, footprint included, with its top-left corner at (x, y) mm.
 *
 * The transform puts module (0, 0) at that corner with y running down the
 * page, so each run of dark modules in a row is one rectangle in module units.
 */
function symbolOps(modules: boolean[][], x: number, y: number, sizeMm: number, pageHeightPt: number) {
  const scale = (sizeMm / SYMBOL_MODULES) * PT_PER_MM;
  const ops = [
    "q",
    `${num(scale)} 0 0 ${num(-scale)} ${num(x * PT_PER_MM)} ${num(pageHeightPt - y * PT_PER_MM)} cm`,
    `1 g 0 0 ${SYMBOL_MODULES} ${SYMBOL_MODULES} re f`,
    "0 g",
  ];
  modules.forEach((row, r) => {
    for (let c = 0; c < row.length; ) {
      if (!row[c]) {
        c++;
        continue;
      }
      const start = c;
      while (c < row.length && row[c]) c++;
      ops.push(`${start + QUIET_ZONE} ${r + QUIET_ZONE} ${c - start} 1 re`);
    }
  });
  ops.push("f", "Q");
  return ops.join("\n");
}

function textOps(font: "F1" | "F2", sizePt: number, x: number, baselineFromTop: number, pageHeightPt: number, text: string) {
  return `BT /${font} ${sizePt} Tf ${num(x)} ${num(pageHeightPt - baselineFromTop)} Td ${pdfString(text)} Tj ET`;
}

async function deflate(bytes: Uint8Array<ArrayBuffer>): Promise<Uint8Array<ArrayBuffer>> {
  const stream = new Blob([bytes]).stream().pipeThrough(new CompressionStream("deflate"));
  return new Uint8Array(await new Response(stream).arrayBuffer());
}

const latin1 = (text: string) => {
  const out = new Uint8Array(text.length);
  for (let i = 0; i < text.length; i++) out[i] = text.charCodeAt(i);
  return out;
};

/**
 * Builds the sheet as a PDF.
 *
 * `compress` is on unless the platform lacks CompressionStream; tests turn it
 * off to read the drawing back.
 */
export async function buildSheetPdf(
  entries: LabelEntry[],
  batchNumber: string,
  layout: LabelLayout,
  { compress = typeof CompressionStream !== "undefined" } = {},
): Promise<Blob> {
  const plan = planSheet(entries.length, layout);
  const widthPt = plan.width * PT_PER_MM;
  const heightPt = plan.height * PT_PER_MM;
  const size = layout.footprint_mm;
  const withText = layout.show_header || layout.show_reference;
  const header = headerText(layout, batchNumber, entries.length);

  const chunks: Uint8Array<ArrayBuffer>[] = [];
  const offsets: number[] = [];
  let length = 0;
  const write = (chunk: Uint8Array<ArrayBuffer>) => {
    chunks.push(chunk);
    length += chunk.length;
  };
  const object = (body: string) => {
    offsets.push(length);
    write(latin1(`${offsets.length} 0 obj\n${body}\nendobj\n`));
  };

  // 1 catalog, 2 page tree, 3-4 fonts when there is text, then a page and
  // its content per page.
  const firstPage = withText ? 5 : 3;
  const kids = plan.pages.map((_, i) => `${firstPage + 2 * i} 0 R`).join(" ");

  write(latin1("%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"));
  object("<< /Type /Catalog /Pages 2 0 R /ViewerPreferences << /PrintScaling /None >> >>");
  object(
    `<< /Type /Pages /Kids [${kids}] /Count ${plan.pages.length} ` +
      `/MediaBox [0 0 ${num(widthPt)} ${num(heightPt)}] >>`,
  );
  if (withText) {
    object("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>");
    object("<< /Type /Font /Subtype /Type1 /BaseFont /Courier /Encoding /WinAnsiEncoding >>");
  }

  const resources = withText ? "/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> " : "/Resources << >> ";
  for (let i = 0; i < plan.pages.length; i++) {
    const ops: string[] = [];
    if (layout.show_header) {
      ops.push(
        "0 g",
        textOps(
          "F1", HEADER_FONT_PT, plan.left * PT_PER_MM,
          layout.page_margin_mm * PT_PER_MM + HEADER_FONT_PT * 0.75, heightPt, header,
        ),
      );
    }
    for (const { index, x, y } of plan.pages[i]) {
      ops.push(symbolOps(symbolModules(entries[index].qr), x, y, size, heightPt));
      if (layout.show_reference) {
        const reference = entries[index].external_reference;
        const textWidth = [...reference].length * COURIER_ADVANCE * CAPTION_FONT_PT;
        ops.push(
          "0 g",
          textOps(
            "F2", CAPTION_FONT_PT, (x + size / 2) * PT_PER_MM - textWidth / 2,
            (y + size + CAPTION_OFFSET_MM) * PT_PER_MM + CAPTION_FONT_PT * 0.75, heightPt, reference,
          ),
        );
      }
    }

    object(`<< /Type /Page /Parent 2 0 R ${resources}/Contents ${firstPage + 2 * i + 1} 0 R >>`);
    let content = latin1(ops.join("\n"));
    if (compress) content = await deflate(content);
    offsets.push(length);
    write(
      latin1(
        `${offsets.length} 0 obj\n<< /Length ${content.length}` +
          `${compress ? " /Filter /FlateDecode" : ""} >>\nstream\n`,
      ),
    );
    write(content);
    write(latin1("\nendstream\nendobj\n"));
  }

  const xref = length;
  write(
    latin1(
      `xref\n0 ${offsets.length + 1}\n0000000000 65535 f \n` +
        offsets.map((o) => `${String(o).padStart(10, "0")} 00000 n \n`).join("") +
        `trailer\n<< /Size ${offsets.length + 1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`,
    ),
  );
  return new Blob(chunks, { type: "application/pdf" });
}
