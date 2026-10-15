/// The app's look: one palette, in light and dark.
///
/// Light is the default whatever the phone is set to; dark is a choice made in
/// Settings. The teal, surfaces and rounding match the staff portal and the hub.
///
/// Result colours are deliberately restrained. A matching record is shown in
/// the brand teal, not a "safe" green: the app reports that a code matches a
/// record, never that the medicine is genuine (docs/09), and the colour must
/// not say more than the words do.
library;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

/// One tone: a tinted background, the strong colour on it, and its border.
@immutable
class Tone {
  const Tone(this.background, this.foreground, this.border);
  final Color background;
  final Color foreground;
  final Color border;
}

/// The four tones a result or notice can take.
@immutable
class AppTones extends ThemeExtension<AppTones> {
  const AppTones({
    required this.match,
    required this.caution,
    required this.danger,
    required this.neutral,
    required this.muted,
  });

  /// The code matches the record.
  final Tone match;

  /// Worth attention, not alarming: an earlier check, a code not yet active.
  final Tone caution;

  /// A restriction: recalled, blocked, expired, a record that would not verify.
  final Tone danger;

  /// Nothing was decided: offline, service or device problems, plain notices.
  final Tone neutral;

  /// Secondary text.
  final Color muted;

  static AppTones of(BuildContext context) => Theme.of(context).extension<AppTones>()!;

  @override
  AppTones copyWith() => this;

  @override
  AppTones lerp(AppTones? other, double t) => t < 0.5 ? this : (other ?? this);
}

const brandTeal = Color(0xFF0B7A6B);

class _Palette {
  const _Palette({
    required this.brightness,
    required this.primary,
    required this.onPrimary,
    required this.background,
    required this.surface,
    required this.surfaceAlt,
    required this.line,
    required this.lineStrong,
    required this.ink,
    required this.muted,
    required this.tones,
  });

  final Brightness brightness;
  final Color primary;
  final Color onPrimary;
  final Color background;
  final Color surface;
  final Color surfaceAlt;
  final Color line;
  final Color lineStrong;
  final Color ink;
  final Color muted;
  final AppTones tones;
}

const _light = _Palette(
  brightness: Brightness.light,
  primary: brandTeal,
  onPrimary: Colors.white,
  background: Color(0xFFF4F6F8),
  surface: Colors.white,
  surfaceAlt: Color(0xFFF8FAFB),
  line: Color(0xFFE3E8EE),
  lineStrong: Color(0xFFCFD7DF),
  ink: Color(0xFF0F1B2A),
  muted: Color(0xFF64748B),
  tones: AppTones(
    match: Tone(Color(0xFFE7F5F2), Color(0xFF08685B), Color(0xFFB4E0D7)),
    caution: Tone(Color(0xFFFFFAEB), Color(0xFF93500A), Color(0xFFFEDF89)),
    danger: Tone(Color(0xFFFEF3F2), Color(0xFFB42318), Color(0xFFFECDCA)),
    neutral: Tone(Color(0xFFF1F5F9), Color(0xFF334155), Color(0xFFE2E8F0)),
    muted: Color(0xFF64748B),
  ),
);

const _dark = _Palette(
  brightness: Brightness.dark,
  primary: Color(0xFF3CC4AE),
  onPrimary: Color(0xFF00201B),
  background: Color(0xFF0B1220),
  surface: Color(0xFF121B2B),
  surfaceAlt: Color(0xFF172236),
  line: Color(0xFF233049),
  lineStrong: Color(0xFF314260),
  ink: Color(0xFFE6EDF5),
  muted: Color(0xFF94A3B8),
  tones: AppTones(
    match: Tone(Color(0xFF0E2E2A), Color(0xFF6FD9C6), Color(0xFF1C4A43)),
    caution: Tone(Color(0xFF2E2410), Color(0xFFF5C46B), Color(0xFF4A3A16)),
    danger: Tone(Color(0xFF341615), Color(0xFFFF9B92), Color(0xFF5A2421)),
    neutral: Tone(Color(0xFF1A2436), Color(0xFFCBD5E1), Color(0xFF2A3850)),
    muted: Color(0xFF94A3B8),
  ),
);

ThemeData lightTheme() => _build(_light);
ThemeData darkTheme() => _build(_dark);

ThemeData _build(_Palette p) {
  final scheme = ColorScheme.fromSeed(
    seedColor: brandTeal,
    brightness: p.brightness,
  ).copyWith(
    primary: p.primary,
    onPrimary: p.onPrimary,
    surface: p.surface,
    onSurface: p.ink,
    onSurfaceVariant: p.muted,
    outline: p.lineStrong,
    outlineVariant: p.line,
    surfaceContainerLowest: p.surface,
    surfaceContainerLow: p.surfaceAlt,
    surfaceContainer: p.surfaceAlt,
    surfaceContainerHigh: p.surfaceAlt,
    surfaceContainerHighest: p.line,
    error: p.tones.danger.foreground,
  );

  final base = ThemeData(useMaterial3: true, colorScheme: scheme, brightness: p.brightness);
  final text = base.textTheme.apply(bodyColor: p.ink, displayColor: p.ink).copyWith(
        headlineSmall: base.textTheme.headlineSmall
            ?.copyWith(fontWeight: FontWeight.w700, letterSpacing: -0.3, color: p.ink),
        titleLarge: base.textTheme.titleLarge
            ?.copyWith(fontWeight: FontWeight.w700, letterSpacing: -0.2, color: p.ink),
        titleMedium: base.textTheme.titleMedium
            ?.copyWith(fontWeight: FontWeight.w600, color: p.ink),
        labelLarge: base.textTheme.labelLarge
            ?.copyWith(fontWeight: FontWeight.w600, letterSpacing: 0.1),
        bodyMedium: base.textTheme.bodyMedium?.copyWith(height: 1.45, color: p.ink),
        bodySmall: base.textTheme.bodySmall?.copyWith(height: 1.4, color: p.muted),
      );

  final radius12 = BorderRadius.circular(12);
  final rounded = RoundedRectangleBorder(borderRadius: BorderRadius.circular(14));

  return base.copyWith(
    scaffoldBackgroundColor: p.background,
    textTheme: text,
    extensions: [p.tones],
    appBarTheme: AppBarTheme(
      backgroundColor: p.background,
      foregroundColor: p.ink,
      surfaceTintColor: Colors.transparent,
      elevation: 0,
      scrolledUnderElevation: 0,
      centerTitle: false,
      titleTextStyle: text.titleLarge?.copyWith(fontSize: 19),
      systemOverlayStyle: p.brightness == Brightness.light
          ? SystemUiOverlayStyle.dark.copyWith(statusBarColor: Colors.transparent)
          : SystemUiOverlayStyle.light.copyWith(statusBarColor: Colors.transparent),
    ),
    cardTheme: CardThemeData(
      color: p.surface,
      surfaceTintColor: Colors.transparent,
      elevation: 0,
      margin: EdgeInsets.zero,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(18),
        side: BorderSide(color: p.line),
      ),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        minimumSize: const Size(0, 54),
        shape: rounded,
        textStyle: text.labelLarge?.copyWith(fontSize: 16),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        minimumSize: const Size(0, 54),
        shape: rounded,
        foregroundColor: p.ink,
        side: BorderSide(color: p.lineStrong),
        textStyle: text.labelLarge?.copyWith(fontSize: 15),
      ),
    ),
    textButtonTheme: TextButtonThemeData(
      style: TextButton.styleFrom(
        shape: rounded,
        textStyle: text.labelLarge,
      ),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: p.surface,
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
      border: OutlineInputBorder(borderRadius: radius12, borderSide: BorderSide(color: p.lineStrong)),
      enabledBorder:
          OutlineInputBorder(borderRadius: radius12, borderSide: BorderSide(color: p.lineStrong)),
      focusedBorder:
          OutlineInputBorder(borderRadius: radius12, borderSide: BorderSide(color: p.primary, width: 2)),
      labelStyle: TextStyle(color: p.muted),
    ),
    segmentedButtonTheme: SegmentedButtonThemeData(
      style: SegmentedButton.styleFrom(
        side: BorderSide(color: p.lineStrong),
        selectedBackgroundColor: p.tones.match.background,
        selectedForegroundColor: p.primary,
        shape: RoundedRectangleBorder(borderRadius: radius12),
      ),
    ),
    bottomSheetTheme: BottomSheetThemeData(
      backgroundColor: p.surface,
      surfaceTintColor: Colors.transparent,
      showDragHandle: true,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(28)),
      ),
    ),
    snackBarTheme: SnackBarThemeData(
      behavior: SnackBarBehavior.floating,
      shape: RoundedRectangleBorder(borderRadius: radius12),
    ),
    dividerTheme: DividerThemeData(color: p.line, space: 1, thickness: 1),
    listTileTheme: ListTileThemeData(
      iconColor: p.muted,
      shape: RoundedRectangleBorder(borderRadius: radius12),
    ),
    radioTheme: RadioThemeData(
      fillColor: WidgetStateProperty.resolveWith(
        (states) => states.contains(WidgetState.selected) ? p.primary : p.lineStrong,
      ),
    ),
    progressIndicatorTheme: ProgressIndicatorThemeData(color: p.primary),
  );
}
