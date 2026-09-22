/// The app's path from a camera frame to a token.
///
/// ML Kit's rawBytes carries only the public URL, so the token is recovered by
/// ZXing from the frame. These run that path on the shared label images.
library;

import 'dart:convert';
import 'dart:io';

import 'package:consumer_app/core/label_reader.dart';
import 'package:consumer_app/core/scanned_url.dart';
import 'package:flutter_test/flutter_test.dart';

const _vectors = '../crypto-vectors/label';

final _expected =
    (jsonDecode(File('$_vectors/valid-label.json').readAsStringSync())
        as Map<String, dynamic>);

void main() {
  for (final image in ['valid-label.png', 'valid-label-frame.jpg']) {
    test('recovers the token from $image', () {
      final codewords =
          dataCodewordsFromImage(File('$_vectors/$image').readAsBytesSync());
      expect(codewords, isNotNull, reason: 'ZXing found no code');

      final scanned = parseScannedBarcode(text: publicUrl, rawBytes: codewords);
      expect(scanned?.token, equals(_expected['token']));
    });
  }

  test('what ML Kit reports is not enough on its own', () {
    // Measured on the emulator: rawBytes is the text, and nothing after it.
    final mlKitRawBytes = ascii.encode(publicUrl);
    expect(parseScannedBarcode(text: publicUrl, rawBytes: mlKitRawBytes), isNull);
  });

  test('an image with no code yields nothing', () {
    expect(dataCodewordsFromImage(File('$_vectors/../../assets/brand/mark.webp')
        .readAsBytesSync()), isNull);
  });
}
