/// Runs the golden signature vectors on the device.
///
/// The same files are checked by the Django suite and by the OpenSSL CLI. If a
/// build of this app ever disagrees with them -- a dependency bump, a new ABI,
/// a platform quirk -- this reports it on the device rather than leaving it to
/// be discovered against a real package in a pharmacy.
library;

import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/services.dart' show rootBundle;

import 'verifier.dart';

const _vectorAssets = <String>[
  'assets/crypto-vectors/activation/valid-activation.json',
  'assets/crypto-vectors/status/valid-status.json',
  'assets/crypto-vectors/negative/tampered-payload.json',
  'assets/crypto-vectors/negative/wrong-context.json',
  'assets/crypto-vectors/negative/wrong-key.json',
  'assets/crypto-vectors/negative/truncated-signature.json',
  'assets/crypto-vectors/negative/empty-signature.json',
  'assets/crypto-vectors/negative/duplicate-json-key.json',
  'assets/crypto-vectors/negative/wrong-token-binding.json',
];

class VectorResult {
  final String name;
  final String check;
  final bool passed;
  final String detail;

  VectorResult(this.name, this.check, this.passed, this.detail);
}

class SelfCheckReport {
  final List<VectorResult> results;
  final Duration verifyP50;
  final int sampleCount;

  SelfCheckReport(this.results, this.verifyP50, this.sampleCount);

  bool get allPassed => results.every((r) => r.passed);
  int get passedCount => results.where((r) => r.passed).length;
}

Uint8List _contextByValue(String value) => switch (value) {
      'medicine-activation-v1' => SigContext.activation,
      'medicine-status-v1' => SigContext.status,
      'medicine-trust-manifest-v1' => SigContext.trustManifest,
      _ => throw ArgumentError('unknown context: $value'),
    };

Future<SelfCheckReport> runSelfCheck() async {
  final results = <VectorResult>[];
  Uint8List? benchPk, benchPayload, benchSig;

  for (final asset in _vectorAssets) {
    final vector =
        json.decode(await rootBundle.loadString(asset)) as Map<String, dynamic>;
    final name = vector['name'] as String;
    final check = (vector['check'] ?? 'signature') as String;
    final expectValid = vector['expected'] == 'VALID';

    try {
      switch (check) {
        case 'parse':
          var parsed = true;
          try {
            parseStrict(base64.decode(vector['payload'] as String));
          } on FormatException {
            parsed = false;
          }
          results.add(VectorResult(
              name, check, parsed == expectValid, parsed ? 'parsed' : 'refused'));

        case 'binding':
          final payload = base64.decode(vector['payload'] as String);
          final sigOk = verifySignature(
            publicKey: base64.decode(vector['public_key'] as String),
            payload: payload,
            signature: base64.decode(vector['signature'] as String),
            context: _contextByValue(vector['context'] as String),
          );
          var refused = false;
          try {
            checkActivationBinding(
              payload,
              expectedTokenSha256:
                  hashToken(vector['presented_with_token'] as String),
              expectedManufacturerId: 'mfr-square-pharmaceuticals',
              expectedKeyId: vector['key_id'] as String,
            );
          } on BindingError {
            refused = true;
          }
          // The signature must be genuine and the binding must still refuse it.
          results.add(VectorResult(name, check, sigOk && refused,
              'signature ${sigOk ? "valid" : "INVALID"}, binding ${refused ? "refused" : "ACCEPTED"}'));

        default:
          final signature = vector['signature'] as String;
          final pk = base64.decode(vector['public_key'] as String);
          final payload = base64.decode(vector['payload'] as String);
          final actual = signature.isEmpty
              ? false
              : verifySignature(
                  publicKey: pk,
                  payload: payload,
                  signature: base64.decode(signature),
                  context: _contextByValue(vector['context'] as String),
                );
          if (expectValid && actual) {
            benchPk = pk;
            benchPayload = payload;
            benchSig = base64.decode(signature);
          }
          results.add(VectorResult(name, check, actual == expectValid,
              actual ? 'verified' : 'rejected'));
      }
    } catch (e) {
      results.add(VectorResult(name, check, false, 'threw: $e'));
    }
  }

  // Time verification on this device. Two signatures are checked per scan.
  var p50 = Duration.zero;
  const samples = 20;
  if (benchPk != null) {
    final timings = <int>[];
    for (var i = 0; i < samples; i++) {
      final watch = Stopwatch()..start();
      verifySignature(
        publicKey: benchPk,
        payload: benchPayload!,
        signature: benchSig!,
        context: SigContext.activation,
      );
      watch.stop();
      timings.add(watch.elapsedMicroseconds);
    }
    timings.sort();
    p50 = Duration(microseconds: timings[timings.length ~/ 2]);
  }

  return SelfCheckReport(results, p50, samples);
}
