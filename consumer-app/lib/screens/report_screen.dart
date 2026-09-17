/// Filing a concern.
///
/// A token is not required. Someone whose code will not scan still needs a way
/// to raise a concern, so the printed reference is accepted instead. Location
/// is never requested.
library;

import 'package:flutter/material.dart';

import '../app_state.dart';
import '../core/outcomes.dart';
import '../data/api_client.dart';

const _reasons = [
  'CODE_NOT_FOUND',
  'ALREADY_VERIFIED',
  'PACKAGING_SUSPICIOUS',
  'SCAN_FAILED',
  'OTHER',
];

class ReportScreen extends StatefulWidget {
  const ReportScreen({super.key, this.externalReference = ''});
  final String externalReference;

  @override
  State<ReportScreen> createState() => _ReportScreenState();
}

class _ReportScreenState extends State<ReportScreen> {
  String _reason = _reasons.first;
  final _description = TextEditingController();
  late final TextEditingController _reference =
      TextEditingController(text: widget.externalReference);
  final _pharmacy = TextEditingController();
  String? _caseNumber;
  String _error = '';
  bool _busy = false;

  @override
  void dispose() {
    _description.dispose();
    _reference.dispose();
    _pharmacy.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    setState(() {
      _busy = true;
      _error = '';
    });
    try {
      final caseNumber = await AppScope.of(context).client.fileReport(
            reason: _reason,
            description: _description.text,
            externalReference: _reference.text,
            pharmacyNote: _pharmacy.text,
          );
      if (mounted) setState(() => _caseNumber = caseNumber);
    } on AttestationRejected {
      // The same wording as anywhere else attestation fails.
      if (mounted) {
        setState(() => _error =
            AppScope.of(context).strings.resultText(Outcome.attestationFailed));
      }
    } catch (_) {
      if (mounted) {
        setState(() => _error = AppScope.of(context).strings.resultText(
              Outcome.serviceUnavailable,
            ));
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final s = AppScope.of(context).strings;
    final caseNumber = _caseNumber;

    return Scaffold(
      appBar: AppBar(title: Text(s.reportTitle)),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          if (caseNumber != null)
            Card(
              child: ListTile(
                leading: const Icon(Icons.check_circle_outline),
                title: Text(s.reportFiled),
                subtitle: SelectableText(caseNumber),
              ),
            )
          else ...[
            if (_error.isNotEmpty)
              Padding(
                padding: const EdgeInsets.only(bottom: 12),
                child: Text(_error,
                    style: TextStyle(color: Theme.of(context).colorScheme.error)),
              ),
            Text(s.reportReason, style: Theme.of(context).textTheme.labelLarge),
            const SizedBox(height: 8),
            RadioGroup<String>(
              groupValue: _reason,
              onChanged: (value) => setState(() => _reason = value!),
              child: Column(
                children: _reasons
                    .map((code) => RadioListTile<String>(
                          value: code,
                          title: Text(s.reasonLabel(code)),
                          dense: true,
                        ))
                    .toList(),
              ),
            ),
            const SizedBox(height: 8),
            TextField(
              controller: _description,
              decoration: InputDecoration(
                labelText: s.reportDescription,
                border: const OutlineInputBorder(),
              ),
              maxLines: 3,
            ),
            const SizedBox(height: 12),
            TextField(
              controller: _reference,
              decoration: InputDecoration(
                labelText: s.reportReference,
                border: const OutlineInputBorder(),
              ),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: _pharmacy,
              decoration: InputDecoration(
                labelText: s.reportPharmacy,
                border: const OutlineInputBorder(),
              ),
            ),
            const SizedBox(height: 16),
            FilledButton(
              onPressed: _busy ? null : _submit,
              child: Text(_busy ? s.checking : s.submitReport),
            ),
          ],
        ],
      ),
    );
  }
}
