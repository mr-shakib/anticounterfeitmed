/// Recovering a label's data codewords from a camera frame.
///
/// ML Kit finds our labels quickly, but its `rawBytes` is the decoded text,
/// not the symbol's data codewords -- checked on the bundled ML Kit 17.3.0 this
/// app ships, which returns the 31 bytes of the public URL and nothing after
/// it. The token rides after the terminator, so it needs a decoder that exposes
/// every codeword. ZXing does. It runs only on a frame where ML Kit has already
/// found a code that reads as our public URL.
library;

import 'dart:typed_data';

import 'package:image/image.dart' as img;
import 'package:zxing2/qrcode.dart';

final _hints = DecodeHints()..put(DecodeHintType.tryHarder);

/// Returns the data codewords of the QR code in an encoded image (JPEG or
/// PNG), or null when there is none ZXing can read.
///
/// Top-level and synchronous so it can run in a background isolate: decoding a
/// camera frame takes long enough to stall the preview on the UI thread.
Uint8List? dataCodewordsFromImage(Uint8List encoded) {
  final image = img.decodeImage(encoded);
  if (image == null) return null;

  final pixels = Int32List(image.width * image.height);
  var i = 0;
  for (final pixel in image) {
    pixels[i++] = 0xFF000000 |
        (pixel.r.toInt() << 16) |
        (pixel.g.toInt() << 8) |
        pixel.b.toInt();
  }

  try {
    final result = QRCodeReader().decode(
      BinaryBitmap(
        HybridBinarizer(RGBLuminanceSource(image.width, image.height, pixels)),
      ),
      hints: _hints,
    );
    final raw = result.rawBytes;
    return raw == null ? null : Uint8List.fromList(raw);
  } on ReaderException {
    // No code ZXing can read in this frame. The next one may be better.
    return null;
  }
}
