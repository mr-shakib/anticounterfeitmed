/// The scanned-payload parser is the app's outermost boundary.
///
/// It decides what is even eligible to reach the network, so its refusals
/// matter more than its acceptances.
library;

import 'package:consumer_app/core/scanned_url.dart';
import 'package:flutter_test/flutter_test.dart';

const goodToken = 'CxIZICcuNTxDSlFYX2ZtdHuCiZCXnqWss7rByM_W3eQ';

void main() {
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
