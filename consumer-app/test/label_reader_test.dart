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
import 'package:image/image.dart' as img;

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

  // What Android actually hands over: the frame as a lossless RGBA PNG. The
  // fast reader must agree with the image package on every PNG filter type.
  group('an Android camera frame', () {
    final jpeg = File('$_vectors/valid-label-frame.jpg').readAsBytesSync();
    final frame = img.decodeImage(jpeg)!.convert(numChannels: 4, alpha: 255);
    final expected = dataCodewordsFromImage(jpeg);

    for (final filter in img.PngFilter.values) {
      test('RGBA PNG, ${filter.name} filter', () {
        final png = img.encodePng(frame, filter: filter);
        final codewords = dataCodewordsFromImage(png);
        expect(codewords, equals(expected));
        expect(parseScannedBarcode(text: publicUrl, rawBytes: codewords)?.token,
            equals(_expected['token']));
      });
    }

    test('reading only where ML Kit saw the code', () {
      final png = img.encodePng(frame);
      // The symbol in this frame (from its finder patterns), padded by half.
      expect(dataCodewordsFromImage(png, region: [476, 136, 347, 364]), equals(expected));
    });

    test('a region in the wrong place still reads, from the whole frame', () {
      final png = img.encodePng(frame);
      expect(dataCodewordsFromImage(png, region: [0, 0, 120, 120]), equals(expected));
      expect(dataCodewordsFromFrame((image: png, region: [2000, 2000, 50, 50])),
          equals(expected));
    });
  });

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
