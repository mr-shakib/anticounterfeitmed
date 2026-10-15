/// The manufacturer's prescribing information, as sections a person can open.
///
/// It is labelled as the manufacturer's, because the platform signs that this
/// is what the manufacturer provided -- not that it is medically correct -- and
/// it carries the standard advice to take medicine as a physician directs.
library;

import 'package:flutter/material.dart';

import '../data/api_client.dart';
import '../l10n/strings.dart';
import 'components.dart';
import 'theme.dart';

class MedicineInformation extends StatelessWidget {
  const MedicineInformation({super.key, required this.sections, required this.strings});

  final List<InformationSection> sections;
  final Strings strings;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final tones = AppTones.of(context);
    final titled = [
      for (final section in sections)
        if (strings.informationHeading(section.field) case final heading?)
          (heading: heading, section: section),
    ];
    if (titled.isEmpty) return const SizedBox.shrink();

    return Card(
      clipBehavior: Clip.antiAlias,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(18, 16, 18, 12),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Icon(Icons.menu_book_rounded, color: tones.match.foreground, size: 22),
                    const SizedBox(width: 10),
                    Expanded(
                      child: Text(strings.informationTitle, style: theme.textTheme.titleMedium),
                    ),
                  ],
                ),
                const SizedBox(height: 4),
                Text(strings.informationSource, style: theme.textTheme.bodySmall),
                const SizedBox(height: 12),
                ToneBanner(
                  tone: tones.caution,
                  icon: Icons.medical_services_outlined,
                  message: strings.physicianAdvice,
                ),
              ],
            ),
          ),
          for (final (index, item) in titled.indexed) ...[
            const Divider(),
            Theme(
              // ExpansionTile draws its own borders; the dividers do that here.
              data: theme.copyWith(dividerColor: Colors.transparent),
              child: ExpansionTile(
                initiallyExpanded: index == 0,
                tilePadding: const EdgeInsets.symmetric(horizontal: 18),
                childrenPadding: const EdgeInsets.fromLTRB(18, 0, 18, 16),
                expandedCrossAxisAlignment: CrossAxisAlignment.start,
                title: Text(
                  item.heading,
                  style: theme.textTheme.bodyLarge?.copyWith(fontWeight: FontWeight.w600),
                ),
                children: [
                  SelectableText(item.section.text, style: theme.textTheme.bodyMedium),
                ],
              ),
            ),
          ],
        ],
      ),
    );
  }
}
