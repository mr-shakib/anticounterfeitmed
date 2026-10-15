/// Recovering a label's data codewords from a camera frame.
///
/// ML Kit finds our labels quickly, but its `rawBytes` is the decoded text,
/// not the symbol's data codewords -- checked on the bundled ML Kit 17.3.0 this
/// app ships, which returns the 31 bytes of the public URL and nothing after
/// it. The token rides after the terminator, so it needs a decoder that exposes
/// every codeword. ZXing does. It runs only on a frame where ML Kit has already
/// found a code that reads as our public URL.
///
/// This runs once per attempt, and an attempt is repeated until a frame reads,
/// so its cost is most of the wait between pointing the camera and seeing a
/// result. On Android, mobile_scanner hands over each frame as a lossless RGBA
/// PNG. Decoding that with the pure-Dart image package and copying it a pixel
/// at a time cost about 145 ms on a desktop and several times that on a phone.
/// Now the PNG is inflated by the platform's native zlib and turned straight
/// into luminance (measured 3.3x faster, identical values), and ZXing first
/// looks only where ML Kit saw the code, then at the whole frame if that fails.
library;

import 'dart:io' show ZLibDecoder;
import 'dart:typed_data';

import 'package:image/image.dart' as img;
import 'package:zxing2/qrcode.dart';

final _hints = DecodeHints()..put(DecodeHintType.tryHarder);

/// One frame to read, and optionally where in it ML Kit saw the code:
/// `[left, top, width, height]` in the frame's pixels. Sendable to an isolate.
typedef FrameRead = ({Uint8List image, List<int>? region});

/// [dataCodewordsFromImage] in a form `compute` can call.
Uint8List? dataCodewordsFromFrame(FrameRead frame) =>
    dataCodewordsFromImage(frame.image, region: frame.region);

/// Returns the data codewords of the QR code in an encoded image (PNG or
/// JPEG), or null when there is none ZXing can read.
///
/// Top-level and synchronous so it can run in a background isolate: decoding a
/// camera frame takes long enough to stall the preview on the UI thread.
Uint8List? dataCodewordsFromImage(Uint8List encoded, {List<int>? region}) {
  final frame = _luminance(encoded);
  if (frame == null) return null;

  // Where ML Kit saw it first: a fraction of the work. If the region is off --
  // a coordinate mismatch would put it in the wrong place -- the whole frame
  // is still read, so the narrow attempt can only save time, never lose a read.
  final crop = _clampRegion(region, frame.width, frame.height);
  if (crop != null) {
    final found = _decode(frame, crop[0], crop[1], crop[2], crop[3]);
    if (found != null) return found;
  }
  return _decode(frame, 0, 0, frame.width, frame.height);
}

Uint8List? _decode(_Luma frame, int left, int top, int width, int height) {
  try {
    final result = QRCodeReader().decode(
      BinaryBitmap(HybridBinarizer(_LumaSource(frame, left, top, width, height))),
      hints: _hints,
    );
    final raw = result.rawBytes;
    return raw == null ? null : Uint8List.fromList(raw);
  } on ReaderException {
    // No code ZXing can read here. The next frame may be better.
    return null;
  }
}

List<int>? _clampRegion(List<int>? region, int width, int height) {
  if (region == null || region.length != 4) return null;
  final left = region[0].clamp(0, width);
  final top = region[1].clamp(0, height);
  final right = (region[0] + region[2]).clamp(0, width);
  final bottom = (region[1] + region[3]).clamp(0, height);
  // Too small to hold a version 6 symbol at any readable size, or the whole
  // frame anyway: not worth a separate attempt.
  if (right - left < 60 || bottom - top < 60) return null;
  if (right - left >= width && bottom - top >= height) return null;
  return [left, top, right - left, bottom - top];
}

class _Luma {
  _Luma(this.pixels, this.width, this.height);
  final Uint8List pixels;
  final int width;
  final int height;
}

/// A frame's luminance, one byte per pixel.
_Luma? _luminance(Uint8List encoded) => _pngLuminance(encoded) ?? _anyLuminance(encoded);

/// Anything the fast path does not handle (JPEG, palette or 16-bit PNG,
/// interlacing), through the image package.
_Luma? _anyLuminance(Uint8List encoded) {
  final image = img.decodeImage(encoded);
  if (image == null) return null;
  final rgb = image.getBytes(order: img.ChannelOrder.rgb);
  final luma = Uint8List(image.width * image.height);
  for (var i = 0, k = 0; i < luma.length; i++, k += 3) {
    luma[i] = (rgb[k] * 77 + rgb[k + 1] * 150 + rgb[k + 2] * 29) >> 8;
  }
  return _Luma(luma, image.width, image.height);
}

/// 8-bit RGB or RGBA, non-interlaced PNG -- what Android's Bitmap.compress
/// writes for a camera frame -- straight to luminance.
_Luma? _pngLuminance(Uint8List b) {
  const signature = [0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A];
  if (b.length < 33) return null;
  for (var i = 0; i < 8; i++) {
    if (b[i] != signature[i]) return null;
  }
  final data = ByteData.sublistView(b);
  var offset = 8;
  var width = 0, height = 0, bpp = 0;
  final compressed = BytesBuilder(copy: false);
  while (offset + 12 <= b.length) {
    final length = data.getUint32(offset);
    final end = offset + 8 + length;
    if (end + 4 > b.length) return null;
    final type = String.fromCharCodes(b, offset + 4, offset + 8);
    if (type == 'IHDR') {
      width = data.getUint32(offset + 8);
      height = data.getUint32(offset + 12);
      final depth = b[offset + 16], colorType = b[offset + 17], interlace = b[offset + 20];
      if (depth != 8 || interlace != 0) return null;
      if (colorType == 6) {
        bpp = 4;
      } else if (colorType == 2) {
        bpp = 3;
      } else {
        return null;
      }
    } else if (type == 'IDAT') {
      compressed.add(Uint8List.sublistView(b, offset + 8, end));
    } else if (type == 'IEND') {
      break;
    }
    offset = end + 4; // skip the CRC
  }
  if (width == 0 || height == 0 || bpp == 0) return null;

  final stride = width * bpp;
  final List<int> inflated;
  try {
    inflated = ZLibDecoder().convert(compressed.takeBytes());
  } on FormatException {
    return null;
  }
  if (inflated.length < (stride + 1) * height) return null;
  final raw = inflated is Uint8List ? inflated : Uint8List.fromList(inflated);

  var previous = Uint8List(stride), current = Uint8List(stride);
  final luma = Uint8List(width * height);
  for (var y = 0; y < height; y++) {
    final base = y * (stride + 1);
    final filter = raw[base];
    for (var x = 0; x < stride; x++) {
      final value = raw[base + 1 + x];
      final left = x >= bpp ? current[x - bpp] : 0;
      final up = previous[x];
      int out;
      switch (filter) {
        case 0:
          out = value;
        case 1:
          out = value + left;
        case 2:
          out = value + up;
        case 3:
          out = value + ((left + up) >> 1);
        case 4:
          final upLeft = x >= bpp ? previous[x - bpp] : 0;
          final p = left + up - upLeft;
          final pa = (p - left).abs(), pb = (p - up).abs(), pc = (p - upLeft).abs();
          out = value + ((pa <= pb && pa <= pc) ? left : (pb <= pc ? up : upLeft));
        default:
          return null;
      }
      current[x] = out & 0xFF;
    }
    final row = y * width;
    for (var x = 0, k = 0; x < width; x++, k += bpp) {
      luma[row + x] = (current[k] * 77 + current[k + 1] * 150 + current[k + 2] * 29) >> 8;
    }
    final swap = previous;
    previous = current;
    current = swap;
  }
  return _Luma(luma, width, height);
}

/// ZXing's view of part of a luminance frame. ZXing reads bytes as signed and
/// masks them, so the same buffer is handed over without a copy.
class _LumaSource extends LuminanceSource {
  _LumaSource(_Luma frame, this._left, this._top, int width, int height)
      : _pixels = Int8List.sublistView(frame.pixels),
        _stride = frame.width,
        super(width, height);

  final Int8List _pixels;
  final int _stride;
  final int _left;
  final int _top;

  @override
  Int8List getRow(int y, Int8List? row) {
    if (row == null || row.length < width) row = Int8List(width);
    final start = (y + _top) * _stride + _left;
    row.setRange(0, width, _pixels, start);
    return row;
  }

  @override
  Int8List getMatrix() {
    if (_left == 0 && _top == 0 && width == _stride) {
      return Int8List.sublistView(_pixels, 0, width * height);
    }
    final matrix = Int8List(width * height);
    for (var y = 0; y < height; y++) {
      final start = (y + _top) * _stride + _left;
      matrix.setRange(y * width, (y + 1) * width, _pixels, start);
    }
    return matrix;
  }
}
