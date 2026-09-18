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

  Widget _row(String label, String value) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 4),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            SizedBox(
              width: 130,
              child: Text(label, style: const TextStyle(color: Colors.grey)),
            ),
            Expanded(child: Text(value)),
          ],
        ),
      );

  @override
  Widget build(BuildContext context) {
    final state = AppScope.of(context);
    final s = state.strings;
    final package = widget.prepared.package;
    final outcome = widget.prepared.outcome;

    return Scaffold(
      appBar: AppBar(title: Text(s.packageTitle)),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          if (outcome.isRestriction || !outcome.showsPackage)
            Card(
              color: Theme.of(context).colorScheme.errorContainer,
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Text(s.resultText(outcome)),
              ),
            ),

          if (package != null) ...[
            Card(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(package.brand,
                        style: Theme.of(context).textTheme.titleLarge),
                    const SizedBox(height: 12),
                    _row(s.generic, package.generic),
                    _row(s.strength, package.strength),
                    _row(s.dosageForm, package.dosageForm),
                    _row(s.packDescription, package.packDescription),
                    _row(s.batch, package.batchNumber),
                    _row(s.manufacturedOn, package.manufacturedOn),
                    _row(s.expiresOn, package.expiresOn),
                  ],
                ),
              ),
            ),
            if (outcome == Outcome.previouslyVerified)
              Card(
                color: Theme.of(context).colorScheme.surfaceContainerHighest,
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Text(s.resultText(outcome)),
                ),
              ),
          ],

          const SizedBox(height: 16),
          if (outcome.canConfirm) ...[
            Text(s.verifyExplanation,
                style: Theme.of(context).textTheme.bodySmall),
            const SizedBox(height: 8),
            FilledButton(
              onPressed: _busy ? null : _confirm,
              child: Text(_busy ? s.checking : s.verifyAction),
            ),
          ] else
            FilledButton(
              onPressed: () => Navigator.of(context).pop(),
              child: Text(s.close),
            ),
        ],
      ),
    );
  }
}
