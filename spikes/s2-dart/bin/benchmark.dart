/// Measures ML-DSA-65 verification cost in Dart.
///
/// The app verifies two signatures per scan -- the activation credential and
/// the status envelope -- so the figure that matters to a user standing in a
/// pharmacy is roughly twice the per-verify time.
library;

import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import '../lib/verifier.dart';

void main(List<String> args) {
  final iterations = args.isNotEmpty ? int.parse(args[0]) : 50;
  final vector = json.decode(
    File('../../crypto-vectors/activation/valid-activation.json')
        .readAsStringSync(),
  ) as Map<String, dynamic>;

  final pk = base64.decode(vector['public_key'] as String);
  final payload = base64.decode(vector['payload'] as String);
  final sig = base64.decode(vector['signature'] as String);

  // Warm up the JIT/AOT paths before timing.
  for (var i = 0; i < 5; i++) {
    verifySignature(
      publicKey: pk, payload: payload, signature: sig,
      context: SigContext.activation,
    );
  }

  final samples = <int>[];
  for (var i = 0; i < iterations; i++) {
    final watch = Stopwatch()..start();
    final ok = verifySignature(
      publicKey: pk, payload: payload, signature: sig,
      context: SigContext.activation,
    );
    watch.stop();
    if (!ok) throw StateError('vector failed to verify during benchmark');
    samples.add(watch.elapsedMicroseconds);
  }

  samples.sort();
  int pct(int p) => samples[((samples.length - 1) * p / 100).round()];

  print('iterations       : $iterations');
  print('min              : ${(samples.first / 1000).toStringAsFixed(1)} ms');
  print('p50              : ${(pct(50) / 1000).toStringAsFixed(1)} ms');
  print('p95              : ${(pct(95) / 1000).toStringAsFixed(1)} ms');
  print('max              : ${(samples.last / 1000).toStringAsFixed(1)} ms');
  print('two per scan p95 : ${(pct(95) * 2 / 1000).toStringAsFixed(1)} ms');
}
