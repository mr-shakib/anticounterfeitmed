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

class HistoryScreen extends StatefulWidget {
  const HistoryScreen({super.key});

  @override
  State<HistoryScreen> createState() => _HistoryScreenState();
}

class _HistoryScreenState extends State<HistoryScreen> {
  List<Receipt>? _receipts;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final receipts = await AppScope.of(context).sessionStore.readReceipts();
    if (mounted) setState(() => _receipts = receipts);
  }

  @override
  Widget build(BuildContext context) {
    final s = AppScope.of(context).strings;
    final receipts = _receipts;

    return Scaffold(
      appBar: AppBar(title: Text(s.historyTitle)),
      body: receipts == null
          ? const Center(child: CircularProgressIndicator())
          : receipts.isEmpty
              ? Center(
                  child: Padding(
                    padding: const EdgeInsets.all(32),
                    child: Text(s.noHistory, textAlign: TextAlign.center),
                  ),
                )
              : ListView(
                  padding: const EdgeInsets.all(16),
                  children: [
                    Text(s.historyNotice,
                        style: Theme.of(context).textTheme.bodySmall),
                    const SizedBox(height: 12),
                    ...receipts.map(
                      (r) => Card(
                        child: ListTile(
                          leading: Icon(
                            r.firstVerification
                                ? Icons.verified_outlined
                                : Icons.history,
                          ),
                          title: Text(r.brand.isEmpty ? r.batchNumber : r.brand),
                          subtitle: Text(
                            '${s.checkedAt}: ${r.checkedAt.toLocal()}\n'
                            '${s.resultText(_outcomeOf(r.outcome))}',
                          ),
                          isThreeLine: true,
                        ),
                      ),
                    ),
                  ],
                ),
    );
  }

  Outcome _outcomeOf(String name) => Outcome.values.firstWhere(
        (o) => o.name == name,
        orElse: () => Outcome.serviceUnavailable,
      );
}
