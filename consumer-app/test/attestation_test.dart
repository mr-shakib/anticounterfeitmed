/// Attestation behaviour that can be checked off a device.
///
/// Play Integrity itself needs real hardware, Play Services and a Firebase
/// project. What is testable here is the part that decides whether a request
/// is made at all: a build that cannot attest must not reach the network, and
/// must not substitute anything for the token.
library;

import 'dart:typed_data';

import 'package:consumer_app/data/api_client.dart';
import 'package:consumer_app/data/attestation.dart';
import 'package:consumer_app/data/session_store.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;

/// Fails the test if the client reaches the network.
class _NoRequests extends http.BaseClient {
  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    fail('a request was made without an attestation token: ${request.url}');
  }
}

/// Keeps the credential in memory, so no test touches the platform keystore.
class _MemorySessionStore extends SessionStore {
  String? _credential;

  @override
  Future<String?> readCredential() async => _credential;

  @override
  Future<void> writeCredential(String credential) async =>
      _credential = credential;

  @override
  Future<void> clearCredential() async => _credential = null;
}

ApiClient clientWith(Future<String> Function() provider) => ApiClient(
      baseUrl: 'https://example.invalid',
      rootPublicKey: Uint8List(0),
      sessionStore: _MemorySessionStore(),
      httpClient: _NoRequests(),
      attestationProvider: provider,
    );

void main() {
  test('a build with no Firebase project is not configured', () {
    // The test build carries no FIREBASE_* defines, which is the case this
    // guards: nothing silently stands in for a project.
    expect(isAttestationConfigured, isFalse);
  });

  test('an unconfigured development build sends the placeholder', () async {
    // kReleaseMode is false under the test runner. The release case is the
    // throw in attestationToken, which a release build exercises.
    expect(await attestationToken(), developmentToken);
  });

  test('a device that cannot attest makes no request', () async {
    final client = clientWith(
      () async => throw AttestationUnavailable('no Play Services'),
    );
    await expectLater(
      client.prepare('x' * 43),
      throwsA(isA<AttestationRejected>()),
    );
  });

  test('the refusal reason is carried, and carries no token', () async {
    final client = clientWith(
      () async => throw AttestationUnavailable('no Play Services'),
    );
    try {
      await client.prepare('x' * 43);
      fail('expected a refusal');
    } on AttestationRejected catch (error) {
      expect(error.reason, 'no Play Services');
      expect(error.toString(), isNot(contains('x' * 43)));
    }
  });
}
