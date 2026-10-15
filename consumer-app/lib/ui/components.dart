/// Building blocks shared by every screen.
library;

import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../core/outcomes.dart';
import '../l10n/strings.dart';
import 'theme.dart';

/// How each outcome looks. The words come from l10n/strings.dart; this only
/// decides colour and icon, and never makes a result look more certain than
/// its wording.
extension OutcomeLook on Outcome {
  Tone tone(AppTones tones) => switch (this) {
        Outcome.verifiedFirst => tones.match,
        Outcome.previouslyVerified ||
        Outcome.notActivated ||
        Outcome.notFound =>
          tones.caution,
        Outcome.expired ||
        Outcome.recalled ||
        Outcome.restricted ||
        Outcome.invalidCredential =>
          tones.danger,
        Outcome.serviceUnavailable ||
        Outcome.attestationFailed ||
        Outcome.offline =>
          tones.neutral,
      };

  IconData get icon => switch (this) {
        // A record check, not a seal of approval.
        Outcome.verifiedFirst => Icons.fact_check_rounded,
        Outcome.previouslyVerified => Icons.history_rounded,
        Outcome.notActivated => Icons.hourglass_empty_rounded,
        Outcome.notFound => Icons.search_off_rounded,
        Outcome.expired => Icons.event_busy_rounded,
        Outcome.recalled => Icons.campaign_rounded,
        Outcome.restricted => Icons.block_rounded,
        Outcome.invalidCredential => Icons.gpp_bad_rounded,
        Outcome.serviceUnavailable => Icons.cloud_off_rounded,
        Outcome.attestationFailed => Icons.phonelink_lock_rounded,
        Outcome.offline => Icons.wifi_off_rounded,
      };
}

/// A check's time, as a person reads it.
String formatCheckedAt(DateTime time, AppLanguage language) {
  final locale = language == AppLanguage.bangla ? 'bn' : 'en';
  return DateFormat('d MMM y, h:mm a', locale).format(time.toLocal());
}

/// A round, tinted icon.
class IconBadge extends StatelessWidget {
  const IconBadge({super.key, required this.icon, required this.tone, this.size = 44});

  final IconData icon;
  final Tone tone;
  final double size;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        color: tone.background,
        shape: BoxShape.circle,
        border: Border.all(color: tone.border),
      ),
      child: Icon(icon, color: tone.foreground, size: size * 0.52),
    );
  }
}

/// A tinted notice with an icon.
class ToneBanner extends StatelessWidget {
  const ToneBanner({
    super.key,
    required this.tone,
    required this.icon,
    required this.message,
    this.emphasis = false,
  });

  final Tone tone;
  final IconData icon;
  final String message;

  /// Larger, bolder text: for a restriction that must not be skimmed past.
  final bool emphasis;

  @override
  Widget build(BuildContext context) {
    final style = emphasis
        ? Theme.of(context).textTheme.titleMedium
        : Theme.of(context).textTheme.bodyMedium;
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: tone.background,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: tone.border),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, color: tone.foreground, size: emphasis ? 26 : 22),
          const SizedBox(width: 12),
          Expanded(
            child: Text(message, style: style?.copyWith(color: tone.foreground)),
          ),
        ],
      ),
    );
  }
}

/// A white card with an optional heading.
class SectionCard extends StatelessWidget {
  const SectionCard({super.key, this.title, required this.child, this.padding});

  final String? title;
  final Widget child;
  final EdgeInsets? padding;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: padding ?? const EdgeInsets.fromLTRB(18, 16, 18, 16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            if (title != null) ...[
              Text(
                title!.toUpperCase(),
                style: Theme.of(context).textTheme.labelSmall?.copyWith(
                      color: AppTones.of(context).muted,
                      letterSpacing: 0.8,
                      fontWeight: FontWeight.w700,
                    ),
              ),
              const SizedBox(height: 10),
            ],
            child,
          ],
        ),
      ),
    );
  }
}

/// One labelled value, with an icon.
class InfoRow extends StatelessWidget {
  const InfoRow({super.key, required this.icon, required this.label, required this.value});

  final IconData icon;
  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    final muted = AppTones.of(context).muted;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: Row(
        children: [
          Icon(icon, size: 20, color: muted),
          const SizedBox(width: 12),
          Expanded(
            child: Text(label, style: Theme.of(context).textTheme.bodyMedium?.copyWith(color: muted)),
          ),
          const SizedBox(width: 12),
          Flexible(
            flex: 2,
            child: Text(
              value.isEmpty ? '—' : value,
              textAlign: TextAlign.end,
              style: Theme.of(context).textTheme.bodyMedium?.copyWith(fontWeight: FontWeight.w600),
            ),
          ),
        ],
      ),
    );
  }
}

/// Buttons pinned to the bottom of a screen, above the system navigation.
class BottomActionBar extends StatelessWidget {
  const BottomActionBar({super.key, required this.children});

  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return DecoratedBox(
      decoration: BoxDecoration(
        color: theme.colorScheme.surface,
        border: Border(top: BorderSide(color: theme.dividerTheme.color ?? Colors.transparent)),
      ),
      child: SafeArea(
        top: false,
        minimum: const EdgeInsets.fromLTRB(16, 12, 16, 12),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: children,
        ),
      ),
    );
  }
}
