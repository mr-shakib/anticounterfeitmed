/**
 * Parsing of a scanned label, in the portal.
 *
 * The same rules as the consumer app's parser, and for the same reason: a code
 * that is not ours is not opened, not followed, and not sent anywhere. Here it
 * is simply not a label from this batch.
 *
 * The token this returns is a live credential. It goes straight to the scan
 * endpoint and is never stored, rendered, or put in a URL.
 */

import { PUBLIC_URL, tokenFromDataCodewords } from "./labelSymbol.ts";

const EXPECTED_HOST = "anticounterfeitmed.com";
const EXPECTED_VERSION = "1";
const TOKEN = /^[A-Za-z0-9_-]{43}$/;

export type Scan = {
  /** What the decoder read as text. A keyboard-wedge scanner gives only this. */
  text: string;
  /** The symbol's data codewords, from a decoder that exposes them. */
  rawBytes?: Uint8Array | null;
};

export type ScanReading =
  | { kind: "token"; token: string }
  /** One of our labels, read by something that only reports text. */
  | { kind: "public-only" }
  | { kind: "not-ours" };

/**
 * Reads a token from a scanned label.
 *
 * Current labels carry the token only in the codewords, so the camera is the
 * way to scan them. The original format -- the token in the URL fragment, or a
 * bare token from a scanner set to strip the prefix -- is still accepted here,
 * so labels printed before the change can be scanned on their own line.
 */
export function readScan({ text, rawBytes }: Scan): ScanReading {
  if (rawBytes) {
    const token = tokenFromDataCodewords(rawBytes, text || null);
    if (token) return { kind: "token", token };
  }

  const trimmed = text.trim();
  if (!trimmed) return { kind: "not-ours" };
  if (trimmed === PUBLIC_URL) return { kind: "public-only" };
  if (TOKEN.test(trimmed)) return { kind: "token", token: trimmed };

  let url: URL;
  try {
    url = new URL(trimmed);
  } catch {
    return { kind: "not-ours" };
  }

  if (url.protocol !== "https:") return { kind: "not-ours" };
  if (url.hostname.toLowerCase() !== EXPECTED_HOST) return { kind: "not-ours" };

  const fields = new URLSearchParams(url.hash.replace(/^#/, ""));
  if (fields.get("v") !== EXPECTED_VERSION) return { kind: "not-ours" };

  const token = fields.get("t");
  return token && TOKEN.test(token) ? { kind: "token", token } : { kind: "not-ours" };
}
