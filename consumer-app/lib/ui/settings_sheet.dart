/// Language and appearance, from a sheet on the scan screen.
library;

import 'package:flutter/material.dart';

import '../app_state.dart';
import '../l10n/strings.dart';
import 'theme.dart';

Future<void> showSettingsSheet(BuildContext context) {
  return showModalBottomSheet<void>(
    context: context,
    builder: (_) => const _SettingsSheet(),
  );
}

class _SettingsSheet extends StatelessWidget {
  const _SettingsSheet();

  @override
  Widget build(BuildContext context) {
    final state = AppScope.of(context);
    final s = state.strings;
    final muted = AppTones.of(context).muted;

    Widget label(String text, IconData icon) => Padding(
          padding: const EdgeInsets.only(bottom: 10),
          child: Row(
            children: [
              Icon(icon, size: 20, color: muted),
              const SizedBox(width: 8),
              Text(text, style: Theme.of(context).textTheme.titleSmall),
            ],
          ),
        );

    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(20, 0, 20, 20),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(s.settingsTitle, style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 20),
            label(s.languageLabel, Icons.translate_rounded),
            SegmentedButton<AppLanguage>(
              showSelectedIcon: false,
              segments: const [
                ButtonSegment(value: AppLanguage.english, label: Text('English')),
                ButtonSegment(value: AppLanguage.bangla, label: Text('বাংলা')),
              ],
              selected: {state.language},
              onSelectionChanged: (v) => state.setLanguage(v.first),
            ),
            const SizedBox(height: 22),
            label(s.appearanceLabel, Icons.contrast_rounded),
            SegmentedButton<ThemeMode>(
              showSelectedIcon: false,
              segments: [
                ButtonSegment(
                  value: ThemeMode.light,
                  label: Text(s.themeLight),
                ),
                ButtonSegment(
                  value: ThemeMode.dark,
                  label: Text(s.themeDark),
                ),
                ButtonSegment(
                  value: ThemeMode.system,
                  label: Text(s.themeSystem),
                ),
              ],
              selected: {state.themeMode},
              onSelectionChanged: (v) => state.setThemeMode(v.first),
            ),
          ],
        ),
      ),
    );
  }
}
