/// The outcome of a check.
///
/// Two rules govern this screen. The wording comes from the fixed strings, and
/// a successful result always carries the clarification that this checks a
/// record rather than the medicine.
library;

import 'package:flutter/material.dart';

import '../app_state.dart';
import '../core/outcomes.dart';
import '../screens/report_screen.dart';

class ResultScreen extends StatelessWidget {
  const ResultScreen({
    super.key,
    required this.outcome,
    required this.checkedAt,
    this.firstVerification = false,
    this.pendingReceipt = false,
    this.externalReference = '',
  });

  final Outcome outcome;
  final DateTime checkedAt;
  final bool firstVerification;
  final bool pendingReceipt;
  final String externalReference;

  Color _tone(BuildContext context) {
    if (outcome.isRestriction) return Theme.of(context).colorScheme.errorContainer;
    if (outcome.isPositive) return const Color(0xFFE9F7EF);
    return Theme.of(context).colorScheme.surfaceContainerHighest;
  }

  IconData get _icon {
    if (outcome.isRestriction) return Icons.warning_amber_rounded;
    if (outcome.isPositive) return Icons.verified_outlined;
    if (outcome == Outcome.previouslyVerified) return Icons.history;
    return Icons.info_outline;
  }

  @override
  Widget build(BuildContext context) {
    final state = AppScope.of(context);
    final s = state.strings;

    return Scaffold(
      appBar: AppBar(title: Text(s.appName)),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Card(
            color: _tone(context),
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Icon(_icon, size: 36),
                  const SizedBox(height: 12),
                  Text(
                    s.resultText(outcome),
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                  const SizedBox(height: 12),
                  Text(
                    '${s.checkedAt}: ${checkedAt.toLocal()}',
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                  if (firstVerification) ...[
                    const SizedBox(height: 4),
                    Text(s.firstVerificationRecorded,
                        style: Theme.of(context).textTheme.bodySmall),
                  ],
                  if (pendingReceipt) ...[
                    const SizedBox(height: 8),
                    Text(s.pendingReceipt,
                        style: Theme.of(context).textTheme.bodySmall),
                  ],
                ],
              ),
            ),
          ),

          // Mandatory on any successful result. Never let a positive outcome
          // read as a statement about the medicine itself.
          if (outcome.showsPackage)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 12),
              child: Text(
                s.contentsClarification,
                style: Theme.of(context).textTheme.bodyMedium,
              ),
            ),

          const SizedBox(height: 8),
          OutlinedButton.icon(
            icon: const Icon(Icons.flag_outlined),
            label: Text(s.reportTitle),
            onPressed: () => Navigator.of(context).push(
              MaterialPageRoute(
                builder: (_) => ReportScreen(externalReference: externalReference),
              ),
            ),
          ),
          const SizedBox(height: 8),
          FilledButton(
            onPressed: () => Navigator.of(context)
                .popUntil((route) => route.isFirst),
            child: Text(s.close),
          ),
        ],
      ),
    );
  }
}
