/// Filing a concern.
///
/// A token is not required. Someone whose code will not scan still needs a way
/// to raise a concern, so the printed reference is accepted instead. Location
/// is never requested.
library;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../app_state.dart';
import '../core/outcomes.dart';
import '../data/api_client.dart';
import '../ui/components.dart';
import '../ui/theme.dart';

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
    final tones = AppTones.of(context);
    final theme = Theme.of(context);
    final caseNumber = _caseNumber;

    if (caseNumber != null) {
      return Scaffold(
        appBar: AppBar(title: Text(s.reportTitle)),
        body: Center(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                IconBadge(icon: Icons.mark_email_read_outlined, tone: tones.match, size: 84),
                const SizedBox(height: 20),
                Text(s.reportFiled, textAlign: TextAlign.center, style: theme.textTheme.titleMedium),
                const SizedBox(height: 14),
                Container(
                  padding: const EdgeInsets.fromLTRB(20, 10, 8, 10),
                  decoration: BoxDecoration(
                    color: theme.colorScheme.surface,
                    borderRadius: BorderRadius.circular(16),
                    border: Border.all(color: tones.match.border),
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Flexible(
                        child: SelectableText(
                          caseNumber,
                          style: theme.textTheme.headlineSmall?.copyWith(letterSpacing: 1),
                        ),
                      ),
                      const SizedBox(width: 6),
                      IconButton(
                        tooltip: MaterialLocalizations.of(context).copyButtonLabel,
                        icon: const Icon(Icons.copy_rounded),
                        onPressed: () {
                          Clipboard.setData(ClipboardData(text: caseNumber));
                          ScaffoldMessenger.of(context)
                              .showSnackBar(SnackBar(content: Text(s.copied)));
                        },
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
        bottomNavigationBar: BottomActionBar(
          children: [
            FilledButton(
              onPressed: () => Navigator.of(context).pop(),
              child: Text(s.close),
            ),
          ],
        ),
      );
    }

    return Scaffold(
      appBar: AppBar(title: Text(s.reportTitle)),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(16, 4, 16, 24),
        children: [
          if (_error.isNotEmpty) ...[
            ToneBanner(tone: tones.danger, icon: Icons.error_outline_rounded, message: _error),
            const SizedBox(height: 12),
          ],
          SectionCard(
            title: s.reportReason,
            padding: const EdgeInsets.fromLTRB(8, 16, 8, 8),
            child: RadioGroup<String>(
              groupValue: _reason,
              onChanged: (value) => setState(() => _reason = value!),
              child: Column(
                children: _reasons
                    .map((code) => RadioListTile<String>(
                          value: code,
                          title: Text(s.reasonLabel(code)),
                          contentPadding: const EdgeInsets.symmetric(horizontal: 8),
                        ))
                    .toList(),
              ),
            ),
          ),
          const SizedBox(height: 12),
          SectionCard(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                // Labels sit above the fields rather than inside them: these
                // run long, in Bangla especially, and an in-field label is cut
                // off at one line.
                _FieldLabel(s.reportDescription),
                TextField(controller: _description, minLines: 3, maxLines: 5),
                const SizedBox(height: 16),
                _FieldLabel(s.reportReference),
                TextField(
                  controller: _reference,
                  decoration: const InputDecoration(prefixIcon: Icon(Icons.tag_rounded)),
                ),
                const SizedBox(height: 16),
                _FieldLabel(s.reportPharmacy),
                TextField(
                  controller: _pharmacy,
                  decoration:
                      const InputDecoration(prefixIcon: Icon(Icons.local_pharmacy_outlined)),
                ),
              ],
            ),
          ),
        ],
      ),
      bottomNavigationBar: BottomActionBar(
        children: [
          FilledButton.icon(
            onPressed: _busy ? null : _submit,
            icon: _busy
                ? const SizedBox(
                    width: 20,
                    height: 20,
                    child: CircularProgressIndicator(strokeWidth: 2.5),
                  )
                : const Icon(Icons.send_rounded),
            label: Text(_busy ? s.checking : s.submitReport),
          ),
        ],
      ),
    );
  }
}

class _FieldLabel extends StatelessWidget {
  const _FieldLabel(this.text);

  final String text;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8, left: 2),
      child: Text(text, style: Theme.of(context).textTheme.labelLarge),
    );
  }
}
