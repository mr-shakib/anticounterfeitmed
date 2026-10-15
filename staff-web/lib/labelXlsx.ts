/**
 * The label codes as an Excel workbook: pictures of the codes and, under
 * each, its short serial.
 *
 * Excel cannot make these codes itself -- the token rides after the
 * terminator (labelSymbol.ts), which no spreadsheet function, QR font or
 * add-in produces from text -- so the portal draws each one and the workbook
 * only holds it. The only cell values are the serials, when the layout shows
 * them; never a header or a full reference.
 *
 * One code per row, all in column A: a list to keep, not a page grid. The
 * code is a picture half the spacing in from the cell's left. Its serial is
 * the cell's own text, centred and at the bottom, so it sits under the code;
 * the code then starts a full spacing down, so the spacing runs from one
 * serial to the next code. Without serials the code is half the spacing down
 * instead. Either way a page break never parts a code from its serial, and row
 * heights are rounded up to Excel's pixel step, so the spacing is never less
 * than the layout's.
 *
 * Printed, each code is centred across the page by the left margin rather than
 * the program's own centring, which would follow that program's idea of the
 * column width -- they disagree (LibreOffice draws Excel's widths about 6%
 * wider), but not about a distance in millimetres. The page prints at 100%,
 * and the sheet is protected without a password so a picture cannot be nudged
 * by accident.
 *
 * Written with JSZip, which the portal already ships for the SVG archive.
 */

import JSZip from "jszip";
import { QUIET_ZONE, SYMBOL_MODULES, symbolModules } from "./labelSymbol.ts";
import {
  CAPTION_OFFSET_MM,
  PAGE_SIZES,
  captionFontPt,
  shortSerial,
  type LabelEntry,
  type LabelLayout,
} from "./labelPrint.ts";

const EMU_PER_MM = 36000;
/** Excel's column widths are counted in Calibri 11's digit width, 7 pixels. */
const DIGIT_PX = 7;
const PX_PER_MM = 96 / 25.4;
const PT_PER_MM = 72 / 25.4;
/** A row height is a whole number of pixels: 0.75 pt at 96 dpi. */
const ROW_STEP_PT = 0.75;
/** At least this many dots per inch at the printed footprint. */
const MIN_DPI = 600;
/** A line of Calibri is about 1.22 em tall; a little over, for Excel's padding. */
const LINE_HEIGHT = 1.3;

const PAPER_SIZE = { A4: 9, LETTER: 1 } as const;

export type WorkbookPlan = {
  /** One per code. */
  rows: number;
  /** Column A's width as stored, in Excel's character units. */
  columnWidth: number;
  /** That width as Excel draws it, in pixels. */
  columnPx: number;
  rowHeightPt: number;
  /** Page margins. The left one centres the codes; top and bottom are equal. */
  leftMm: number;
  rightMm: number;
  edgeMm: number;
  /** How far in from its cell's left, and down from its top, each code starts. */
  offsetMm: number;
  topMm: number;
  /** The serial's size, when shown. */
  captionPt: number | null;
};

/** Pixels Excel draws for a stored column width (ECMA-376 §18.3.1.13). */
export function columnPixels(width: number): number {
  return Math.trunc(((256 * width + Math.trunc(128 / DIGIT_PX)) / 256) * DIGIT_PX);
}

/** Room left for a program that draws the column wider than Excel does. */
const COLUMN_SLACK = 1.1;

export function planWorkbook(count: number, layout: LabelLayout): WorkbookPlan {
  const page = PAGE_SIZES[layout.page_size];
  const size = layout.footprint_mm;
  const gap = layout.gap_mm;
  const cellMm = size + gap;
  const captionPt = layout.show_reference ? captionFontPt(size) : null;
  const bandMm = captionPt ? CAPTION_OFFSET_MM + (captionPt * LINE_HEIGHT) / PT_PER_MM : 0;
  const topMm = captionPt ? gap : gap / 2;

  const columnPx = Math.ceil(cellMm * PX_PER_MM - 1e-9);
  const columnWidth = Math.trunc((columnPx * 256) / DIGIT_PX) / 256;
  const rowHeightPt =
    Math.ceil(((cellMm + bandMm) * PT_PER_MM) / ROW_STEP_PT - 1e-9) * ROW_STEP_PT;

  // The code starts half the spacing into column A; this puts it in the
  // middle of the page. The right margin only bounds the column, and is kept
  // small enough that a program drawing it a little wide still fits it.
  const leftMm = Math.max(0, (page.width - size) / 2 - gap / 2);
  const rightMm = Math.max(
    0,
    Math.min(leftMm, page.width - leftMm - (COLUMN_SLACK * columnPx) / PX_PER_MM),
  );
  const edgeMm = Math.max(0, layout.page_margin_mm - topMm);
  if (rowHeightPt / PT_PER_MM > page.height - 2 * edgeMm + 1e-9) {
    throw new Error(
      "Not even one label fits on the page with this margin, footprint and spacing.",
    );
  }
  return {
    rows: Math.max(1, count),
    columnWidth,
    columnPx,
    rowHeightPt,
    leftMm,
    rightMm,
    edgeMm,
    offsetMm: gap / 2,
    topMm,
    captionPt,
  };
}

const CRC_TABLE = Array.from({ length: 256 }, (_, n) => {
  let c = n;
  for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
  return c >>> 0;
});

function crc32(bytes: Uint8Array): number {
  let c = 0xffffffff;
  for (const b of bytes) c = CRC_TABLE[(c ^ b) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}

function pngChunk(type: string, data: Uint8Array): Uint8Array<ArrayBuffer> {
  const out = new Uint8Array(12 + data.length);
  const view = new DataView(out.buffer);
  view.setUint32(0, data.length);
  for (let i = 0; i < 4; i++) out[4 + i] = type.charCodeAt(i);
  out.set(data, 8);
  view.setUint32(8 + data.length, crc32(out.subarray(4, 8 + data.length)));
  return out;
}

async function zlib(bytes: Uint8Array<ArrayBuffer>): Promise<Uint8Array<ArrayBuffer>> {
  const stream = new Blob([bytes]).stream().pipeThrough(new CompressionStream("deflate"));
  return new Uint8Array(await new Response(stream).arrayBuffer());
}

/**
 * A symbol, quiet zone included, as a one-bit greyscale PNG with `scale`
 * pixels to a module, so every module edge falls on a pixel edge.
 */
export async function symbolPng(modules: boolean[][], scale: number): Promise<Uint8Array> {
  const side = (modules.length + 2 * QUIET_ZONE) * scale;
  const stride = 1 + Math.ceil(side / 8);
  const raw = new Uint8Array(stride * side).fill(0xff);

  for (let y = 0; y < side; y++) {
    const row = raw.subarray(y * stride, (y + 1) * stride);
    row[0] = 0; // no filter
    const r = Math.floor(y / scale) - QUIET_ZONE;
    if (r < 0 || r >= modules.length) continue;
    for (let x = 0; x < side; x++) {
      const c = Math.floor(x / scale) - QUIET_ZONE;
      if (c >= 0 && c < modules.length && modules[r][c]) {
        row[1 + (x >> 3)] &= ~(0x80 >> (x & 7)); // 0 is black
      }
    }
  }

  const header = new Uint8Array(13);
  const view = new DataView(header.buffer);
  view.setUint32(0, side);
  view.setUint32(4, side);
  header.set([1, 0, 0, 0, 0], 8); // 1 bit, greyscale, deflate, no filter, no interlace

  const parts = [
    Uint8Array.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    pngChunk("IHDR", header),
    pngChunk("IDAT", await zlib(raw)),
    pngChunk("IEND", new Uint8Array(0)),
  ];
  const out = new Uint8Array(parts.reduce((n, p) => n + p.length, 0));
  let at = 0;
  for (const p of parts) {
    out.set(p, at);
    at += p.length;
  }
  return out;
}

const XML = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n';
const NS_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main";
const NS_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships";
const NS_PKG = "http://schemas.openxmlformats.org/package/2006/relationships";
const REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships";

const inches = (mm: number) => (mm / 25.4).toFixed(4);

const escapeXml = (text: string) =>
  text.replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");

/** Builds the workbook. The caller wraps it in a Blob to save it. */
export async function buildLabelWorkbook(
  entries: LabelEntry[],
  layout: LabelLayout,
): Promise<Uint8Array> {
  const plan = planWorkbook(entries.length, layout);
  const size = layout.footprint_mm;
  // Whole pixels per module, enough for MIN_DPI at the printed footprint.
  const scale = Math.max(8, Math.ceil(((MIN_DPI / 25.4) * size) / SYMBOL_MODULES));
  const zip = new JSZip();

  zip.file(
    "[Content_Types].xml",
    XML +
      '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">' +
      '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>' +
      '<Default Extension="xml" ContentType="application/xml"/>' +
      '<Default Extension="png" ContentType="image/png"/>' +
      '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>' +
      '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' +
      '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>' +
      '<Override PartName="/xl/drawings/drawing1.xml" ContentType="application/vnd.openxmlformats-officedocument.drawing+xml"/>' +
      "</Types>",
  );
  zip.file(
    "_rels/.rels",
    XML +
      `<Relationships xmlns="${NS_PKG}">` +
      `<Relationship Id="rId1" Type="${REL}/officeDocument" Target="xl/workbook.xml"/>` +
      "</Relationships>",
  );

  const lastCell = `$A$${plan.rows}`;
  zip.file(
    "xl/workbook.xml",
    XML +
      `<workbook xmlns="${NS_MAIN}" xmlns:r="${NS_REL}">` +
      '<sheets><sheet name="Labels" sheetId="1" r:id="rId1"/></sheets>' +
      `<definedNames><definedName name="_xlnm.Print_Area" localSheetId="0">Labels!$A$1:${lastCell}</definedName></definedNames>` +
      "</workbook>",
  );
  zip.file(
    "xl/_rels/workbook.xml.rels",
    XML +
      `<Relationships xmlns="${NS_PKG}">` +
      `<Relationship Id="rId1" Type="${REL}/worksheet" Target="worksheets/sheet1.xml"/>` +
      `<Relationship Id="rId2" Type="${REL}/styles" Target="styles.xml"/>` +
      "</Relationships>",
  );
  // Calibri 11 is what the 7-pixel digit width above is measured in. Style 1
  // is the serial: centred, at the bottom of the cell, under the code.
  zip.file(
    "xl/styles.xml",
    XML +
      `<styleSheet xmlns="${NS_MAIN}">` +
      '<fonts count="2"><font><sz val="11"/><name val="Calibri"/><family val="2"/></font>' +
      `<font><sz val="${plan.captionPt ?? 11}"/><name val="Calibri"/><family val="2"/></font></fonts>` +
      '<fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills>' +
      '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>' +
      '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>' +
      '<cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>' +
      '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1" applyAlignment="1">' +
      '<alignment horizontal="center" vertical="bottom"/></xf></cellXfs>' +
      '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>' +
      "</styleSheet>",
  );

  const rows = Array.from({ length: plan.rows }, (_, r) => {
    const open = `<row r="${r + 1}" ht="${plan.rowHeightPt}" customHeight="1"`;
    if (!plan.captionPt || !entries[r]) return `${open}/>`;
    const serial = escapeXml(shortSerial(entries[r].external_reference));
    return `${open}><c r="A${r + 1}" s="1" t="inlineStr"><is><t>${serial}</t></is></c></row>`;
  }).join("");
  zip.file(
    "xl/worksheets/sheet1.xml",
    XML +
      `<worksheet xmlns="${NS_MAIN}" xmlns:r="${NS_REL}">` +
      '<sheetViews><sheetView showGridLines="0" workbookViewId="0"/></sheetViews>' +
      '<sheetFormatPr defaultRowHeight="15"/>' +
      `<cols><col min="1" max="1" width="${plan.columnWidth}" customWidth="1"/></cols>` +
      `<sheetData>${rows}</sheetData>` +
      '<sheetProtection sheet="1" objects="1"/>' +
      `<pageMargins left="${inches(plan.leftMm)}" right="${inches(plan.rightMm)}" ` +
      `top="${inches(plan.edgeMm)}" bottom="${inches(plan.edgeMm)}" header="0" footer="0"/>` +
      `<pageSetup paperSize="${PAPER_SIZE[layout.page_size]}" scale="100" orientation="portrait"/>` +
      '<drawing r:id="rId1"/>' +
      "</worksheet>",
  );
  zip.file(
    "xl/worksheets/_rels/sheet1.xml.rels",
    XML +
      `<Relationships xmlns="${NS_PKG}">` +
      `<Relationship Id="rId1" Type="${REL}/drawing" Target="../drawings/drawing1.xml"/>` +
      "</Relationships>",
  );

  const extent = Math.round(size * EMU_PER_MM);
  const offset = Math.round(plan.offsetMm * EMU_PER_MM);
  const top = Math.round(plan.topMm * EMU_PER_MM);
  const anchors: string[] = [];
  const links: string[] = [];
  for (let i = 0; i < entries.length; i++) {
    const id = `rId${i + 1}`;
    zip.file(`xl/media/code${i + 1}.png`, await symbolPng(symbolModules(entries[i].qr), scale), {
      compression: "STORE", // already deflated
    });
    links.push(`<Relationship Id="${id}" Type="${REL}/image" Target="../media/code${i + 1}.png"/>`);
    anchors.push(
      "<xdr:oneCellAnchor>" +
        `<xdr:from><xdr:col>0</xdr:col><xdr:colOff>${offset}</xdr:colOff>` +
        `<xdr:row>${i}</xdr:row><xdr:rowOff>${top}</xdr:rowOff></xdr:from>` +
        `<xdr:ext cx="${extent}" cy="${extent}"/>` +
        "<xdr:pic>" +
        `<xdr:nvPicPr><xdr:cNvPr id="${i + 2}" name="Code ${i + 1}"/>` +
        '<xdr:cNvPicPr><a:picLocks noChangeAspect="1"/></xdr:cNvPicPr></xdr:nvPicPr>' +
        `<xdr:blipFill><a:blip r:embed="${id}"/><a:stretch><a:fillRect/></a:stretch></xdr:blipFill>` +
        `<xdr:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="${extent}" cy="${extent}"/></a:xfrm>` +
        '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></xdr:spPr>' +
        "</xdr:pic><xdr:clientData/></xdr:oneCellAnchor>",
    );
  }
  zip.file(
    "xl/drawings/drawing1.xml",
    XML +
      '<xdr:wsDr xmlns:xdr="http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing" ' +
      `xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="${NS_REL}">` +
      anchors.join("") +
      "</xdr:wsDr>",
  );
  zip.file(
    "xl/drawings/_rels/drawing1.xml.rels",
    XML + `<Relationships xmlns="${NS_PKG}">${links.join("")}</Relationships>`,
  );

  return zip.generateAsync({ type: "uint8array", compression: "DEFLATE" });
}
