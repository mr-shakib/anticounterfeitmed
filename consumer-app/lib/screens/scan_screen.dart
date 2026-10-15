/// The camera screen.
///
/// A scanned code is parsed locally and strictly before anything reaches the
/// network. A code that is not ours is simply not ours: it is never opened as a
/// link and never sent anywhere.
library;

import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:mobile_scanner/mobile_scanner.dart';

import '../app_state.dart';
import '../core/label_reader.dart';
import '../core/outcomes.dart';
import '../core/scanned_url.dart';
import '../data/api_client.dart';
import '../l10n/strings.dart';
import '../ui/settings_sheet.dart';
import '../ui/theme.dart';
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
  _Hint? _hint;
  Timer? _hintTimer;
  // Frames where ML Kit saw our code but ZXing could not read the token.
  int _missedReads = 0;

  @override
  void dispose() {
    _hintTimer?.cancel();
    _controller.dispose();
    super.dispose();
  }

  /// Shows a hint over the camera for a moment. A newer hint replaces it.
  void _showHint(_Hint hint) {
    _hintTimer?.cancel();
    _hintTimer = Timer(const Duration(milliseconds: 2500), () {
      if (mounted) setState(() => _hint = null);
    });
    if (_hint != hint) setState(() => _hint = hint);
  }

  /// Where ML Kit saw the code, padded by half its size on every side, as
  /// `[left, top, width, height]`. The reader clamps it to the frame, and falls
  /// back to the whole frame when it is wrong.
  static List<int>? _regionAround(List<Offset> corners) {
    if (corners.length < 3) return null;
    final xs = corners.map((c) => c.dx), ys = corners.map((c) => c.dy);
    final left = xs.reduce(math.min), right = xs.reduce(math.max);
    final top = ys.reduce(math.min), bottom = ys.reduce(math.max);
    final pad = math.max(right - left, bottom - top) / 2;
    return [
      (left - pad).floor(),
      (top - pad).floor(),
      (right - left + 2 * pad).ceil(),
      (bottom - top + 2 * pad).ceil(),
    ];
  }

  /// The code's side in frame pixels: its longest edge between corners.
  /// Independent of how the frame is rotated.
  static double _sideOf(List<Offset> corners) {
    var side = 0.0;
    for (var i = 0; i < corners.length; i++) {
      side = math.max(side, (corners[i] - corners[(i + 1) % corners.length]).distance);
    }
    return side;
  }

  /// After a frame ML Kit saw but ZXing could not read: say what would help,
  /// rather than retrying in silence.
  void _guide(List<Offset> corners) {
    _missedReads += 1;
    final s = AppScope.of(context).strings;
    // Our symbol is 41 modules across, and ZXing reads it reliably from about
    // 3 pixels a module (measured on the label vectors: 2.3 when sharp, 3.3
    // with slight blur). Below that, nearer is what helps; above it, blur.
    final pixelsPerModule = _sideOf(corners) / 41;
    if (pixelsPerModule > 0 && pixelsPerModule < 3.0) {
      _showHint(_Hint(s.moveCloser, Icons.zoom_in_rounded));
    } else if (_missedReads >= 2) {
      _showHint(_Hint(s.holdSteady, Icons.pan_tool_alt_outlined));
    }
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
        codewords = await compute(
          dataCodewordsFromFrame,
          (image: frame, region: _regionAround(barcode.corners)),
        );
      } finally {
        _reading = false;
      }
      if (!mounted || _handling) return;
      // ZXing could not read this frame. That is not a verdict on the code:
      // wait for a better frame rather than calling it not ours -- and tell
      // the person what would make the next one better.
      if (codewords == null) {
        _guide(barcode.corners);
        return;
      }
      scanned = parseScannedBarcode(text: barcode.rawValue, rawBytes: codewords);
    }

    if (scanned == null) {
      _showHint(_Hint(AppScope.of(context).strings.notOurCode, Icons.qr_code_2_rounded,
          warning: true));
      return;
    }

    _hintTimer?.cancel();
    setState(() {
      _handling = true;
      _hint = null;
      _missedReads = 0;
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
    final surface = Theme.of(context).colorScheme.surface;

    // The camera is dark whatever the theme, so the status bar over it is light.
    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: SystemUiOverlayStyle.light.copyWith(statusBarColor: Colors.transparent),
      child: Scaffold(
        backgroundColor: Colors.black,
        body: Column(
          children: [
            Expanded(
              child: Stack(
                fit: StackFit.expand,
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
                    overlayBuilder: (context, constraints) =>
                        IgnorePointer(child: _Viewfinder(scanning: !_handling)),
                  ),
                  Positioned(
                    top: 0,
                    left: 0,
                    right: 0,
                    child: _TopBar(
                      languageLabel:
                          state.language == AppLanguage.english ? 'বাংলা' : 'English',
                      onLanguage: state.toggleLanguage,
                    ),
                  ),
                  if (_hint != null)
                    Positioned(
                      left: 24,
                      right: 24,
                      bottom: 44,
                      child: _HintPill(hint: _hint!),
                    ),
                  if (_handling) _CheckingOverlay(label: s.checking),
                  // The panel's rounded top, drawn over the bottom of the
                  // preview so the panel appears to rest on the camera.
                  Positioned(
                    left: 0,
                    right: 0,
                    bottom: 0,
                    height: 24,
                    child: DecoratedBox(
                      decoration: BoxDecoration(
                        color: surface,
                        borderRadius: const BorderRadius.vertical(top: Radius.circular(24)),
                      ),
                    ),
                  ),
                ],
              ),
            ),
            _ScanPanel(
              strings: s,
              controller: _controller,
              onHistory: () => Navigator.of(context).push(
                MaterialPageRoute(builder: (_) => const HistoryScreen()),
              ),
              onReport: () => Navigator.of(context).push(
                MaterialPageRoute(builder: (_) => const ReportScreen()),
              ),
              onSettings: () => showSettingsSheet(context),
            ),
          ],
        ),
      ),
    );
  }
}

/// The brand and the language switch, floating over the camera. The switch
/// stays here, one tap away, because someone may not read the other language.
class _TopBar extends StatelessWidget {
  const _TopBar({required this.languageLabel, required this.onLanguage});

  final String languageLabel;
  final VoidCallback onLanguage;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: const BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [Color(0x99000000), Color(0x00000000)],
        ),
      ),
      child: SafeArea(
        bottom: false,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(16, 8, 12, 24),
          child: Row(
            children: [
              ClipOval(
                child: Image.asset('assets/brand/mark.png', width: 34, height: 34),
              ),
              const SizedBox(width: 10),
              const Expanded(
                child: Text(
                  'Anticounterfeit Med',
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    color: Colors.white,
                    fontSize: 17,
                    fontWeight: FontWeight.w700,
                    letterSpacing: -0.2,
                  ),
                ),
              ),
              const SizedBox(width: 12),
              _GlassButton(
                onPressed: onLanguage,
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const Icon(Icons.translate_rounded, color: Colors.white, size: 18),
                    const SizedBox(width: 6),
                    Text(
                      languageLabel,
                      style: const TextStyle(
                        color: Colors.white,
                        fontWeight: FontWeight.w600,
                        fontSize: 14,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// A translucent control that stays readable over any camera image.
class _GlassButton extends StatelessWidget {
  const _GlassButton({required this.onPressed, required this.child});

  final VoidCallback onPressed;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: const Color(0x59000000),
      shape: const StadiumBorder(side: BorderSide(color: Color(0x33FFFFFF))),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onPressed,
        child: ConstrainedBox(
          constraints: const BoxConstraints(minWidth: 44, minHeight: 44),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 12),
            child: Center(widthFactor: 1, child: child),
          ),
        ),
      ),
    );
  }
}

/// The scanning window: a dimmed surround, corner marks, and a moving line
/// while the camera is looking for a code.
class _Viewfinder extends StatefulWidget {
  const _Viewfinder({required this.scanning});

  final bool scanning;

  @override
  State<_Viewfinder> createState() => _ViewfinderState();
}

class _ViewfinderState extends State<_Viewfinder> with SingleTickerProviderStateMixin {
  late final AnimationController _sweep = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 2200),
  );

  @override
  void initState() {
    super.initState();
    if (widget.scanning) _sweep.repeat(reverse: true);
  }

  @override
  void didUpdateWidget(_Viewfinder old) {
    super.didUpdateWidget(old);
    if (widget.scanning && !_sweep.isAnimating) {
      _sweep.repeat(reverse: true);
    } else if (!widget.scanning && _sweep.isAnimating) {
      _sweep.stop();
    }
  }

  @override
  void dispose() {
    _sweep.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _sweep,
      builder: (context, _) => CustomPaint(
        size: Size.infinite,
        painter: _ViewfinderPainter(
          progress: Curves.easeInOut.transform(_sweep.value),
          showLine: widget.scanning,
          accent: const Color(0xFF3CC4AE),
        ),
      ),
    );
  }
}

class _ViewfinderPainter extends CustomPainter {
  _ViewfinderPainter({required this.progress, required this.showLine, required this.accent});

  final double progress;
  final bool showLine;
  final Color accent;

  @override
  void paint(Canvas canvas, Size size) {
    final side = (size.shortestSide * 0.68).clamp(180.0, 300.0);
    // Slightly above centre, away from the panel's rounded edge.
    final center = Offset(size.width / 2, size.height / 2 - 8);
    final window = Rect.fromCenter(center: center, width: side, height: side);
    final rounded = RRect.fromRectAndRadius(window, const Radius.circular(24));

    // Dim everything but the window.
    final surround = Path()
      ..fillType = PathFillType.evenOdd
      ..addRect(Offset.zero & size)
      ..addRRect(rounded);
    canvas.drawPath(surround, Paint()..color = const Color(0x8C000000));

    // Corner marks.
    const arm = 34.0;
    const r = 24.0;
    final corner = Paint()
      ..color = Colors.white
      ..style = PaintingStyle.stroke
      ..strokeWidth = 4.5
      ..strokeCap = StrokeCap.round;
    final l = window.left, t = window.top, rt = window.right, b = window.bottom;
    canvas
      ..drawPath(
          Path()
            ..moveTo(l, t + arm)
            ..lineTo(l, t + r)
            ..arcToPoint(Offset(l + r, t), radius: const Radius.circular(r))
            ..lineTo(l + arm, t),
          corner)
      ..drawPath(
          Path()
            ..moveTo(rt - arm, t)
            ..lineTo(rt - r, t)
            ..arcToPoint(Offset(rt, t + r), radius: const Radius.circular(r))
            ..lineTo(rt, t + arm),
          corner)
      ..drawPath(
          Path()
            ..moveTo(rt, b - arm)
            ..lineTo(rt, b - r)
            ..arcToPoint(Offset(rt - r, b), radius: const Radius.circular(r))
            ..lineTo(rt - arm, b),
          corner)
      ..drawPath(
          Path()
            ..moveTo(l + arm, b)
            ..lineTo(l + r, b)
            ..arcToPoint(Offset(l, b - r), radius: const Radius.circular(r))
            ..lineTo(l, b - arm),
          corner);

    if (!showLine) return;
    final y = window.top + 18 + (window.height - 36) * progress;
    final line = Rect.fromLTWH(window.left + 18, y - 1.5, window.width - 36, 3);
    canvas.drawRRect(
      RRect.fromRectAndRadius(line, const Radius.circular(2)),
      Paint()
        ..shader = LinearGradient(
          colors: [accent.withValues(alpha: 0), accent, accent.withValues(alpha: 0)],
        ).createShader(line),
    );
    // A soft glow under the line.
    canvas.drawRect(
      Rect.fromLTWH(line.left, y - 14, line.width, 28),
      Paint()
        ..shader = LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [
            accent.withValues(alpha: 0),
            accent.withValues(alpha: 0.18),
            accent.withValues(alpha: 0),
          ],
        ).createShader(Rect.fromLTWH(line.left, y - 14, line.width, 28)),
    );
  }

  @override
  bool shouldRepaint(_ViewfinderPainter old) =>
      old.progress != progress || old.showLine != showLine;
}

/// A short message over the camera.
@immutable
class _Hint {
  const _Hint(this.text, this.icon, {this.warning = false});

  final String text;
  final IconData icon;

  /// Red for "not one of our codes"; otherwise neutral guidance.
  final bool warning;

  @override
  bool operator ==(Object other) =>
      other is _Hint && other.text == text && other.warning == warning;

  @override
  int get hashCode => Object.hash(text, warning);
}

/// "Move closer", "Hold steady", or "That is not one of our codes".
class _HintPill extends StatelessWidget {
  const _HintPill({required this.hint});

  final _Hint hint;

  @override
  Widget build(BuildContext context) {
    final text = hint.text;
    return Center(
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
        decoration: BoxDecoration(
          color: hint.warning ? const Color(0xE6B42318) : const Color(0xD90F1B2A),
          borderRadius: BorderRadius.circular(999),
          border: hint.warning ? null : Border.all(color: const Color(0x33FFFFFF)),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(hint.icon, color: Colors.white, size: 18),
            const SizedBox(width: 8),
            Flexible(
              child: Text(
                text,
                textAlign: TextAlign.center,
                style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w600),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Shown while a scanned code is being looked up.
class _CheckingOverlay extends StatelessWidget {
  const _CheckingOverlay({required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    return ColoredBox(
      color: const Color(0x99000000),
      child: Center(
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 28, vertical: 22),
          decoration: BoxDecoration(
            color: Theme.of(context).colorScheme.surface,
            borderRadius: BorderRadius.circular(20),
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const SizedBox(
                width: 34,
                height: 34,
                child: CircularProgressIndicator(strokeWidth: 3.5),
              ),
              const SizedBox(height: 14),
              Text(label, style: Theme.of(context).textTheme.titleMedium),
            ],
          ),
        ),
      ),
    );
  }
}

/// What to do, and everything else the screen offers: the light, past
/// checks, reporting without a scan, and settings.
class _ScanPanel extends StatelessWidget {
  const _ScanPanel({
    required this.strings,
    required this.controller,
    required this.onHistory,
    required this.onReport,
    required this.onSettings,
  });

  final Strings strings;
  final MobileScannerController controller;
  final VoidCallback onHistory;
  final VoidCallback onReport;
  final VoidCallback onSettings;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final tones = AppTones.of(context);
    return ColoredBox(
      color: theme.colorScheme.surface,
      child: SafeArea(
        top: false,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(20, 0, 20, 10),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Container(
                    width: 44,
                    height: 44,
                    decoration: BoxDecoration(
                      color: tones.match.background,
                      borderRadius: BorderRadius.circular(14),
                    ),
                    child: Icon(Icons.qr_code_scanner_rounded, color: tones.match.foreground),
                  ),
                  const SizedBox(width: 14),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(strings.scanTitle, style: theme.textTheme.titleLarge),
                        const SizedBox(height: 4),
                        Text(
                          strings.scanInstruction,
                          style: theme.textTheme.bodyMedium?.copyWith(color: tones.muted),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 16),
              IntrinsicHeight(
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Expanded(
                      child: ValueListenableBuilder<MobileScannerState>(
                        valueListenable: controller,
                        builder: (context, camera, _) {
                          final on = camera.torchState == TorchState.on;
                          return _ActionTile(
                            icon: on ? Icons.flashlight_on_rounded : Icons.flashlight_off_rounded,
                            label: strings.torch,
                            active: on,
                            onTap: () => controller.toggleTorch(),
                          );
                        },
                      ),
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: _ActionTile(
                        icon: Icons.history_rounded,
                        label: strings.historyTitle,
                        onTap: onHistory,
                      ),
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: _ActionTile(
                        icon: Icons.flag_outlined,
                        label: strings.reportTitle,
                        onTap: onReport,
                      ),
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: _ActionTile(
                        icon: Icons.tune_rounded,
                        label: strings.settingsTitle,
                        onTap: onSettings,
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 10),
              Text(
                'Developed by Shakib Howlader',
                textAlign: TextAlign.center,
                style: theme.textTheme.bodySmall?.copyWith(color: tones.muted),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// An icon over a short label. The label may wrap, so Bangla fits too.
class _ActionTile extends StatelessWidget {
  const _ActionTile({
    required this.icon,
    required this.label,
    required this.onTap,
    this.active = false,
  });

  final IconData icon;
  final String label;
  final VoidCallback onTap;
  final bool active;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final tones = AppTones.of(context);
    final fg = active ? tones.match.foreground : theme.colorScheme.onSurface;
    return Material(
      color: active ? tones.match.background : theme.colorScheme.surfaceContainerLow,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(16),
        side: BorderSide(color: active ? tones.match.border : theme.colorScheme.outlineVariant),
      ),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 12),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(icon, color: fg, size: 24),
              const SizedBox(height: 6),
              Text(
                label,
                textAlign: TextAlign.center,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: theme.textTheme.labelMedium?.copyWith(color: fg, height: 1.2),
              ),
            ],
          ),
        ),
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
      color: const Color(0xFF0B1220),
      child: Center(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(28, 96, 28, 48),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Container(
                width: 72,
                height: 72,
                decoration: const BoxDecoration(
                  color: Color(0x1FFFFFFF),
                  shape: BoxShape.circle,
                ),
                child: const Icon(Icons.no_photography_outlined, color: Colors.white, size: 34),
              ),
              const SizedBox(height: 18),
              Text(
                strings.cameraUnavailable,
                textAlign: TextAlign.center,
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 18,
                  fontWeight: FontWeight.w700,
                ),
              ),
              const SizedBox(height: 8),
              Text(
                strings.cameraHelp,
                textAlign: TextAlign.center,
                style: const TextStyle(color: Color(0xCCFFFFFF), fontSize: 14, height: 1.45),
              ),
              const SizedBox(height: 20),
              OutlinedButton.icon(
                style: OutlinedButton.styleFrom(
                  foregroundColor: Colors.white,
                  side: const BorderSide(color: Color(0x66FFFFFF)),
                ),
                icon: const Icon(Icons.flag_outlined),
                label: Text(strings.reportTitle),
                onPressed: onReport,
              ),
            ],
          ),
        ),
      ),
    );
  }
}
