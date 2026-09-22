/**
 * Decoding a label from a camera frame.
 *
 * The browser's built-in BarcodeDetector reports text only, which for our
 * labels is the public URL and nothing else. ZXing reports the symbol's data
 * codewords as well, which is where the token is.
 */

import {
  BinaryBitmap,
  DecodeHintType,
  HybridBinarizer,
  QRCodeReader,
  RGBLuminanceSource,
} from "@zxing/library";

import type { Scan } from "./scanned.ts";

const reader = new QRCodeReader();
const hints = new Map<DecodeHintType, unknown>([[DecodeHintType.TRY_HARDER, true]]);

/** Greyscale, one byte per pixel, from RGBA image data. */
export function luminance(rgba: Uint8ClampedArray): Uint8ClampedArray {
  const out = new Uint8ClampedArray(rgba.length / 4);
  for (let i = 0; i < out.length; i++) {
    const r = rgba[4 * i];
    const g = rgba[4 * i + 1];
    const b = rgba[4 * i + 2];
    out[i] = (r * 77 + g * 150 + b * 29) >> 8;
  }
  return out;
}

/** Decodes the QR code in a greyscale frame, or returns null if there is none. */
export function decodeFrame(
  grey: Uint8ClampedArray,
  width: number,
  height: number,
): Scan | null {
  try {
    const bitmap = new BinaryBitmap(
      new HybridBinarizer(new RGBLuminanceSource(grey, width, height)),
    );
    const result = reader.decode(bitmap, hints);
    return { text: result.getText(), rawBytes: result.getRawBytes() ?? null };
  } catch {
    // No code in frame, or one too damaged to read: both routine.
    return null;
  } finally {
    reader.reset();
  }
}
