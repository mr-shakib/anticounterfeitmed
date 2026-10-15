/// Package preview and the confirmation step.
///
/// Everything shown here came out of a credential whose signature and token
/// binding were checked before this screen was built. Previewing records
/// nothing; only the explicit action does.
library;

import 'package:flutter/material.dart';

import '../app_state.dart';
import '../core/outcomes.dart';
import '../data/api_client.dart';
import '../data/session_store.dart';
import '../ui/components.dart';
import '../ui/medicine_information.dart';
import '../ui/theme.dart';
import 'result_screen.dart';

class PackageScreen extends StatefulWidget {
  const PackageScreen({super.key, required this.prepared});
  final PrepareResult prepared;

  @override
  State<PackageScreen> createState() => _PackageScreenState();
}

class _PackageScreenState extends State<PackageScreen> {
  bool _busy = false;

  /// Stable for this attempt, so a retry after a timeout resolves to the same
  /// operation instead of recording a second check.
  late final String _idempotencyKey =
      '${widget.prepared.unitId}-${DateTime.now().microsecondsSinceEpoch}';

  Future<void> _confirm() async {
    final state = AppScope.of(context);
    setState(() => _busy = true);
    try {
      final result = await state.client.confirm(
        unitId: widget.prepared.unitId!,
        challengeId: widget.prepared.challengeId!,
        idempotencyKey: _idempotencyKey,
      );

      final package = widget.prepared.package;
      await state.sessionStore.addReceipt(
        Receipt(
          unitId: widget.prepared.unitId!,
          outcome: result.outcome.name,
          brand: package?.brand ?? '',
          batchNumber: package?.batchNumber ?? '',
          checkedAt: result.checkedAt,
          firstVerification: result.firstVerificationRecorded,
        ),
      );

      if (!mounted) return;
      Navigator.of(context).pushReplacement(
        MaterialPageRoute(
          builder: (_) => ResultScreen(
            outcome: result.outcome,
            checkedAt: result.checkedAt,
            firstVerification: result.firstVerificationRecorded,
            // The event is committed; only the receipt may still be pending.
            pendingReceipt: !result.receiptReady,
            operationId: result.operationId,
            information: widget.prepared.information,
          ),
        ),
      );
    } on AttestationRejected {
      if (!mounted) return;
      Navigator.of(context).pushReplacement(MaterialPageRoute(
        builder: (_) => ResultScreen(
          outcome: Outcome.attestationFailed,
          checkedAt: DateTime.now(),
        ),
      ));
    } catch (_) {
      if (!mounted) return;
      Navigator.of(context).pushReplacement(MaterialPageRoute(
        builder: (_) => ResultScreen(
          outcome: Outcome.serviceUnavailable,
          checkedAt: DateTime.now(),
        ),
      ));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final state = AppScope.of(context);
    final s = state.strings;
    final tones = AppTones.of(context);
    final theme = Theme.of(context);
    final package = widget.prepared.package;
    final outcome = widget.prepared.outcome;

    return Scaffold(
      appBar: AppBar(title: Text(s.packageTitle)),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(16, 4, 16, 24),
        children: [
          // A restriction comes first and cannot be scrolled past unnoticed.
          if (outcome.isRestriction || !outcome.showsPackage) ...[
            ToneBanner(
              tone: outcome.tone(tones),
              icon: outcome.icon,
              message: s.resultText(outcome),
              emphasis: true,
            ),
            const SizedBox(height: 12),
          ],

          if (package != null) ...[
            Card(
              child: Padding(
                padding: const EdgeInsets.all(18),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Container(
                      width: 56,
                      height: 56,
                      decoration: BoxDecoration(
                        color: tones.match.background,
                        borderRadius: BorderRadius.circular(16),
                      ),
                      child: Icon(Icons.medication_rounded,
                          color: tones.match.foreground, size: 30),
                    ),
                    const SizedBox(width: 14),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(package.brand, style: theme.textTheme.headlineSmall),
                          const SizedBox(height: 2),
                          Text(
                            [package.generic, package.strength]
                                .where((v) => v.isNotEmpty)
                                .join(' · '),
                            style: theme.textTheme.bodyLarge?.copyWith(color: tones.muted),
                          ),
                          const SizedBox(height: 10),
                          Wrap(
                            spacing: 8,
                            runSpacing: 8,
                            children: [
                              if (package.dosageForm.isNotEmpty)
                                _Chip(icon: Icons.category_outlined, text: package.dosageForm),
                              if (package.packDescription.isNotEmpty)
                                _Chip(
                                    icon: Icons.inventory_2_outlined,
                                    text: package.packDescription),
                            ],
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 12),
            SectionCard(
              child: Column(
                children: [
                  InfoRow(icon: Icons.tag_rounded, label: s.batch, value: package.batchNumber),
                  const Divider(),
                  InfoRow(
                    icon: Icons.factory_outlined,
                    label: s.manufacturedOn,
                    value: package.manufacturedOn,
                  ),
                  const Divider(),
                  InfoRow(
                    icon: Icons.event_outlined,
                    label: s.expiresOn,
                    value: package.expiresOn,
                  ),
                ],
              ),
            ),
            if (outcome == Outcome.previouslyVerified) ...[
              const SizedBox(height: 12),
              ToneBanner(
                tone: outcome.tone(tones),
                icon: outcome.icon,
                message: s.resultText(outcome),
              ),
            ],
            if (widget.prepared.information.isNotEmpty) ...[
              const SizedBox(height: 12),
              MedicineInformation(sections: widget.prepared.information, strings: s),
            ],
          ],
        ],
      ),
      bottomNavigationBar: BottomActionBar(
        children: outcome.canConfirm
            ? [
                Row(
                  children: [
                    Icon(Icons.info_outline_rounded, size: 18, color: tones.muted),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(s.verifyExplanation, style: theme.textTheme.bodySmall),
                    ),
                  ],
                ),
                const SizedBox(height: 10),
                FilledButton.icon(
                  onPressed: _busy ? null : _confirm,
                  icon: _busy
                      ? const SizedBox(
                          width: 20,
                          height: 20,
                          child: CircularProgressIndicator(strokeWidth: 2.5),
                        )
                      : const Icon(Icons.fact_check_rounded),
                  label: Text(_busy ? s.checking : s.verifyAction),
                ),
              ]
            : [
                FilledButton(
                  onPressed: () => Navigator.of(context).pop(),
                  child: Text(s.close),
                ),
              ],
      ),
    );
  }
}

class _Chip extends StatelessWidget {
  const _Chip({required this.icon, required this.text});

  final IconData icon;
  final String text;

  @override
  Widget build(BuildContext context) {
    final tones = AppTones.of(context);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: tones.neutral.background,
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: tones.neutral.border),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 15, color: tones.neutral.foreground),
          const SizedBox(width: 6),
          Flexible(
            child: Text(
              text,
              style: Theme.of(context).textTheme.labelMedium?.copyWith(
                    color: tones.neutral.foreground,
                  ),
            ),
          ),
        ],
      ),
    );
  }
}
