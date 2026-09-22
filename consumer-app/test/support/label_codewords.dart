/// Builds a label symbol's data codewords for a token, as the backend does.
///
/// Test-only: the app never encodes labels. The layout is the one in
/// `medcrypto/labels.py`, and the vectors in `crypto-vectors/label/` pin both
/// sides to it.
library;

import 'dart:convert';
import 'dart:typed_data';

import 'package:consumer_app/core/scanned_url.dart';

Uint8List labelCodewords(String token) {
  final bits = <int>[];
  void put(int value, int width) {
    for (var shift = width - 1; shift >= 0; shift--) {
      bits.add((value >> shift) & 1);
    }
  }

  final url = ascii.encode(publicUrl);
  put(0x4, 4);
  put(url.length, 8);
  for (final b in url) {
    put(b, 8);
  }
  put(0, 4);

  final out = <int>[];
  for (var i = 0; i < bits.length; i += 8) {
    out.add(int.parse(bits.sublist(i, i + 8).join(), radix: 2));
  }
  out
    ..addAll([0x4D, 0x56, 0x02])
    ..addAll(base64Url.decode('$token='));
  for (var i = 0; out.length < 76; i++) {
    out.add(i.isEven ? 0xEC : 0x11);
  }
  return Uint8List.fromList(out);
}
