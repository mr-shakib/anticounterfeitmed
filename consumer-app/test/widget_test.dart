/// Verifier tests that run on the host as part of the normal suite.
///
/// The on-device self-check in lib/crypto/self_check.dart covers the same
/// vectors on real hardware; these catch a regression before it gets that far.
library;

import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:consumer_app/crypto/verifier.dart';
import 'package:flutter_test/flutter_test.dart';

Uint8List b64(String v) => base64.decode(v);

Map<String, dynamic> loadVector(String path) =>
    json.decode(File('assets/crypto-vectors/$path').readAsStringSync())
        as Map<String, dynamic>;

Uint8List contextByValue(String value) => switch (value) {
      'medicine-activation-v1' => SigContext.activation,
      'medicine-status-v1' => SigContext.status,
      'medicine-trust-manifest-v1' => SigContext.trustManifest,
      _ => throw ArgumentError(value),
    };

void main() {
  test('a valid activation credential verifies', () {
    final v = loadVector('activation/valid-activation.json');
    expect(
      verifySignature(
        publicKey: b64(v['public_key'] as String),
        payload: b64(v['payload'] as String),
        signature: b64(v['signature'] as String),
        context: SigContext.activation,
      ),
      isTrue,
    );
  });

  test('a signature does not verify under another context', () {
    final v = loadVector('activation/valid-activation.json');
    expect(
      verifySignature(
        publicKey: b64(v['public_key'] as String),
        payload: b64(v['payload'] as String),
        signature: b64(v['signature'] as String),
        context: SigContext.status,
      ),
      isFalse,
      reason: 'context separation must hold on the client too',
    );
  });

  test('a tampered payload is rejected', () {
    final v = loadVector('negative/tampered-payload.json');
    expect(
      verifySignature(
        publicKey: b64(v['public_key'] as String),
        payload: b64(v['payload'] as String),
        signature: b64(v['signature'] as String),
        context: contextByValue(v['context'] as String),
      ),
      isFalse,
    );
  });

  test('a credential for another package is refused on binding', () {
    final v = loadVector('negative/wrong-token-binding.json');
    final payload = b64(v['payload'] as String);

    // The signature is genuine; the binding is what must refuse it.
    expect(
      verifySignature(
        publicKey: b64(v['public_key'] as String),
        payload: payload,
        signature: b64(v['signature'] as String),
        context: SigContext.activation,
      ),
      isTrue,
    );
    expect(
      () => checkActivationBinding(
        payload,
        expectedTokenSha256: hashToken(v['presented_with_token'] as String),
        expectedManufacturerId: 'mfr-square-pharmaceuticals',
        expectedKeyId: v['key_id'] as String,
      ),
      throwsA(isA<BindingError>()),
    );
  });

  test('duplicate JSON keys are refused', () {
    final v = loadVector('negative/duplicate-json-key.json');
    expect(() => parseStrict(b64(v['payload'] as String)),
        throwsA(isA<FormatException>()));
  });

  test('token hashing matches the server digest', () {
    final v = loadVector('activation/valid-activation.json');
    expect(hashToken(v['token'] as String), equals(v['token_sha256']));
  });
}
