/// The verification API client.
///
/// Every signed response is verified here, against a key the trust manifest
/// authorises, before any of its contents reach a screen. The backend re-checks
/// everything server-side regardless: this verification protects the user from
/// a tampered or replayed response, it is not what decides the outcome.
library;

import 'dart:convert';
import 'dart:io';
import 'dart:math';
import 'dart:typed_data';

import 'package:http/http.dart' as http;

import '../core/outcomes.dart';
import '../crypto/verifier.dart';
import 'session_store.dart';
import 'trust_store.dart';

/// Raised when attestation fails.
///
/// Kept distinct because the SRS specifies a hard stop here: the user is told
/// the device cannot verify. If decision D20 later chooses a degraded path
/// instead, this is the single place that changes.
class AttestationRejected implements Exception {}

class ResponseUntrusted implements Exception {
  final String reason;
  ResponseUntrusted(this.reason);
  @override
  String toString() => 'ResponseUntrusted: $reason';
}

class PackageDetails {
  final String brand;
  final String generic;
  final String strength;
  final String dosageForm;
  final String packDescription;
  final String batchNumber;
  final String manufacturedOn;
  final String expiresOn;

  const PackageDetails({
    required this.brand,
    required this.generic,
    required this.strength,
    required this.dosageForm,
    required this.packDescription,
    required this.batchNumber,
    required this.manufacturedOn,
    required this.expiresOn,
  });
}

class PrepareResult {
  final Outcome outcome;
  final String? unitId;
  final String? challengeId;
  final PackageDetails? package;
  final List<String> restrictions;

  const PrepareResult({
    required this.outcome,
    this.unitId,
    this.challengeId,
    this.package,
    this.restrictions = const [],
  });
}

class ConfirmResult {
  final Outcome outcome;
  final bool firstVerificationRecorded;
  final String operationId;
  final DateTime checkedAt;

  /// False while the event is committed but its receipt is not yet signed.
  final bool receiptReady;

  const ConfirmResult({
    required this.outcome,
    required this.firstVerificationRecorded,
    required this.operationId,
    required this.checkedAt,
    this.receiptReady = true,
  });
}

class ApiClient {
  ApiClient({
    required this.baseUrl,
    required this.rootPublicKey,
    required SessionStore sessionStore,
    http.Client? httpClient,
    Future<String> Function()? attestationProvider,
  })  : _store = sessionStore,
        _http = httpClient ?? http.Client(),
        _attestation = attestationProvider ?? _defaultAttestation;

  final String baseUrl;
  final Uint8List rootPublicKey;
  final SessionStore _store;
  final http.Client _http;
  final Future<String> Function() _attestation;

  TrustManifest? _manifest;
  DateTime? _manifestFetchedAt;

  /// A fresh manifest is required for online verification. Twenty-four hours
  /// is the pilot's cache limit; an unknown or revoked key forces a refresh
  /// regardless.
  static const manifestMaxAge = Duration(hours: 24);

  static Future<String> _defaultAttestation() async {
    // Replaced by the Firebase App Check SDK once a project exists (D9).
    // Until then the development backend accepts any non-empty token, and the
    // production backend refuses this mode outright.
    return 'dev-token';
  }

  final _random = Random.secure();

  String _nonce() {
    final bytes = List<int>.generate(16, (_) => _random.nextInt(256));
    return base64Url.encode(bytes).replaceAll('=', '');
  }

  Future<Map<String, String>> _headers({bool withSession = true}) async {
    final headers = <String, String>{
      'Content-Type': 'application/json',
      'X-App-Check': await _attestation(),
    };
    if (withSession) {
      final credential = await _ensureSession();
      headers['Authorization'] = 'Session $credential';
    }
    return headers;
  }

  Future<String> _ensureSession() async {
    final existing = await _store.readCredential();
    if (existing != null && existing.isNotEmpty) return existing;

    final response = await _http.post(
      Uri.parse('$baseUrl/v1/consumer/sessions'),
      headers: {
        'Content-Type': 'application/json',
        'X-App-Check': await _attestation(),
      },
      body: json.encode({}),
    );
    if (response.statusCode == 401 || response.statusCode == 403) {
      throw AttestationRejected();
    }
    if (response.statusCode != 201) {
      throw ResponseUntrusted('could not create a session');
    }
    final body = json.decode(response.body) as Map<String, dynamic>;
    final credential = body['session_credential'] as String;
    await _store.writeCredential(credential);
    return credential;
  }

  Future<TrustManifest> _ensureManifest({bool force = false}) async {
    final cached = _manifest;
    final fetched = _manifestFetchedAt;
    if (!force &&
        cached != null &&
        fetched != null &&
        DateTime.now().difference(fetched) < manifestMaxAge) {
      return cached;
    }

    final response = await _http.get(Uri.parse('$baseUrl/v1/trust/manifest'));
    if (response.statusCode != 200) {
      throw ResponseUntrusted('trust manifest unavailable');
    }
    final body = json.decode(response.body) as Map<String, dynamic>;
    final manifest = verifyManifest(
      rootPublicKey: rootPublicKey,
      payload: base64.decode(body['payload'] as String),
      signature: base64.decode(body['signature'] as String),
      minimumVersion: await _store.readManifestVersion(),
    );
    await _store.writeManifestVersion(manifest.version);
    _manifest = manifest;
    _manifestFetchedAt = DateTime.now();
    return manifest;
  }

  /// Verifies a signed envelope and returns its parsed record.
  Future<Map<String, dynamic>> _openEnvelope(
    Map<String, dynamic> envelope, {
    required String expectedNonce,
    required SigContextKind kind,
  }) async {
    final keyId = envelope['key_id'] as String?;
    if (keyId == null) throw ResponseUntrusted('response names no key');

    var manifest = await _ensureManifest();
    var key = manifest[keyId];
    if (key == null) {
      // An unknown key means our manifest may be stale; refresh once before
      // refusing.
      manifest = await _ensureManifest(force: true);
      key = manifest[keyId];
    }
    if (key == null) throw ResponseUntrusted('response signed by an unknown key');
    if (key.isRevoked) throw ResponseUntrusted('response signed by a revoked key');

    final payload = base64.decode(envelope['payload'] as String);
    final signature = base64.decode(envelope['signature'] as String);
    final ok = verifySignature(
      publicKey: key.publicKey,
      payload: payload,
      signature: signature,
      context: kind == SigContextKind.status
          ? SigContext.status
          : SigContext.activation,
    );
    if (!ok) throw ResponseUntrusted('response signature did not verify');

    final record = parseStrict(payload);

    // Bind the response to this request and to a permitted age.
    if (record['request_nonce'] != expectedNonce) {
      throw ResponseUntrusted('response does not answer this request');
    }
    final expiresAt = DateTime.tryParse(record['expires_at'] as String? ?? '');
    if (expiresAt == null || DateTime.now().toUtc().isAfter(expiresAt)) {
      throw ResponseUntrusted('response has expired');
    }
    return record;
  }

  Future<PrepareResult> prepare(String token) async {
    final nonce = _nonce();
    final http.Response response;
    try {
      response = await _http.post(
        Uri.parse('$baseUrl/v1/consumer/verifications/prepare'),
        headers: await _headers(),
        body: json.encode({'token': token, 'nonce': nonce}),
      );
    } on SocketException {
      return const PrepareResult(outcome: Outcome.offline);
    }

    if (response.statusCode == 401 || response.statusCode == 403) {
      throw AttestationRejected();
    }
    if (response.statusCode != 200) {
      return const PrepareResult(outcome: Outcome.serviceUnavailable);
    }

    final body = json.decode(response.body) as Map<String, dynamic>;
    final status = await _openEnvelope(
      body['status'] as Map<String, dynamic>,
      expectedNonce: nonce,
      kind: SigContextKind.status,
    );

    final outcome = Outcome.fromWire(status['outcome'] as String?);
    final restrictions =
        (status['restrictions'] as List?)?.cast<String>() ?? const <String>[];

    PackageDetails? package;
    final credential = body['activation_credential'] as Map<String, dynamic>?;
    if (credential != null) {
      // The credential is verified and bound to *this* token before any of its
      // contents are shown. A genuine credential for another package must not
      // reach the screen.
      final payload = base64.decode(credential['payload'] as String);
      final manifest = await _ensureManifest();
      final key = manifest[credential['key_id'] as String];
      if (key == null || key.isRevoked) {
        throw ResponseUntrusted('credential signed by an untrusted key');
      }
      final ok = verifySignature(
        publicKey: key.publicKey,
        payload: payload,
        signature: base64.decode(credential['signature'] as String),
        context: SigContext.activation,
      );
      if (!ok) throw ResponseUntrusted('credential signature did not verify');

      final record = checkActivationBinding(
        payload,
        expectedTokenSha256: hashToken(token),
        expectedManufacturerId: key.organizationId ?? '',
        expectedKeyId: key.keyId,
      );
      final snapshot = record['product_snapshot'] as Map<String, dynamic>;
      package = PackageDetails(
        brand: snapshot['brand'] as String? ?? '',
        generic: snapshot['generic'] as String? ?? '',
        strength: snapshot['strength'] as String? ?? '',
        dosageForm: snapshot['dosage_form'] as String? ?? '',
        packDescription: snapshot['pack_description'] as String? ?? '',
        batchNumber: record['batch_number'] as String? ?? '',
        manufacturedOn: record['manufactured_on'] as String? ?? '',
        expiresOn: record['expires_on'] as String? ?? '',
      );
    }

    return PrepareResult(
      outcome: outcome,
      unitId: body['unit_id'] as String?,
      challengeId: body['challenge_id'] as String?,
      package: package,
      restrictions: restrictions,
    );
  }

  Future<ConfirmResult> confirm({
    required String unitId,
    required String challengeId,
    required String idempotencyKey,
  }) async {
    final nonce = _nonce();
    final response = await _http.post(
      Uri.parse('$baseUrl/v1/consumer/verifications/confirm'),
      headers: await _headers(),
      body: json.encode({
        'unit_id': unitId,
        'challenge_id': challengeId,
        'idempotency_key': idempotencyKey,
        'nonce': nonce,
      }),
    );

    if (response.statusCode == 401 || response.statusCode == 403) {
      throw AttestationRejected();
    }
    if (response.statusCode != 200) {
      return ConfirmResult(
        outcome: Outcome.serviceUnavailable,
        firstVerificationRecorded: false,
        operationId: '',
        checkedAt: DateTime.now(),
      );
    }

    final body = json.decode(response.body) as Map<String, dynamic>;
    final status = await _openEnvelope(
      body['status'] as Map<String, dynamic>,
      expectedNonce: nonce,
      kind: SigContextKind.status,
    );

    return ConfirmResult(
      outcome: Outcome.fromWire(status['outcome'] as String?),
      firstVerificationRecorded: body['first_verification_recorded'] as bool? ?? false,
      operationId: body['operation_id'] as String? ?? '',
      receiptReady: body['receipt_ready'] as bool? ?? false,
      checkedAt: DateTime.tryParse(status['issued_at'] as String? ?? '')?.toLocal() ??
          DateTime.now(),
    );
  }

  /// Re-reads an earlier attempt without recording a new check.
  ///
  /// Used when a confirmation committed but its response never arrived: the
  /// redemption already stands, and the app is waiting for the signed receipt.
  Future<ConfirmResult> operationStatus(String operationId) async {
    final nonce = _nonce();
    final response = await _http.post(
      Uri.parse('$baseUrl/v1/consumer/operations/$operationId/status'),
      headers: await _headers(),
      body: json.encode({'nonce': nonce}),
    );
    if (response.statusCode != 200) {
      throw ResponseUntrusted('operation status unavailable');
    }
    final body = json.decode(response.body) as Map<String, dynamic>;
    final status = await _openEnvelope(
      body['status'] as Map<String, dynamic>,
      expectedNonce: nonce,
      kind: SigContextKind.status,
    );
    return ConfirmResult(
      outcome: Outcome.fromWire(status['outcome'] as String?),
      firstVerificationRecorded: false,
      operationId: operationId,
      checkedAt: DateTime.tryParse(status['issued_at'] as String? ?? '')?.toLocal() ??
          DateTime.now(),
      receiptReady: body['receipt_ready'] as bool? ?? false,
    );
  }

  /// Refreshes a package's current status. Never redeems.
  ///
  /// A stored receipt cannot know about a recall published after it was made,
  /// which is why history refreshes rather than trusting what it holds.
  Future<Outcome> refreshStatus(String token) async {
    final nonce = _nonce();
    try {
      final response = await _http.post(
        Uri.parse('$baseUrl/v1/consumer/packages/status'),
        headers: await _headers(),
        body: json.encode({'token': token, 'nonce': nonce}),
      );
      if (response.statusCode != 200) return Outcome.serviceUnavailable;
      final body = json.decode(response.body) as Map<String, dynamic>;
      final status = await _openEnvelope(
        body['status'] as Map<String, dynamic>,
        expectedNonce: nonce,
        kind: SigContextKind.status,
      );
      return Outcome.fromWire(status['outcome'] as String?);
    } on SocketException {
      return Outcome.offline;
    }
  }

  Future<String> fileReport({
    required String reason,
    String description = '',
    String externalReference = '',
    String pharmacyNote = '',
  }) async {
    final response = await _http.post(
      Uri.parse('$baseUrl/v1/reports'),
      headers: await _headers(),
      body: json.encode({
        'reason': reason,
        'description': description,
        'external_reference': externalReference,
        'pharmacy_note': pharmacyNote,
      }),
    );
    if (response.statusCode != 201) {
      throw ResponseUntrusted('could not file the report');
    }
    return (json.decode(response.body) as Map<String, dynamic>)['case_number'] as String;
  }
}

enum SigContextKind { status, activation }
