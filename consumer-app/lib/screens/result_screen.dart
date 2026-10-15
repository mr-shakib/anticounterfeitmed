/// The outcome of a check.
///
/// Two rules govern this screen. The wording comes from the fixed strings, and
/// a successful result always carries the clarification that this checks a
/// record rather than the medicine.
library;

import 'dart:async';

import 'package:flutter/material.dart';

import '../app_state.dart';
import '../core/outcomes.dart';
import '../data/api_client.dart';
import '../screens/report_screen.dart';
import '../ui/components.dart';
import '../ui/medicine_information.dart';
import '../ui/theme.dart';

class ResultScreen extends StatefulWidget {
  const ResultScreen({
    super.key,
    required this.outcome,
    required this.checkedAt,
    this.firstVerification = false,
    this.pendingReceipt = false,
    this.operationId,
    this.externalReference = '',
    this.information = const [],
  });

  final Outcome outcome;
  final DateTime checkedAt;
  final bool firstVerification;
  final bool pendingReceipt;

  /// Set when a receipt is still being signed, so the screen can poll for it.
  final String? operationId;
  final String externalReference;

  /// The prescribing information from the preview, shown again here so it is
  /// not lost the moment the check is recorded.
  final List<InformationSection> information;

  @override
  State<ResultScreen> createState() => _ResultScreenState();
}

class _ResultScreenState extends State<ResultScreen> {
  late bool _pending = widget.pendingReceipt;
  Timer? _poll;

  Outcome get outcome => widget.outcome;
  DateTime get checkedAt => widget.checkedAt;
  bool get firstVerification => widget.firstVerification;
  String get externalReference => widget.externalReference;

  @override
  void initState() {
    super.initState();
    if (_pending && widget.operationId != null) _startPolling();
  }

  @override
  void dispose() {
    _poll?.cancel();
    super.dispose();
  }

  /// The verification is already committed at this point. Polling only waits
  /// for the signed receipt, and giving up never undoes the redemption.
  void _startPolling() {
    var attempts = 0;
    _poll = Timer.periodic(const Duration(seconds: 3), (timer) async {
      attempts += 1;
      if (attempts > 10) {
        timer.cancel();
        return;
      }
      try {
        final status =
            await AppScope.of(context).client.operationStatus(widget.operationId!);
        if (status.receiptReady && mounted) {
          timer.cancel();
          setState(() => _pending = false);
        }
      } catch (_) {
        // A failed poll is not a failed verification; keep waiting.
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final state = AppScope.of(context);
    final s = state.strings;
    final tones = AppTones.of(context);
    final theme = Theme.of(context);
    final tone = outcome.tone(tones);

    return Scaffold(
      appBar: AppBar(
        automaticallyImplyLeading: false,
        title: Text(s.appName),
        actions: [
          IconButton(
            tooltip: s.close,
            icon: const Icon(Icons.close_rounded),
            onPressed: () => Navigator.of(context).popUntil((route) => route.isFirst),
          ),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
        children: [
          Container(
            padding: const EdgeInsets.fromLTRB(20, 28, 20, 24),
            decoration: BoxDecoration(
              color: tone.background,
              borderRadius: BorderRadius.circular(24),
              border: Border.all(color: tone.border),
            ),
            child: Column(
              children: [
                Container(
                  width: 76,
                  height: 76,
                  decoration: BoxDecoration(
                    color: theme.colorScheme.surface,
                    shape: BoxShape.circle,
                    border: Border.all(color: tone.border, width: 2),
                  ),
                  child: Icon(outcome.icon, color: tone.foreground, size: 38),
                ),
                const SizedBox(height: 18),
                // The fixed wording from docs/09, word for word.
                Text(
                  s.resultText(outcome),
                  textAlign: TextAlign.center,
                  style: theme.textTheme.titleLarge?.copyWith(
                    color: tone.foreground,
                    height: 1.3,
                  ),
                ),
              ],
            ),
          ),

          // Mandatory on any successful result, and given the same weight as
          // the result itself: a positive outcome must never read as a
          // statement about the medicine.
          if (outcome.showsPackage) ...[
            const SizedBox(height: 12),
            ToneBanner(
              tone: tones.neutral,
              icon: Icons.science_outlined,
              message: s.contentsClarification,
              emphasis: true,
            ),
          ],

          const SizedBox(height: 12),
          SectionCard(
            child: Column(
              children: [
                InfoRow(
                  icon: Icons.schedule_rounded,
                  label: s.checkedAt,
                  value: formatCheckedAt(checkedAt, state.language),
                ),
                if (firstVerification) ...[
                  const Divider(),
                  Padding(
                    padding: const EdgeInsets.symmetric(vertical: 8),
                    child: Row(
                      children: [
                        Icon(Icons.task_alt_rounded, size: 20, color: tones.match.foreground),
                        const SizedBox(width: 12),
                        Expanded(
                          child: Text(
                            s.firstVerificationRecorded,
                            style: theme.textTheme.bodyMedium
                                ?.copyWith(fontWeight: FontWeight.w600),
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
                if (_pending) ...[
                  const Divider(),
                  Padding(
                    padding: const EdgeInsets.symmetric(vertical: 8),
                    child: Row(
                      children: [
                        const SizedBox(
                          width: 18,
                          height: 18,
                          child: CircularProgressIndicator(strokeWidth: 2.5),
                        ),
                        const SizedBox(width: 14),
                        Expanded(child: Text(s.pendingReceipt, style: theme.textTheme.bodyMedium)),
                      ],
                    ),
                  ),
                ],
              ],
            ),
          ),

          if (outcome.showsPackage && widget.information.isNotEmpty) ...[
            const SizedBox(height: 12),
            MedicineInformation(sections: widget.information, strings: s),
          ],
        ],
      ),
      bottomNavigationBar: BottomActionBar(
        children: [
          OutlinedButton.icon(
            icon: const Icon(Icons.flag_outlined),
            label: Text(s.reportTitle),
            onPressed: () => Navigator.of(context).push(
              MaterialPageRoute(
                builder: (_) => ReportScreen(externalReference: externalReference),
              ),
            ),
          ),
          const SizedBox(height: 10),
          FilledButton(
            onPressed: () => Navigator.of(context).popUntil((route) => route.isFirst),
            child: Text(s.close),
          ),
        ],
      ),
    );
  }
}
