/// The scanned-payload parser is the app's outermost boundary.
///
/// It decides what is even eligible to reach the network, so its refusals
/// matter more than its acceptances.
library;

import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:consumer_app/core/scanned_url.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/label_codewords.dart';

/// A structurally valid token, built rather than pasted.
///
/// Embedding a literal one would put a token-shaped string in tracked source,
/// which the leak scan flags -- correctly, since it cannot tell a fixture from
/// the real thing.
final goodToken = List.generate(
  43,
  (i) => 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_'[
      (i * 7 + 11) % 64],
).join();

/// A token built from 32 bytes, as real ones are, so it survives the raw-bytes
/// round trip exactly. [goodToken] passes the URL checks but is not canonical.
final canonicalToken = base64Url
    .encode(List.generate(32, (i) => (i * 13 + 29) % 256))
    .replaceAll('=', '');

Uint8List _hex(String hex) => Uint8List.fromList([
      for (var i = 0; i < hex.length; i += 2)
        int.parse(hex.substring(i, i + 2), radix: 16),
    ]);

void main() {
  group('label symbol', () {
    test('agrees with every shared vector', () {
      final files = Directory('../crypto-vectors/label')
          .listSync()
          .whereType<File>()
          .where((f) => f.path.endsWith('.json'))
          .toList();
      expect(files, isNotEmpty, reason: 'run crypto-vectors/generate_labels.py');

      for (final file in files) {
        final vector = jsonDecode(file.readAsStringSync()) as Map<String, dynamic>;
        final token = tokenFromDataCodewords(
          _hex(vector['data_codewords'] as String),
          text: vector['text'] as String?,
        );
        if (vector['expected'] == 'VALID') {
          expect(token, equals(vector['token']), reason: file.path);
        } else {
          expect(token, isNull, reason: file.path);
        }
      }
    });

    test('recovers the token from the raw codewords', () {
      final scanned = parseScannedBarcode(
        text: publicUrl,
        rawBytes: labelCodewords(canonicalToken),
      );
      expect(scanned?.token, equals(canonicalToken));
    });

    test('refuses the public reading alone', () {
      // What a scanner that reports only text gives us.
      expect(parseScannedBarcode(text: publicUrl), isNull);
    });

    test('refuses a URL label unless the build opts in', () {
      final url = 'https://anticounterfeitmed.com/#v=1&t=$goodToken';
      expect(parseScannedBarcode(text: url), acceptUrlLabels ? isNotNull : isNull);
    });
  });

  test('accepts our own URL', () {
    final scanned = parseScannedPayload(
      'https://anticounterfeitmed.com/#v=1&t=$goodToken',
    );
    expect(scanned, isNotNull);
    expect(scanned!.token, equals(goodToken));
  });

  test('tolerates surrounding whitespace from a scanner', () {
    expect(
      parseScannedPayload('  https://anticounterfeitmed.com/#v=1&t=$goodToken \n')
          ?.token,
      equals(goodToken),
    );
  });

  group('refuses', () {
    test('a look-alike host', () {
      for (final host in [
        'anticounterfeitmed.com.evil.example',
        'evil.example',
        'anticounterfeitrned.com',
        'sub.anticounterfeitmed.com',
      ]) {
        expect(
          parseScannedPayload('https://$host/#v=1&t=$goodToken'),
          isNull,
          reason: host,
        );
      }
    });

    test('plain http, which an attacker chooses freely', () {
      expect(
        parseScannedPayload('http://anticounterfeitmed.com/#v=1&t=$goodToken'),
        isNull,
      );
    });

    test('a non-HTTP scheme', () {
      for (final payload in [
        'javascript:alert(1)',
        'file:///etc/passwd',
        'intent://anticounterfeitmed.com/#v=1&t=$goodToken',
      ]) {
        expect(parseScannedPayload(payload), isNull, reason: payload);
      }
    });

    test('a wrong or missing version', () {
      expect(parseScannedPayload('https://anticounterfeitmed.com/#v=2&t=$goodToken'),
          isNull);
      expect(parseScannedPayload('https://anticounterfeitmed.com/#t=$goodToken'),
          isNull);
    });

    test('a malformed token', () {
      final cases = {
        'too short': goodToken.substring(0, 42),
        'too long': '${goodToken}x',
        'illegal character': '${goodToken.substring(0, 42)}!',
        'empty': '',
      };
      cases.forEach((label, token) {
        expect(
          parseScannedPayload('https://anticounterfeitmed.com/#v=1&t=$token'),
          isNull,
          reason: label,
        );
      });
    });

    test('arbitrary text and empty input', () {
      for (final payload in ['', '   ', 'hello world', 'not a url at all']) {
        expect(parseScannedPayload(payload), isNull);
      }
    });

    test('a token placed in the query rather than the fragment', () {
      // The token belongs in the fragment, which keeps it out of request paths.
      expect(
        parseScannedPayload('https://anticounterfeitmed.com/?v=1&t=$goodToken'),
        isNull,
      );
    });
  });
}
