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

const EXPECTED_HOST = "anticounterfeitmed.com";
const EXPECTED_VERSION = "1";
const TOKEN = /^[A-Za-z0-9_-]{43}$/;

/**
 * Returns the token from a scanned label, or null when it is not one of ours.
 *
 * Accepts the printed URL, or a bare token: a keyboard-wedge scanner
 * configured to strip the prefix types only the code.
 */
export function tokenFromScan(raw: string): string | null {
  const trimmed = raw.trim();
  if (!trimmed) return null;
  if (TOKEN.test(trimmed)) return trimmed;

  let url: URL;
  try {
    url = new URL(trimmed);
  } catch {
    return null;
  }

  if (url.protocol !== "https:") return null;
  if (url.hostname.toLowerCase() !== EXPECTED_HOST) return null;

  const fields = new URLSearchParams(url.hash.replace(/^#/, ""));
  if (fields.get("v") !== EXPECTED_VERSION) return null;

  const token = fields.get("t");
  return token && TOKEN.test(token) ? token : null;
}
