/// Client-side verification of the platform's signed records.
///
/// This mirrors what the Flutter app must do before it displays anything:
/// verify the signature over the *received bytes*, then check that the record
/// is actually bound to the package in the user's hand. A valid signature over
/// someone else's credential must not be shown as a valid package.
library;

import 'dart:convert';
import 'dart:typed_data';

import 'package:crypto/crypto.dart' as crypto;
import 'package:pqcrypto/pqcrypto.dart';

/// ML-DSA context strings. These must match the backend exactly: a signature
/// made under one context must not verify under another.
class SigContext {
  static final activation = Uint8List.fromList(utf8.encode('medicine-activation-v1'));
  static final status = Uint8List.fromList(utf8.encode('medicine-status-v1'));
  static final trustManifest =
      Uint8List.fromList(utf8.encode('medicine-trust-manifest-v1'));
}

/// Why a credential was refused. Kept distinct from "signature failed" because
/// the two mean very different things operationally.
class BindingError implements Exception {
  final String message;
  BindingError(this.message);
  @override
  String toString() => 'BindingError: $message';
}

/// Verifies an ML-DSA-65 signature over [payload] under [context].
///
/// Returns false rather than throwing for any malformed input, so a corrupt
/// response can never crash the scan screen.
bool verifySignature({
  required Uint8List publicKey,
  required Uint8List payload,
  required Uint8List signature,
  required Uint8List context,
}) {
  return MlDsa.verify(
    publicKey,
    payload,
    signature,
    DilithiumParams.mlDsa65,
    ctx: context,
  );
}

/// SHA-256 of a raw token, as lowercase hex.
///
/// The app holds the raw token only for the duration of a scan. Everything it
/// sends or compares uses this digest.
String hashToken(String token) =>
    crypto.sha256.convert(utf8.encode(token)).toString();

/// Parses JSON, refusing duplicate keys.
///
/// Dart's decoder silently keeps the last value for a repeated key. A record
/// that says two different things is ambiguous, and an ambiguous record that
/// carries a valid signature is still ambiguous.
Map<String, dynamic> parseStrict(Uint8List payload) {
  final text = utf8.decode(payload);
  final decoded = json.decode(text);
  if (decoded is! Map<String, dynamic>) {
    throw FormatException('payload is not a JSON object');
  }
  _rejectDuplicateKeys(text);
  return decoded;
}

void _rejectDuplicateKeys(String text) {
  // A targeted scan of top-level keys is enough for the records this app
  // receives, all of which are flat objects at the top level.
  final keys = <String>{};
  final matches = RegExp(r'"([^"\\]*)"\s*:').allMatches(text);
  var depth = 0;
  var index = 0;
  for (final match in matches) {
    for (; index < match.start; index++) {
      final ch = text[index];
      if (ch == '{' || ch == '[') depth++;
      if (ch == '}' || ch == ']') depth--;
    }
    if (depth == 1) {
      final key = match.group(1)!;
      if (!keys.add(key)) {
        throw FormatException('duplicate JSON key: $key');
      }
    }
  }
}

/// Confirms a verified credential describes the package that was scanned.
///
/// Call this only after [verifySignature] has succeeded. A valid signature is
/// not sufficient: a genuine credential for a different unit, replayed against
/// this token, must be refused here.
Map<String, dynamic> checkActivationBinding(
  Uint8List credentialBytes, {
  required String expectedTokenSha256,
  required String expectedManufacturerId,
  required String expectedKeyId,
}) {
  final record = parseStrict(credentialBytes);

  if (record['schema'] != 'medicine-activation-v1') {
    throw BindingError('unexpected credential schema');
  }
  if (record['algorithm'] != 'ML-DSA-65') {
    throw BindingError('unexpected credential algorithm');
  }
  if (record['token_sha256'] != expectedTokenSha256) {
    throw BindingError('credential is bound to a different token');
  }
  if (record['manufacturer_id'] != expectedManufacturerId) {
    throw BindingError('credential issued by a different manufacturer');
  }
  if (record['key_id'] != expectedKeyId) {
    throw BindingError('credential signed by an unexpected key');
  }
  return record;
}
