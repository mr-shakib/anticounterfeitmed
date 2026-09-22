/// Parsing of a scanned QR code.
///
/// This runs before anything touches the network, and it is deliberately
/// strict: the app accepts only its own label layout and never opens an
/// arbitrary scanned link. Anything else is simply "not one of our codes" --
/// not opened, not sent anywhere, not reported as an error worth alarming
/// someone about.
library;

import 'dart:convert';
import 'dart:typed_data';

const expectedHost = 'anticounterfeitmed.com';
const expectedVersion = '1';
const tokenLength = 43;

/// The only text an ordinary scanner reads from one of our labels.
const publicUrl = 'https://$expectedHost/';

/// Whether to accept the original label format, where the token sat in the
/// URL fragment and any scanner could read it.
///
/// Off by default: a URL that carries a token is exactly what should not scan.
/// Turn it on with `--dart-define=ACCEPT_URL_LABELS=true` only for a pilot that
/// already printed labels in that format and needs them to keep working.
const acceptUrlLabels = bool.fromEnvironment('ACCEPT_URL_LABELS');

const _recordMarker = [0x4D, 0x56]; // "MV"
const _recordVersion = 2;
const _tokenBytes = 32;
const _byteMode = 0x4;

final _tokenPattern = RegExp(r'^[A-Za-z0-9_-]{43}$');

class ScannedCode {
  final String token;
  const ScannedCode(this.token);
}

/// Returns the token from a scanned code, or null when it is not ours.
///
/// [text] is the decoder's reading of the symbol and [rawBytes] its data
/// codewords. Our labels carry the token only in the codewords, after the point
/// where standard decoders stop, so a scanner that reports text alone gets the
/// public URL and nothing else.
ScannedCode? parseScannedBarcode({String? text, Uint8List? rawBytes}) {
  if (rawBytes != null) {
    final token = tokenFromDataCodewords(rawBytes, text: text);
    if (token != null) return ScannedCode(token);
  }
  if (acceptUrlLabels && text != null) return parseScannedPayload(text);
  return null;
}

class _BitReader {
  _BitReader(this.data);

  final Uint8List data;
  int position = 0;

  int? take(int width) {
    if (position + width > data.length * 8) return null;
    var value = 0;
    for (var i = 0; i < width; i++) {
      final byte = data[position >> 3];
      value = (value << 1) | ((byte >> (7 - (position & 7))) & 1);
      position++;
    }
    return value;
  }
}

/// Returns the token a label symbol's data codewords carry, or null.
///
/// Must agree with `medcrypto/labels.py` on every file in
/// `crypto-vectors/label/`. The layout is documented there: a byte-mode segment
/// holding exactly [publicUrl], the terminator, then "MV", version 2 and the 32
/// token bytes. Bytes after the token are ignored.
String? tokenFromDataCodewords(Uint8List raw, {String? text}) {
  if (text != null && text != publicUrl) return null;

  final url = ascii.encode(publicUrl);
  final reader = _BitReader(raw);
  if (reader.take(4) != _byteMode) return null;
  if (reader.take(8) != url.length) return null;
  for (final expected in url) {
    if (reader.take(8) != expected) return null;
  }
  if (reader.take(4) != 0) return null;

  final start = reader.position >> 3;
  const headerLength = 3;
  if (raw.length < start + headerLength + _tokenBytes) return null;
  if (raw[start] != _recordMarker[0] ||
      raw[start + 1] != _recordMarker[1] ||
      raw[start + 2] != _recordVersion) {
    return null;
  }
  final tokenBytes = raw.sublist(
    start + headerLength,
    start + headerLength + _tokenBytes,
  );
  return base64Url.encode(tokenBytes).replaceAll('=', '');
}

/// Returns the token from an original-format URL label, or null.
///
/// The token lives in the URL fragment, which keeps it out of ordinary HTTP
/// request paths -- but any scanner can read it. Reached only when
/// [acceptUrlLabels] is on.
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
