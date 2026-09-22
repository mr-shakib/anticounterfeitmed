/**
 * The printed label symbol: drawing it, and reading a token back out of it.
 *
 * An ordinary scanner reads only PUBLIC_URL from one of our labels. The token
 * sits in the same symbol's data codewords, after the terminator where every
 * standard decoder stops, so only a reader that exposes raw codewords recovers
 * it. The layout is defined in libs/medcrypto/medcrypto/labels.py; this file
 * must agree with it on every vector in crypto-vectors/label/.
 *
 * Hiding the token from ordinary scanners does not make it secret. A raw-byte
 * decoder reads it, and a photocopy of the label still scans.
 */

import qrcodegen from "./vendor/qrcodegen.ts";

export const PUBLIC_URL = "https://anticounterfeitmed.com/";

/** How the backend describes one label's symbol. */
export type LabelSymbol = {
  version: number;
  error_correction: string;
  data_codewords: string;
};

const SYMBOL_VERSION = 6;
const ERROR_CORRECTION = "Q";
const DATA_CODEWORDS = 76;
const RECORD_MARKER = [0x4d, 0x56]; // "MV"
const RECORD_VERSION = 2;
const TOKEN_BYTES = 32;
const BYTE_MODE = 0b0100;

/** Modules per side of the printed footprint, quiet zone included. */
export const SYMBOL_MODULES = 4 * SYMBOL_VERSION + 17 + 2 * 4;

function hexToBytes(hex: string): Uint8Array {
  if (!/^(?:[0-9a-f]{2})*$/.test(hex)) throw new Error("malformed codewords");
  const out = new Uint8Array(hex.length / 2);
  for (let i = 0; i < out.length; i++) out[i] = parseInt(hex.slice(2 * i, 2 * i + 2), 16);
  return out;
}

/**
 * Draws a label symbol as SVG, from the data codewords the backend issued.
 *
 * Refuses anything but the one symbol shape the readers expect, so a format
 * change on the backend cannot silently print labels nobody can read.
 */
export function symbolSvg(symbol: LabelSymbol, quietZone = 4): string {
  if (symbol.version !== SYMBOL_VERSION || symbol.error_correction !== ERROR_CORRECTION) {
    throw new Error(
      `Unsupported label symbol ${symbol.version}-${symbol.error_correction}.`,
    );
  }
  const data = hexToBytes(symbol.data_codewords);
  if (data.length !== DATA_CODEWORDS) throw new Error("malformed codewords");

  const qr = new qrcodegen.QrCode(
    SYMBOL_VERSION,
    qrcodegen.QrCode.Ecc.QUARTILE,
    Array.from(data),
    -1, // the mask with the lowest penalty, as any standard encoder picks
  );

  const side = qr.size + 2 * quietZone;
  const path: string[] = [];
  for (let y = 0; y < qr.size; y++) {
    for (let x = 0; x < qr.size; x++) {
      if (qr.getModule(x, y)) path.push(`M${x + quietZone},${y + quietZone}h1v1h-1z`);
    }
  }
  return (
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${side} ${side}" ` +
    `shape-rendering="crispEdges">` +
    `<rect width="${side}" height="${side}" fill="#fff"/>` +
    `<path d="${path.join("")}" fill="#000"/></svg>`
  );
}

/**
 * Returns the token a label symbol's data codewords carry, or null.
 *
 * `text` is the decoder's own reading of the symbol, when it gives one; it
 * must be exactly PUBLIC_URL. Bytes after the token are ignored.
 */
export function tokenFromDataCodewords(
  raw: Uint8Array,
  text?: string | null,
): string | null {
  if (text != null && text !== PUBLIC_URL) return null;

  let position = 0;
  const take = (width: number): number | null => {
    if (position + width > raw.length * 8) return null;
    let value = 0;
    for (let i = 0; i < width; i++) {
      const byte = raw[position >> 3];
      value = (value << 1) | ((byte >> (7 - (position & 7))) & 1);
      position++;
    }
    return value;
  };

  if (take(4) !== BYTE_MODE) return null;
  if (take(8) !== PUBLIC_URL.length) return null;
  for (let i = 0; i < PUBLIC_URL.length; i++) {
    if (take(8) !== PUBLIC_URL.charCodeAt(i)) return null;
  }
  if (take(4) !== 0) return null;

  const start = position >> 3;
  const header = 3;
  if (raw.length < start + header + TOKEN_BYTES) return null;
  if (
    raw[start] !== RECORD_MARKER[0] ||
    raw[start + 1] !== RECORD_MARKER[1] ||
    raw[start + 2] !== RECORD_VERSION
  ) {
    return null;
  }
  const token = raw.subarray(start + header, start + header + TOKEN_BYTES);
  let binary = "";
  for (const byte of token) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}
