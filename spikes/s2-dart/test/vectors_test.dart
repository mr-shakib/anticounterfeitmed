/// Spike S2: the golden vectors must reach the same verdict in Dart as they do
/// in Python and under the OpenSSL CLI. That agreement, not any one library, is
/// the interoperability contract.
library;

import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:test/test.dart';

import '../lib/verifier.dart';

final vectorDir = Directory('../../crypto-vectors');

Uint8List b64(String value) => base64.decode(value);

Uint8List contextByValue(String value) => switch (value) {
      'medicine-activation-v1' => SigContext.activation,
      'medicine-status-v1' => SigContext.status,
      'medicine-trust-manifest-v1' => SigContext.trustManifest,
      _ => throw ArgumentError('unknown context: $value'),
    };

List<Map<String, dynamic>> loadVectors() {
  final files = vectorDir
      .listSync(recursive: true)
      .whereType<File>()
      .where((f) => f.path.endsWith('.json'))
      .toList()
    ..sort((a, b) => a.path.compareTo(b.path));
  return files
      .map((f) => {...json.decode(f.readAsStringSync()) as Map<String, dynamic>,
            '_path': f.path})
      .toList();
}

void main() {
  final vectors = loadVectors();

  test('vectors are present', () {
    expect(vectors, isNotEmpty,
        reason: 'run crypto-vectors/generate.py first');
    print('loaded ${vectors.length} vectors');
  });

  for (final vector in vectors) {
    final name = vector['name'] as String;
    final check = (vector['check'] ?? 'signature') as String;
    final expectValid = vector['expected'] == 'VALID';

    test('$check/$name expects ${vector['expected']}', () {
      switch (check) {
        case 'parse':
          if (expectValid) {
            expect(() => parseStrict(b64(vector['payload'] as String)),
                returnsNormally);
          } else {
            expect(() => parseStrict(b64(vector['payload'] as String)),
                throwsA(isA<FormatException>()));
          }

        case 'binding':
          final payload = b64(vector['payload'] as String);
          // The signature must be genuine, so that the binding check is what
          // rejects it. A signature failure here would prove nothing.
          final sigOk = verifySignature(
            publicKey: b64(vector['public_key'] as String),
            payload: payload,
            signature: b64(vector['signature'] as String),
            context: contextByValue(vector['context'] as String),
          );
          expect(sigOk, isTrue,
              reason: 'binding vector must carry a valid signature');
          expect(
            () => checkActivationBinding(
              payload,
              expectedTokenSha256:
                  hashToken(vector['presented_with_token'] as String),
              expectedManufacturerId: 'mfr-square-pharmaceuticals',
              expectedKeyId: vector['key_id'] as String,
            ),
            throwsA(isA<BindingError>()),
          );

        default:
          final signature = vector['signature'] as String;
          final actual = signature.isEmpty
              ? false
              : verifySignature(
                  publicKey: b64(vector['public_key'] as String),
                  payload: b64(vector['payload'] as String),
                  signature: b64(signature),
                  context: contextByValue(vector['context'] as String),
                );
          expect(actual, equals(expectValid));
      }
    });
  }
}
