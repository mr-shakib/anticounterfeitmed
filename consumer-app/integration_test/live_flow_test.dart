/// Drives the real API from a real device, end to end.
///
/// The camera is stubbed out -- the token is supplied directly -- but
/// everything after it is genuine: session creation, the root-signed trust
/// manifest, a prepared package whose credential is verified and bound to the
/// scanned token, and a committed confirmation.
///
/// Run with:
///   flutter test integration_test/live_flow_test.dart \
///     --dart-define=ROOT_PUBLIC_KEY=... --dart-define=TEST_TOKEN=...
library;

import 'dart:convert';

import 'package:consumer_app/core/outcomes.dart';
import 'package:consumer_app/core/scanned_url.dart';
import 'package:consumer_app/data/api_client.dart';
import 'package:consumer_app/data/session_store.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';

import '../test/support/label_codewords.dart';

const rootKey = String.fromEnvironment('ROOT_PUBLIC_KEY');
const token = String.fromEnvironment('TEST_TOKEN');
const baseUrl = String.fromEnvironment(
  'BACKEND_BASE_URL',
  defaultValue: 'http://10.0.2.2:8000',
);

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  late ApiClient client;

  setUp(() {
    client = ApiClient(
      baseUrl: baseUrl,
      rootPublicKey: base64.decode(rootKey),
      sessionStore: SessionStore(),
    );
  });

  testWidgets('the printed label parses to the expected token', (_) async {
    final scanned = parseScannedBarcode(
      text: publicUrl,
      rawBytes: labelCodewords(token),
    );
    expect(scanned, isNotNull);
    expect(scanned!.token, equals(token));
  });

  testWidgets('prepare returns a verified, bound package', (_) async {
    final prepared = await client.prepare(token);

    expect(prepared.outcome, equals(Outcome.verifiedFirst));
    expect(prepared.package, isNotNull,
        reason: 'the credential should have verified and bound');
    expect(prepared.package!.brand, isNotEmpty);
    expect(prepared.challengeId, isNotNull);
    debugPrint('LIVE package: ${prepared.package!.brand} '
        '${prepared.package!.strength}, batch ${prepared.package!.batchNumber}');
  });

  testWidgets('confirm commits exactly one first verification', (_) async {
    final prepared = await client.prepare(token);
    expect(prepared.challengeId, isNotNull, reason: 'needs a fresh challenge');

    final result = await client.confirm(
      unitId: prepared.unitId!,
      challengeId: prepared.challengeId!,
      idempotencyKey: 'integration-test-key',
    );
    debugPrint('LIVE confirm: ${result.outcome.name} '
        'first=${result.firstVerificationRecorded}');
    expect(result.outcome, equals(Outcome.verifiedFirst));
    expect(result.firstVerificationRecorded, isTrue);

    // A second scan of the same package is a repeat, never a second first.
    final again = await client.prepare(token);
    expect(again.outcome, equals(Outcome.previouslyVerified));
  });

  testWidgets('an unknown token gets a verifiable negative answer', (_) async {
    const unknown = 'AAAABBBBCCCCDDDDEEEEFFFFGGGGHHHHIIIIJJJJKKK';
    final prepared = await client.prepare(unknown);
    expect(prepared.outcome, equals(Outcome.notFound));
    expect(prepared.package, isNull);
  });
}
