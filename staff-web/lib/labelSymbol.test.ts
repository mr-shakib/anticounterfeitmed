/**
 * The portal's half of the label format.
 *
 * Run with `npm test`. The vectors pin the parser to the Python reference and
 * the Dart app; the round trip checks that a symbol this portal draws reads
 * back as the public URL to a decoder, and as the token to ours.
 */

import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";

import { PUBLIC_URL, SYMBOL_MODULES, symbolSvg, tokenFromDataCodewords } from "./labelSymbol.ts";
import { decodeFrame } from "./readLabel.ts";
import { readScan } from "./scanned.ts";

const VECTORS = join(import.meta.dirname, "../../crypto-vectors/label");

type Vector = {
  name: string;
  data_codewords: string;
  text: string | null;
  expected: "VALID" | "INVALID";
  token?: string;
};

const vectors: Vector[] = readdirSync(VECTORS)
  .filter((f) => f.endsWith(".json"))
  .map((f) => JSON.parse(readFileSync(join(VECTORS, f), "utf8")));

const bytes = (hex: string) => Uint8Array.from(Buffer.from(hex, "hex"));
const valid = vectors.find((v) => v.name === "valid-label")!;
/** The valid vector as the backend issues it. */
const issued = { version: 6, error_correction: "Q", data_codewords: valid.data_codewords };

/** Rasterises the SVG this portal prints, at `scale` pixels per module. */
function rasterise(svg: string, scale = 6) {
  const side = SYMBOL_MODULES * scale;
  const grey = new Uint8ClampedArray(side * side).fill(255);
  for (const [, x, y] of svg.matchAll(/M(\d+),(\d+)h1v1h-1z/g)) {
    for (let dy = 0; dy < scale; dy++) {
      for (let dx = 0; dx < scale; dx++) {
        grey[(Number(y) * scale + dy) * side + Number(x) * scale + dx] = 0;
      }
    }
  }
  return { grey, side };
}

test("agrees with every shared vector", () => {
  assert.ok(vectors.length > 0, "run crypto-vectors/generate_labels.py");
  for (const v of vectors) {
    const token = tokenFromDataCodewords(bytes(v.data_codewords), v.text);
    assert.equal(token, v.expected === "VALID" ? v.token : null, v.name);
  }
});

test("a drawn label reads as the public URL, and as the token to us", () => {
  const { grey, side } = rasterise(symbolSvg(issued));
  const scan = decodeFrame(grey, side, side);

  assert.ok(scan, "the drawn symbol did not decode");
  assert.equal(scan.text, PUBLIC_URL);
  assert.ok(!scan.text.includes(valid.token!));
  assert.deepEqual(readScan(scan), { kind: "token", token: valid.token });
});

test("a scanner that reports text only gets no token", () => {
  assert.deepEqual(readScan({ text: PUBLIC_URL }), { kind: "public-only" });
});

test("the original URL format still reads, for labels already printed", () => {
  const token = valid.token!;
  assert.deepEqual(
    readScan({ text: `https://anticounterfeitmed.com/#v=1&t=${token}` }),
    { kind: "token", token },
  );
  assert.deepEqual(readScan({ text: "https://evil.example/#v=1&t=" + token }), {
    kind: "not-ours",
  });
});

test("refuses to draw a symbol shape the readers do not expect", () => {
  assert.doesNotThrow(() => symbolSvg(issued));
  assert.throws(() => symbolSvg({ ...issued, version: 7 }));
  assert.throws(() => symbolSvg({ ...issued, error_correction: "M" }));
  assert.throws(() => symbolSvg({ ...issued, data_codewords: issued.data_codewords.slice(2) }));
});
