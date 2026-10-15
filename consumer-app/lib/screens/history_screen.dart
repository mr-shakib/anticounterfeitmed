/// This installation's own past checks.
///
/// A stored receipt is historical evidence, not current truth: it cannot know
/// about a recall published afterwards. The screen says so, and each entry
/// carries the time the check was actually made.
library;

import 'package:flutter/material.dart';

import '../app_state.dart';
import '../core/outcomes.dart';
import '../data/session_store.dart';
import '../ui/components.dart';
import '../ui/theme.dart';

class HistoryScreen extends StatefulWidget {
  const HistoryScreen({super.key});

  @override
  State<HistoryScreen> createState() => _HistoryScreenState();
}

class _HistoryScreenState extends State<HistoryScreen> {
  List<Receipt>? _receipts;
  bool _started = false;

  // Not initState: reading AppScope there is an error, which debug builds
  // stop on and release builds silently tolerate.
  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_started) return;
    _started = true;
    _load();
  }

  Future<void> _load() async {
    final receipts = await AppScope.of(context).sessionStore.readReceipts();
    if (mounted) setState(() => _receipts = receipts);
  }

  @override
  Widget build(BuildContext context) {
    final state = AppScope.of(context);
    final s = state.strings;
    final tones = AppTones.of(context);
    final theme = Theme.of(context);
    final receipts = _receipts;

    return Scaffold(
      appBar: AppBar(title: Text(s.historyTitle)),
      body: receipts == null
          ? const Center(child: CircularProgressIndicator())
          : receipts.isEmpty
              ? Center(
                  child: Padding(
                    padding: const EdgeInsets.all(32),
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        IconBadge(icon: Icons.history_rounded, tone: tones.neutral, size: 80),
                        const SizedBox(height: 20),
                        Text(
                          s.noHistory,
                          textAlign: TextAlign.center,
                          style: theme.textTheme.titleMedium,
                        ),
                        const SizedBox(height: 24),
                        FilledButton.icon(
                          icon: const Icon(Icons.qr_code_scanner_rounded),
                          label: Text(s.scanTitle),
                          onPressed: () => Navigator.of(context).pop(),
                        ),
                      ],
                    ),
                  ),
                )
              : ListView(
                  padding: const EdgeInsets.fromLTRB(16, 4, 16, 24),
                  children: [
                    // Receipts are history, not today's status (docs/09).
                    ToneBanner(
                      tone: tones.neutral,
                      icon: Icons.info_outline_rounded,
                      message: s.historyNotice,
                    ),
                    const SizedBox(height: 12),
                    // Newest first.
                    for (final r in receipts.reversed) ...[
                      _ReceiptCard(receipt: r, outcome: _outcomeOf(r.outcome)),
                      const SizedBox(height: 10),
                    ],
                  ],
                ),
    );
  }

  Outcome _outcomeOf(String name) => Outcome.values.firstWhere(
        (o) => o.name == name,
        orElse: () => Outcome.serviceUnavailable,
      );
}

class _ReceiptCard extends StatelessWidget {
  const _ReceiptCard({required this.receipt, required this.outcome});

  final Receipt receipt;
  final Outcome outcome;

  @override
  Widget build(BuildContext context) {
    final state = AppScope.of(context);
    final s = state.strings;
    final tones = AppTones.of(context);
    final theme = Theme.of(context);
    final title = receipt.brand.isEmpty ? receipt.batchNumber : receipt.brand;

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            IconBadge(icon: outcome.icon, tone: outcome.tone(tones)),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(title, style: theme.textTheme.titleMedium),
                  if (receipt.brand.isNotEmpty && receipt.batchNumber.isNotEmpty)
                    Text('${s.batch} ${receipt.batchNumber}', style: theme.textTheme.bodySmall),
                  const SizedBox(height: 8),
                  Text(s.resultText(outcome), style: theme.textTheme.bodyMedium),
                  const SizedBox(height: 10),
                  Row(
                    children: [
                      Icon(Icons.schedule_rounded, size: 15, color: tones.muted),
                      const SizedBox(width: 6),
                      Flexible(
                        child: Text(
                          '${s.checkedAt}: ${formatCheckedAt(receipt.checkedAt, state.language)}',
                          style: theme.textTheme.bodySmall,
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
