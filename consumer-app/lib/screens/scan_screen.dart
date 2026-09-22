/// The camera screen.
///
/// A scanned code is parsed locally and strictly before anything reaches the
/// network. A code that is not ours is simply not ours: it is never opened as a
/// link and never sent anywhere.
library;

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:mobile_scanner/mobile_scanner.dart';

import '../app_state.dart';
import '../core/label_reader.dart';
import '../core/outcomes.dart';
import '../core/scanned_url.dart';
import '../data/api_client.dart';
import '../l10n/strings.dart';
import 'history_screen.dart';
import 'package_screen.dart';
import 'report_screen.dart';
import 'result_screen.dart';

class ScanScreen extends StatefulWidget {
  const ScanScreen({super.key});

  @override
  State<ScanScreen> createState() => _ScanScreenState();
}

class _ScanScreenState extends State<ScanScreen> {
  final MobileScannerController _controller = MobileScannerController(
    // Every frame, not only new codes: ZXing does not always read a label from
    // the first frame ML Kit saw it in, and a duplicate-suppressing scanner
    // would never offer it another.
    detectionSpeed: DetectionSpeed.normal,
    formats: const [BarcodeFormat.qrCode],
    // The frame is handed to ZXing for the label's hidden record.
    returnImage: true,
    // CameraX's default analysis frame is 640x480, where a 20 mm label can
    // fall to about 2 pixels per module; ZXing needs 2.5 or more.
    //
    // Keep it 4:3. mobile_scanner sizes the preview widget from the analysis
    // frame, while the preview itself stays at CameraX's default 4:3, so a
    // 16:9 request (1280x720) stretches the picture on screen. The new
    // selector reads this as a landscape sensor bound with a 4:3 aspect.
    cameraResolution: Size(1280, 960),
    useNewCameraSelector: true,
  );
  bool _handling = false;
  // A frame is being read by ZXing; later frames wait for it.
  bool _reading = false;
  String _hint = '';

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  Future<void> _onDetect(BarcodeCapture capture) async {
    if (_handling || _reading) return;
    final barcode = capture.barcodes.firstOrNull;
    if (barcode == null) return;

    // The token is in the symbol's data codewords, after the text. ML Kit's
    // rawBytes stops at the text, so a code that reads as our public URL goes
    // to ZXing, which returns every codeword (lib/core/label_reader.dart).
    var scanned = parseScannedBarcode(
      text: barcode.rawValue,
      rawBytes: barcode.rawBytes,
    );
    final frame = capture.image;
    if (scanned == null && barcode.rawValue == publicUrl && frame != null) {
      _reading = true;
      Uint8List? codewords;
      try {
        codewords = await compute(dataCodewordsFromImage, frame);
      } finally {
        _reading = false;
      }
      if (!mounted || _handling) return;
      // ZXing could not read this frame. That is not a verdict on the code:
      // wait for a better frame rather than calling it not ours.
      if (codewords == null) return;
      scanned = parseScannedBarcode(text: barcode.rawValue, rawBytes: codewords);
    }

    if (scanned == null) {
      final hint = AppScope.of(context).strings.notOurCode;
      if (_hint != hint) setState(() => _hint = hint);
      return;
    }

    setState(() {
      _handling = true;
      _hint = '';
    });
    await _controller.stop();
    await _lookUp(scanned.token);
  }

  Future<void> _lookUp(String token) async {
    final state = AppScope.of(context);
    try {
      final prepared = await state.client.prepare(token);
      if (!mounted) return;

      if (prepared.outcome.showsPackage || prepared.outcome.isRestriction) {
        await Navigator.of(context).push(MaterialPageRoute(
          builder: (_) => PackageScreen(prepared: prepared),
        ));
      } else {
        await Navigator.of(context).push(MaterialPageRoute(
          builder: (_) => ResultScreen(
            outcome: prepared.outcome,
            checkedAt: DateTime.now(),
          ),
        ));
      }
    } on AttestationRejected {
      // The SRS specifies a hard stop here. If decision D20 chooses a degraded
      // path instead, this branch is what changes.
      if (mounted) {
        await Navigator.of(context).push(MaterialPageRoute(
          builder: (_) => ResultScreen(
            outcome: Outcome.attestationFailed,
            checkedAt: DateTime.now(),
          ),
        ));
      }
    } catch (_) {
      if (mounted) {
        await Navigator.of(context).push(MaterialPageRoute(
          builder: (_) => ResultScreen(
            outcome: Outcome.serviceUnavailable,
            checkedAt: DateTime.now(),
          ),
        ));
      }
    } finally {
      if (mounted) {
        setState(() => _handling = false);
        await _controller.start();
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final state = AppScope.of(context);
    final s = state.strings;

    return Scaffold(
      appBar: AppBar(
        title: Row(
          children: [
            Image.asset('assets/brand/mark.png', width: 28, height: 28),
            const SizedBox(width: 10),
            Flexible(child: Text(s.scanTitle, overflow: TextOverflow.ellipsis)),
          ],
        ),
        actions: [
          TextButton(
            onPressed: state.toggleLanguage,
            child: Text(
              state.language == AppLanguage.english ? 'বাংলা' : 'English',
              style: TextStyle(color: Theme.of(context).colorScheme.onSurface),
            ),
          ),
          IconButton(
            tooltip: s.historyTitle,
            icon: const Icon(Icons.history),
            onPressed: () => Navigator.of(context).push(
              MaterialPageRoute(builder: (_) => const HistoryScreen()),
            ),
          ),
        ],
      ),
      body: Column(
        children: [
          Expanded(
            child: Stack(
              alignment: Alignment.center,
              children: [
                MobileScanner(
                  controller: _controller,
                  onDetect: _onDetect,
                  // The scanner package's own error text is English-only and
                  // says nothing useful to a patient. Replace it with our own,
                  // in the chosen language, plus a way forward that does not
                  // need a camera at all.
                  errorBuilder: (context, error, child) => _CameraUnavailable(
                    strings: s,
                    onReport: () => Navigator.of(context).push(
                      MaterialPageRoute(builder: (_) => const ReportScreen()),
                    ),
                  ),
                  // Framing guidance belongs to the preview, so it disappears
                  // with it. Drawn as a stack sibling it would sit on top of
                  // the camera-unavailable message and cut the text in half.
                  overlayBuilder: (context, constraints) => IgnorePointer(
                    child: Center(
                      child: Container(
                        width: 220,
                        height: 220,
                        decoration: BoxDecoration(
                          border: Border.all(color: Colors.white70, width: 3),
                          borderRadius: BorderRadius.circular(12),
                        ),
                      ),
                    ),
                  ),
                ),
                if (_handling)
                  Container(
                    color: Colors.black54,
                    child: Center(
                      child: Column(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          const CircularProgressIndicator(),
                          const SizedBox(height: 12),
                          Text(s.checking,
                              style: const TextStyle(color: Colors.white)),
                        ],
                      ),
                    ),
                  ),
              ],
            ),
          ),
          Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              children: [
                Text(s.scanInstruction, textAlign: TextAlign.center),
                if (_hint.isNotEmpty) ...[
                  const SizedBox(height: 8),
                  Text(_hint,
                      style: TextStyle(color: Theme.of(context).colorScheme.error)),
                ],
                const SizedBox(height: 8),
                OutlinedButton.icon(
                  icon: const Icon(Icons.flashlight_on_outlined),
                  label: Text(s.torch),
                  onPressed: () => _controller.toggleTorch(),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}


/// Shown in place of the preview when no camera is usable.
class _CameraUnavailable extends StatelessWidget {
  const _CameraUnavailable({required this.strings, required this.onReport});

  final Strings strings;
  final VoidCallback onReport;

  @override
  Widget build(BuildContext context) {
    return ColoredBox(
      color: Colors.black,
      child: Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.no_photography_outlined,
                  color: Colors.white70, size: 40),
              const SizedBox(height: 12),
              Text(
                strings.cameraUnavailable,
                textAlign: TextAlign.center,
                style: const TextStyle(color: Colors.white, fontSize: 16),
              ),
              const SizedBox(height: 8),
              Text(
                strings.cameraHelp,
                textAlign: TextAlign.center,
                style: const TextStyle(color: Colors.white70, fontSize: 13),
              ),
              const SizedBox(height: 16),
              OutlinedButton.icon(
                icon: const Icon(Icons.flag_outlined, color: Colors.white),
                label: Text(strings.reportTitle,
                    style: const TextStyle(color: Colors.white)),
                onPressed: onReport,
              ),
            ],
          ),
        ),
      ),
    );
  }
}
