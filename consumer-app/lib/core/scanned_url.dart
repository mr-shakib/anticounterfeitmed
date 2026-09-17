/// Parsing of a scanned QR payload.
///
/// This runs before anything touches the network, and it is deliberately
/// strict: the app accepts only its own URL shape and never opens an arbitrary
/// scanned link. Anything else is simply "not one of our codes" -- not opened,
/// not sent anywhere, not reported as an error worth alarming someone about.
library;

const expectedHost = 'anticounterfeitmed.com';
const expectedVersion = '1';
const tokenLength = 43;

final _tokenPattern = RegExp(r'^[A-Za-z0-9_-]{43}$');

class ScannedCode {
  final String token;
  const ScannedCode(this.token);
}

/// Returns the token from a scanned payload, or null when it is not ours.
///
/// The token lives in the URL fragment, which keeps it out of ordinary HTTP
/// request paths. It is still sensitive: anyone who can see the uncovered QR
/// can read it.
ScannedCode? parseScannedPayload(String raw) {
  final trimmed = raw.trim();
  if (trimmed.isEmpty) return null;

  final Uri uri;
  try {
    uri = Uri.parse(trimmed);
  } on FormatException {
    return null;
  }

  // Only our own HTTPS origin. A plain-text or http payload is refused rather
  // than upgraded, because an attacker chooses what the QR says.
  if (uri.scheme != 'https') return null;
  if (uri.host.toLowerCase() != expectedHost) return null;
  if (uri.hasPort && uri.port != 443) return null;

  final fragment = uri.fragment;
  if (fragment.isEmpty) return null;

  final fields = <String, String>{};
  for (final part in fragment.split('&')) {
    final index = part.indexOf('=');
    if (index <= 0) continue;
    fields[part.substring(0, index)] = part.substring(index + 1);
  }

  if (fields['v'] != expectedVersion) return null;

  final token = fields['t'];
  if (token == null || !_tokenPattern.hasMatch(token)) return null;

  return ScannedCode(token);
}
