/// Spike S2 harness.
///
/// This is not the consumer app. It exists to prove that ML-DSA verification
/// behaves identically on an Android device to the way it behaves on the
/// server, and to measure what that costs on real hardware. The screens
/// described in docs/09 replace this.
library;

import 'package:flutter/material.dart';

import 'crypto/self_check.dart';

void main() => runApp(const SelfCheckApp());

class SelfCheckApp extends StatelessWidget {
  const SelfCheckApp({super.key});

  @override
  Widget build(BuildContext context) => MaterialApp(
        title: 'Crypto self-check',
        theme: ThemeData(colorSchemeSeed: const Color(0xFF0B6B5E)),
        home: const SelfCheckPage(),
      );
}

class SelfCheckPage extends StatefulWidget {
  const SelfCheckPage({super.key});

  @override
  State<SelfCheckPage> createState() => _SelfCheckPageState();
}

class _SelfCheckPageState extends State<SelfCheckPage> {
  SelfCheckReport? _report;
  Object? _error;

  @override
  void initState() {
    super.initState();
    _run();
  }

  Future<void> _run() async {
    try {
      final report = await runSelfCheck();
      // Printed so a headless run can be read from the console too.
      debugPrint('SELFCHECK passed=${report.passedCount}/${report.results.length} '
          'p50=${report.verifyP50.inMicroseconds}us');
      for (final r in report.results) {
        debugPrint('SELFCHECK  [${r.passed ? "ok" : "FAIL"}] '
            '${r.check}/${r.name}: ${r.detail}');
      }
      if (mounted) setState(() => _report = report);
    } catch (e) {
      debugPrint('SELFCHECK ERROR $e');
      if (mounted) setState(() => _error = e);
    }
  }

  @override
  Widget build(BuildContext context) {
    final report = _report;
    return Scaffold(
      appBar: AppBar(title: const Text('ML-DSA self-check')),
      body: _error != null
          ? Center(child: Text('Error: $_error'))
          : report == null
              ? const Center(child: CircularProgressIndicator())
              : ListView(
                  padding: const EdgeInsets.all(16),
                  children: [
                    Card(
                      color: report.allPassed
                          ? Colors.green.shade50
                          : Colors.red.shade50,
                      child: Padding(
                        padding: const EdgeInsets.all(16),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              report.allPassed
                                  ? 'All ${report.results.length} vectors agree'
                                  : 'MISMATCH: ${report.passedCount}/${report.results.length}',
                              style: Theme.of(context).textTheme.titleMedium,
                            ),
                            const SizedBox(height: 8),
                            Text('verify p50: '
                                '${(report.verifyP50.inMicroseconds / 1000).toStringAsFixed(1)} ms '
                                '(${report.sampleCount} samples)'),
                            Text('two per scan: '
                                '${(report.verifyP50.inMicroseconds * 2 / 1000).toStringAsFixed(1)} ms'),
                          ],
                        ),
                      ),
                    ),
                    const SizedBox(height: 8),
                    ...report.results.map(
                      (r) => ListTile(
                        dense: true,
                        leading: Icon(
                          r.passed ? Icons.check_circle : Icons.cancel,
                          color: r.passed ? Colors.green : Colors.red,
                        ),
                        title: Text('${r.check}/${r.name}'),
                        subtitle: Text(r.detail),
                      ),
                    ),
                  ],
                ),
    );
  }
}
